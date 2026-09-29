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
from hoctap.learning.models import progress_events, progress_sessions

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


def session_wrong_problem_ids(conn: Any, session_id: str) -> list[str]:
    """The frozen `problem_ids` of `session_id` that were NOT answered correctly on the
    first try, in their original Session order.

    Reads ONLY `attempt` events, per the frozen spec text ("find the EARLIEST stored
    `attempt` event ... and check its stored `correct` field") and the Story 2.8
    `deferred-work.md` entry it echoes: `self_marked`/`fallback_revealed` are a
    self-report/telemetry marker, never a `grade_part()` verdict, and must NOT be counted
    into first-try accuracy. Every `attempt` event's Part gets its own earliest-by-rowid
    verdict (the same insertion-order tiebreak `_part_currently_correct()` established in
    Story 2.5 -- `received_at`/the client id are not reliable orderings within one batch).
    The Problem counts as first-try-correct only if EVERY Part it has any `attempt` for was
    correct on that Part's own earliest attempt (implementer's call for a multi-Part
    Problem -- documented in this story's Implementation Notes).

    A Problem with NO `attempt` event within this Session at all -- either a `fallback`-type
    Problem (Story 2.8's self-check never posts `attempt`, only `self_marked`) or an
    unsupported Part type skipped straight past -- is treated as NOT first-try-correct:
    absence of evidence is not evidence of a correct first try. This is a known, documented
    limitation for fallback Problems specifically (a child who self-marked "đúng" still
    sees that Problem counted as "wrong"/offered for replay) -- see this story's
    Implementation Notes and the extended `deferred-work.md` entry.
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

    wrong: list[str] = []
    for problem_id in problem_ids:
        parts = first_seen.get(problem_id)
        if not parts or not all(parts.values()):
            wrong.append(problem_id)
    return wrong


def compute_streak(conn: Any, profile_id: str, today: date) -> int:
    """Days in a row (Asia/Ho_Chi_Minh calendar dates), ending today or yesterday, with at
    least one completed, non-`replay`-mode Session (AD-6 excludes `replay` from every
    derived metric).

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
            progress_sessions.c.mode != "replay",
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
    return SessionSummary(
        first_try_correct=first_try_correct,
        total=total,
        wrong_problem_ids=wrong_ids,
        streak=streak,
    )
