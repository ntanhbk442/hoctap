"""Star computation and awarding (Story 3.1, AD-6).

A new per-Problem aggregation ACROSS Parts (`compute_problem_stars()`) -- Story 2.5's
staged-help logic (`_count_prior_wrong()`/`_part_currently_correct()` in
`learning.sessions`) is per-Part, this is the missing per-Problem rollup. Written into
`progress_stars` inside the SAME transaction (SAVEPOINT) as whichever event resolves the
Problem for this Session -- `post_event()` calls `maybe_award_stars()` right after
inserting that event, inside its own existing `conn.begin_nested()`, never a second
commit boundary.

Stars are 0/1/3, never an arbitrary int (matches `progress_stars`'s own CHECK
constraint):
- **3**: every graded Part's FIRST attempt within this Session was correct.
- **1**: some Part needed a Hint/retry, but no Part ever had its Solution shown within
  this Session -- OR a `fallback` Problem whose `self_marked` event is `correct: true`.
- **0**: any Part had its Solution shown within this Session -- OR a `fallback` Problem
  whose `self_marked` event is `correct: false`. Implementer's call (documented, per this
  story's frozen Boundaries): a `0` row IS written, not skipped, so a plain `SUM(stars)`
  and "how many Problems has this Session resolved" both stay simple without a reader
  needing to know about a hidden "no row at all" third state.

"Solution shown" is read directly off each stored `attempt` event's own
`payload["solution"]` (non-null exactly when `_grade_and_stage()` released a Solution for
that attempt) -- never re-derived by re-running `_count_prior_wrong()`'s Profile-wide
count, which would disagree with what actually happened in THIS Session for a Part that
had prior wrong attempts in an earlier Session.

Only `practice`/`retry`/`concept`-mode Sessions award Stars per event
(`STAR_AWARDING_MODES`) -- `quiz` (Story 3.4) is graded all at once at `quiz_submitted` by
`compute_quiz_stars()`/`award_quiz_stars()` below (3 or 0, no 1-Star tier), and `replay`
never awards, matching Story 2.10's existing
mode-gate pattern (`_grade_and_stage()`'s own `mode != "replay"` Retry-Queue gate).
`compute_problem_stars()` itself stays mode-agnostic (a pure "what WOULD the Stars be"
query) -- the mode gate is applied only by `maybe_award_stars()`, the one caller that
actually writes a row.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select, text

from hoctap.content.effective import ProblemNotFound, load_one
from hoctap.content.schema import FallbackPart
from hoctap.ids import new_id
from hoctap.learning.models import progress_events, progress_sessions, progress_stars

STAR_AWARDING_MODES = frozenset({"practice", "retry", "concept"})


def compute_problem_stars(conn: Any, session_id: str, problem_id: str) -> int | None:
    """3/1/0, or `None` if this Problem's outcome for this Session is not yet
    determinable -- either because the content layer can no longer resolve it (mirrors
    `get_bundle()`'s own defensive `ProblemNotFound`/`state.doc is None` skip: nothing to
    score without a Part list), or because it genuinely has not been resolved yet (a
    graded Part with no attempt at all this Session, or one still wrong-pending-a-later-
    attempt; a `fallback` Problem with no `self_marked` event yet this Session)."""
    try:
        state = load_one(conn, problem_id)
    except ProblemNotFound:
        return None
    if state.doc is None:
        return None
    parts = list(state.doc.parts)
    if any(isinstance(p, FallbackPart) for p in parts):
        return _fallback_stars(conn, session_id, problem_id)
    return _graded_stars(conn, session_id, problem_id, parts)


def _fallback_stars(conn: Any, session_id: str, problem_id: str) -> int | None:
    """A `fallback` Problem's single `self_marked` outcome maps directly: "đúng" -> 1,
    "chưa đúng" -> 0. If `self_marked` was posted more than once for this Problem+Session
    (a genuine change of mind, not a resend -- a resend shares the same event id and never
    reaches here twice), the LATEST one (Session insertion order, i.e. `rowid`) wins."""
    rows = conn.execute(
        select(progress_events.c.payload_json)
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "self_marked",
        )
        .order_by(text("progress_events.rowid ASC"))
    )
    latest: bool | None = None
    for row in rows:
        payload = json.loads(row.payload_json)
        correct = payload.get("correct")
        if isinstance(correct, bool):
            latest = correct
    if latest is None:
        return None
    return 1 if latest else 0


def _graded_stars(conn: Any, session_id: str, problem_id: str, parts: list[Any]) -> int | None:
    graded_keys = [p.part_key for p in parts if not isinstance(p, FallbackPart)]
    if not graded_keys:
        return None

    rows = conn.execute(
        select(progress_events.c.payload_json)
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "attempt",
        )
        .order_by(text("progress_events.rowid ASC"))
    )
    # part_key -> this Session's attempts on it, in Session order: (correct, solution_shown).
    by_part: dict[str, list[tuple[bool, bool]]] = {}
    for row in rows:
        payload = json.loads(row.payload_json)
        part_key = payload.get("part_key")
        if part_key not in graded_keys:
            continue
        by_part.setdefault(part_key, []).append(
            (bool(payload.get("correct")), payload.get("solution") is not None)
        )

    all_first_try = True
    any_solution_shown = False
    for key in graded_keys:
        attempts = by_part.get(key)
        if not attempts:
            return None  # this Part has no attempt yet this Session -- not resolved
        first_correct, _ = attempts[0]
        latest_correct, _ = attempts[-1]
        if not latest_correct:
            return None  # still wrong-pending-a-later-attempt -- not resolved yet
        if not first_correct:
            all_first_try = False
        if any(shown for _, shown in attempts):
            any_solution_shown = True

    if all_first_try:
        return 3
    return 0 if any_solution_shown else 1


def maybe_award_stars(
    conn: Any,
    now_iso: str,
    session_id: str,
    profile_id: str,
    problem_id: str,
    mode: str,
) -> None:
    """Awards this Session's Stars for `problem_id`, exactly once, the moment it becomes
    determinable. A no-op when: `mode` never awards Stars (`STAR_AWARDING_MODES`); the
    outcome isn't determinable yet (`compute_problem_stars()` returns `None`); or a
    `progress_stars` row for this (`session_id`, `problem_id`) already exists (idempotency
    -- a resent resolving event, or two events of one batch both resolving the same
    Problem, must never insert a duplicate or overwrite a different value)."""
    if mode not in STAR_AWARDING_MODES:
        return
    stars = compute_problem_stars(conn, session_id, problem_id)
    if stars is None:
        return
    existing = conn.execute(
        select(progress_stars.c.id).where(
            progress_stars.c.session_id == session_id,
            progress_stars.c.problem_id == problem_id,
        )
    ).first()
    if existing is not None:
        return
    conn.execute(
        progress_stars.insert().values(
            id=new_id(),
            session_id=session_id,
            profile_id=profile_id,
            problem_id=problem_id,
            stars=stars,
            awarded_at=now_iso,
        )
    )


def quiz_part_verdicts(
    conn: Any, session_id: str, problem_id: str, graded_keys: list[str]
) -> dict[str, bool]:
    """Story 3.4: each graded Part's verdict in a quiz Session -- its FIRST stored `attempt`
    (rowid order) for this Session. A Part with no attempt is unanswered, i.e. wrong."""
    rows = conn.execute(
        select(progress_events.c.payload_json)
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "attempt",
        )
        .order_by(text("progress_events.rowid ASC"))
    )
    first: dict[str, bool] = {}
    for row in rows:
        payload = json.loads(row.payload_json)
        key = payload.get("part_key")
        if key in graded_keys and key not in first:
            first[key] = payload.get("correct") is True
    return {key: first.get(key, False) for key in graded_keys}


def compute_quiz_stars(conn: Any, session_id: str, problem_id: str) -> int:
    """Story 3.4: 3 when every graded Part was right (first attempt), otherwise 0. A
    `fallback` Problem (self-check only, never graded in a quiz) and a Problem the content
    layer can no longer resolve are always 0."""
    try:
        state = load_one(conn, problem_id)
    except ProblemNotFound:
        return 0
    if state.doc is None:
        return 0
    parts = list(state.doc.parts)
    if any(isinstance(p, FallbackPart) for p in parts):
        return 0
    graded_keys = [p.part_key for p in parts]
    if not graded_keys:
        return 0
    verdicts = quiz_part_verdicts(conn, session_id, problem_id, graded_keys)
    return 3 if all(verdicts.values()) else 0


def quiz_stars_eligible(conn: Any, session_id: str) -> bool:
    """Story 3.4 retake rule: Stars are awarded only when no OTHER Session of the same
    Profile and Lesson (same `ref_key`) already has a stored `quiz_submitted` event."""
    session = conn.execute(
        select(progress_sessions.c.profile_id, progress_sessions.c.ref_key).where(
            progress_sessions.c.id == session_id
        )
    ).one()
    earlier = conn.execute(
        select(progress_events.c.id)
        .join(progress_sessions, progress_sessions.c.id == progress_events.c.session_id)
        .where(
            progress_sessions.c.profile_id == session.profile_id,
            progress_sessions.c.ref_key == session.ref_key,
            progress_sessions.c.id != session_id,
            progress_events.c.kind == "quiz_submitted",
        )
        .limit(1)
    ).first()
    return earlier is None


def award_quiz_stars(
    conn: Any, now_iso: str, session_id: str, profile_id: str, problem_ids: list[str]
) -> tuple[dict[str, int], bool]:
    """Story 3.4: writes one `progress_stars` row (3 or 0) per Problem, once per (Session,
    Problem), unless this is a retake (`quiz_stars_eligible()`), which writes none.
    Returns the Stars per Problem (all 0 for a retake) and whether Stars were awarded."""
    eligible = quiz_stars_eligible(conn, session_id)
    out: dict[str, int] = {}
    for problem_id in problem_ids:
        stars = compute_quiz_stars(conn, session_id, problem_id)
        if not eligible:
            out[problem_id] = 0
            continue
        out[problem_id] = stars
        existing = conn.execute(
            select(progress_stars.c.id).where(
                progress_stars.c.session_id == session_id,
                progress_stars.c.problem_id == problem_id,
            )
        ).first()
        if existing is None:
            conn.execute(
                progress_stars.insert().values(
                    id=new_id(),
                    session_id=session_id,
                    profile_id=profile_id,
                    problem_id=problem_id,
                    stars=stars,
                    awarded_at=now_iso,
                )
            )
    return out, eligible


def session_stars_earned(conn: Any, session_id: str) -> int:
    """`SUM(stars)` for one Session -- `GET /sessions/{id}/summary`'s `stars_earned`."""
    result = conn.execute(
        select(func.coalesce(func.sum(progress_stars.c.stars), 0)).where(
            progress_stars.c.session_id == session_id
        )
    ).scalar_one()
    return int(result)


def total_stars(conn: Any, profile_id: str) -> int:
    """All-time `SUM(stars)` for a Profile -- the Home-facing total. Every
    `progress_stars` row already belongs to a Star-awarding-mode Session
    (`maybe_award_stars()`'s own mode gate keeps a `replay`/`quiz` Session from ever
    writing one), so no extra mode filter is needed here."""
    result = conn.execute(
        select(func.coalesce(func.sum(progress_stars.c.stars), 0)).where(
            progress_stars.c.profile_id == profile_id
        )
    ).scalar_one()
    return int(result)
