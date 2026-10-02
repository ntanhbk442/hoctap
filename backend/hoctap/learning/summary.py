"""Session summary computation (Story 2.10): first-try accuracy, wrong-Problem ids, and
the Streak count -- everything `GET /sessions/{id}/summary` and `ReplayRef.resolve()` both
need, kept in one place so they can never disagree about what "the wrong Problems of this
Session" means.

Per-Session, not Profile-wide (unlike Story 2.5's Retry-Queue counting): first-try accuracy
is scoped to `session_id`, matching this story's frozen Boundaries & Constraints.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from hoctap.ids import from_iso
from hoctap.learning.models import progress_badges, progress_events, progress_sessions
from hoctap.learning.scoring import session_stars_earned

# The PRD's Streak is defined in child-local calendar days (AD-6/this story's frozen
# Intent), not UTC -- every `occurred_at`/`completed_at` timestamp is stored as UTC ISO-8601
# (`ids.to_iso()`) and converted to this zone before taking its calendar date.
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _local_date(iso_value: str) -> date:
    return from_iso(iso_value).astimezone(LOCAL_TZ).date()


@dataclass(frozen=True)
class SessionSummary:
    first_try_correct: int
    total: int
    wrong_problem_ids: list[str]
    streak: int
    # Story 3.1: `SUM(progress_stars.stars)` for this Session -- a DIFFERENT, wider
    # metric than `first_try_correct` (which only ever reads `attempt` events, per this
    # module's own docstring): `stars_earned` also counts a `fallback` Problem's
    # self-marked "đúng" (1 Star, but never first-try-correct -- that metric can't see
    # `self_marked` at all) and awards a graded Problem needing only a Hint/retry a Star
    # too, not just a flawless first try.
    stars_earned: int
    # Story 3.2: the `badge_key`s newly earned by events posted during THIS Session
    # (`[]` otherwise) -- see `session_new_badges()`'s own docstring for how that's
    # derived without a `session_id` column on `progress_badges`.
    new_badges: list[str]


def session_new_badges(conn: Any, session_id: str) -> list[str]:
    """The `badge_key`s newly earned by events posted during THIS Session. Deliberately
    lives here, not in `learning.badges` (which this module already depends on for
    `compute_streak()`/`LOCAL_TZ` reuse -- importing back from `learning.badges` here
    would be circular): a badge's `earned_at` is always set to exactly the `received_at`
    of the one event whose processing triggered `learning.badges.maybe_award_badges()`
    to insert it (see `learning.sessions.post_event()`), so matching this Session's own
    set of event `received_at` values against the Profile's `progress_badges` rows
    identifies exactly the badge(s) (if any) THIS Session itself caused -- no
    `session_id` column needed on `progress_badges` (which, per this story's frozen
    Boundaries, only ever carries `id`/`profile_id`/`badge_key`/`earned_at`)."""
    session = conn.execute(
        select(progress_sessions.c.profile_id).where(progress_sessions.c.id == session_id)
    ).one()
    received_ats = {
        row.received_at
        for row in conn.execute(
            select(progress_events.c.received_at).where(
                progress_events.c.session_id == session_id
            )
        )
    }
    if not received_ats:
        return []
    rows = conn.execute(
        select(progress_badges.c.badge_key, progress_badges.c.earned_at)
        .where(progress_badges.c.profile_id == session.profile_id)
        .order_by(progress_badges.c.earned_at.asc())
    )
    return [row.badge_key for row in rows if row.earned_at in received_ats]


def session_wrong_problem_ids(conn: Any, session_id: str) -> list[str]:
    """The frozen `problem_ids` of `session_id` that were NOT answered correctly on the
    first try, in their original Session order.

    A graded Problem reads `attempt` events (per the frozen spec text: find the EARLIEST
    stored `attempt` event of each Part and check its stored `correct` field; earliest by
    rowid, the same insertion-order tiebreak `_part_currently_correct()` established in
    Story 2.5 -- `received_at`/the client id are not reliable orderings within one batch).
    The Problem counts as first-try-correct only if EVERY Part it has any `attempt` for was
    correct on that Part's own earliest attempt (implementer's call for a multi-Part
    Problem -- documented in this story's Implementation Notes).

    A `fallback`-type Problem never posts an `attempt` (Story 2.8's self-check only posts
    `self_marked`). Epic 2 review decision (reversing Story 2.10's original wording): its
    first-try result is the `correct` flag of the EARLIEST `self_marked` event for it in
    this Session -- true counts as correct, false as wrong. A Problem with neither an
    `attempt` nor a `self_marked` event in this Session is still NOT first-try-correct:
    absence of evidence is not evidence of a correct first try. `fallback_revealed` is pure
    telemetry and never counts.
    """
    session = conn.execute(
        select(progress_sessions.c.problem_ids_json).where(progress_sessions.c.id == session_id)
    ).one()
    problem_ids: list[str] = json.loads(session.problem_ids_json)

    rows = conn.execute(
        select(
            progress_events.c.problem_id,
            progress_events.c.payload_json,
        )
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.kind == "attempt",
        )
        .order_by(text("progress_events.rowid ASC"))
    )

    # problem_id -> part_key -> first-seen `correct`.
    first_seen: dict[str, dict[str, bool]] = {}
    for row in rows:
        if row.problem_id is None:
            continue
        payload = json.loads(row.payload_json)
        part_key = payload.get("part_key")
        if part_key is None:
            continue
        parts = first_seen.setdefault(row.problem_id, {})
        if part_key in parts:
            continue  # only the EARLIEST attempt per Part counts
        correct = payload.get("correct")
        parts[part_key] = bool(correct)

    # problem_id -> first-seen self-mark `correct` (fallback Problems only have these).
    first_self_mark: dict[str, bool] = {}
    for row in conn.execute(
        select(progress_events.c.problem_id, progress_events.c.payload_json)
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.kind == "self_marked",
        )
        .order_by(text("progress_events.rowid ASC"))
    ):
        if row.problem_id is None or row.problem_id in first_self_mark:
            continue
        first_self_mark[row.problem_id] = json.loads(row.payload_json).get("correct") is True

    wrong: list[str] = []
    for problem_id in problem_ids:
        parts = first_seen.get(problem_id)
        if parts:
            ok = all(parts.values())
        else:
            ok = first_self_mark.get(problem_id, False)
        if not ok:
            wrong.append(problem_id)
    return wrong


def first_try_solved_problem_ids(
    conn: Any, profile_id: str, problem_ids: list[str]
) -> set[str]:
    """Of `problem_ids`, those the Profile solved correctly on the first try in some earlier
    `practice`/`retry`/`concept` Session (`quiz`, `replay` and `exam` Sessions do not count
    -- Story 8.1 extends this module's existing quiz/replay exclusion to exam Sessions too,
    for the same reason: a Concept practice Session's "already solved" prioritisation
    should reflect ordinary practice history, not a timed assessment). Same
    rule as `session_wrong_problem_ids()` (earliest `attempt` per Part by rowid, every Part
    correct; a Problem with no `attempt` uses its earliest `self_marked`), evaluated per
    Session in ONE query over the Profile's events."""
    if not problem_ids:
        return set()
    wanted = set(problem_ids)
    rows = conn.execute(
        select(
            progress_events.c.session_id,
            progress_events.c.problem_id,
            progress_events.c.kind,
            progress_events.c.payload_json,
        )
        .select_from(
            progress_events.join(
                progress_sessions, progress_sessions.c.id == progress_events.c.session_id
            )
        )
        .where(
            progress_sessions.c.profile_id == profile_id,
            progress_sessions.c.mode.notin_(["quiz", "replay", "exam"]),
            progress_events.c.kind.in_(["attempt", "self_marked"]),
            progress_events.c.problem_id.in_(list(wanted)),
        )
        .order_by(text("progress_events.rowid ASC"))
    ).all()
    attempts: dict[tuple[str, str], dict[str, bool]] = {}
    marks: dict[tuple[str, str], bool] = {}
    for row in rows:
        key = (row.session_id, row.problem_id)
        payload = json.loads(row.payload_json)
        if row.kind == "attempt":
            part_key = payload.get("part_key")
            if part_key is None:
                continue
            parts = attempts.setdefault(key, {})
            parts.setdefault(part_key, bool(payload.get("correct")))
        elif key not in marks:
            marks[key] = payload.get("correct") is True
    solved: set[str] = set()
    for key, parts in attempts.items():
        if parts and all(parts.values()):
            solved.add(key[1])
    for key, ok in marks.items():
        if key not in attempts and ok:
            solved.add(key[1])
    return solved


def compute_streak(conn: Any, profile_id: str, today: date) -> int:
    """Days in a row (Asia/Ho_Chi_Minh calendar dates), ending today or yesterday, with at
    least one completed, non-`replay`/non-`exam`-mode Session (AD-6 excludes `replay` from
    every derived metric; Story 8.1 extends the same exclusion to `exam` -- a pure
    assessment Session contributes NOTHING to the Streak, same as it awards zero Stars and
    adds zero Retry Queue rows).

    "Still alive" boundary (implementer's call, documented per the spec's own note): a
    Streak survives a day with nothing completed YET -- it counts backward from today if
    today already has a completed Session, else from yesterday (so a Streak built up to and
    including yesterday still reads correctly during today, before today's own Session is
    finished) -- but a Streak with NEITHER today nor yesterday completed reads 0 (the gap is
    real, not merely "today isn't over yet").
    """
    rows = conn.execute(
        select(progress_sessions.c.completed_at).where(
            progress_sessions.c.profile_id == profile_id,
            progress_sessions.c.mode.notin_(("replay", "exam")),
            progress_sessions.c.completed_at.isnot(None),
        )
    )
    days = {_local_date(row.completed_at) for row in rows}

    cursor = today
    if cursor not in days:
        cursor = today - timedelta(days=1)
        if cursor not in days:
            return 0

    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def compute_summary(conn: Any, session: Any, today: date) -> SessionSummary:
    """The full `GET /sessions/{id}/summary` payload for an already-`_load_session()`-ed
    row. Caller (the API/service layer) is responsible for the 422-before-`completed_at`
    guard -- this function only computes, it never decides whether it's callable yet."""
    problem_ids: list[str] = json.loads(session.problem_ids_json)
    wrong_ids = session_wrong_problem_ids(conn, session.id)
    total = len(problem_ids)
    first_try_correct = total - len(wrong_ids)
    streak = compute_streak(conn, session.profile_id, today)
    stars_earned = session_stars_earned(conn, session.id)
    new_badges = session_new_badges(conn, session.id)
    return SessionSummary(
        first_try_correct=first_try_correct,
        total=total,
        wrong_problem_ids=wrong_ids,
        streak=streak,
        stars_earned=stars_earned,
        new_badges=new_badges,
    )
