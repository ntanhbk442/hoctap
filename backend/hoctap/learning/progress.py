"""The honestly-limited "attempted" progress concept (Story 2.4, see the frozen Intent):
whether a Problem has been attempted at all, in any past Session -- never whether it was
correct (that needs a grader, Story 2.5).

Kept in `learning` (not `content.library`, which this story's frozen spec forbids
modifying) so the Library router can enrich its per-Lesson denominator with a real
numerator without content.library needing to know progress_events exists.
"""

from __future__ import annotations

from sqlalchemy import Connection, delete, select

from hoctap.content import effective
from hoctap.learning.models import (
    progress_assignments,
    progress_badges,
    progress_events,
    progress_retry_items,
    progress_sessions,
    progress_stars,
)


def attempted_problem_ids(conn: Connection, profile_id: str) -> set[str]:
    """Every `problem_id` with at least one `attempt` event for `profile_id`, across all
    Sessions."""
    rows = conn.execute(
        select(progress_events.c.problem_id)
        .where(
            progress_events.c.profile_id == profile_id,
            progress_events.c.kind == "attempt",
            progress_events.c.problem_id.is_not(None),
        )
        .distinct()
    )
    return {r.problem_id for r in rows}


def attempted_lesson_counts(
    conn: Connection, book_id: str, profile_id: str
) -> dict[tuple[str, str], int]:
    """The attempted-and-still-visible Problem count per (unit_key, lesson_key) of one
    Book, for `profile_id` -- the same visible-Problem set `content.library`'s own
    denominator uses, so the numerator never exceeds it. One query pass per Book, mirroring
    `content.library._visible_counts()`'s own shape (not reused directly: that function is
    private to `content.library`, which this story may not modify)."""
    attempted = attempted_problem_ids(conn, profile_id)
    if not attempted:
        return {}
    counts: dict[tuple[str, str], int] = {}
    for state in effective.load_effective(conn, book_id=book_id, include_retired=False):
        if state.visible and state.problem_id in attempted:
            key = (state.unit_key, state.lesson_key)
            counts[key] = counts.get(key, 0) + 1
    return counts


def delete_profile_progress(conn: Connection, profile_id: str) -> None:
    """Removes every `progress_*` row of `profile_id` (Story 4.1), Assignments included
    (Story 4.3). Runs inside the caller's transaction; events and stars go before sessions
    (FK order). `progress_sessions.assignment_id` is a plain column (no FK), so the
    Assignments can go in any order. No FK cascades exist."""
    for table in (
        progress_events,
        progress_stars,
        progress_retry_items,
        progress_badges,
        progress_assignments,
    ):
        conn.execute(delete(table).where(table.c.profile_id == profile_id))
    conn.execute(delete(progress_sessions).where(progress_sessions.c.profile_id == profile_id))
