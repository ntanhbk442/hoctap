"""Badge awarding (Story 3.2, AD-6). Reuses Story 3.1's exact transactional pattern
(`learning.scoring.maybe_award_stars()`): a `progress_badges` row is written the moment
a badge's condition first becomes true, in the SAME transaction/SAVEPOINT as whichever
event caused it -- `post_event()` calls `maybe_award_badges()` right after
`maybe_award_stars()`, never a second commit boundary.

Three fixed badges (`BADGE_KEYS`, matching `progress_badges`'s own CHECK constraint):
- `week1`: the Profile's first-ever completed (`session_completed`), non-`replay`-mode
  Session -- a human decision (this story's frozen Intent), not a curriculum-position or
  elapsed-calendar-time check. Award on that Session's own completion, once, ever.
- `streak7`: `compute_streak(conn, profile_id, today) >= 7` (Story 3.1, reused unchanged).
- `stars100`: `total_stars(conn, profile_id) >= 100` (Story 3.1, reused unchanged) -- a
  one-time threshold crossing, never re-checked once earned.

Only `practice`/`retry`/`concept`/`quiz`-mode Sessions ever trigger a check
(`BADGE_CHECK_MODES`) -- `replay` never counts toward Streak/Stars (AD-6's mode table),
so it must never trigger a badge check either. Each checker's condition is computed
unconditionally on every call; idempotency is enforced by `_award_if_new()`, which only
ever inserts once per (profile_id, badge_key) -- a resent/duplicate-triggering event (or
a Session already past a badge's threshold) is a pure no-op, never a second row or a
repeat "newly earned" result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select

from hoctap.ids import from_iso, new_id
from hoctap.learning.models import progress_badges, progress_sessions
from hoctap.learning.scoring import total_stars
from hoctap.learning.summary import LOCAL_TZ, compute_streak

BADGE_KEYS: tuple[str, ...] = ("week1", "streak7", "stars100")
BADGE_CHECK_MODES = frozenset({"practice", "retry", "concept", "quiz"})


def _today_from_iso(now_iso: str) -> date:
    return from_iso(now_iso).astimezone(LOCAL_TZ).date()


def _check_week1(conn: Any, profile_id: str) -> bool:
    """The Profile's first-ever completed, non-`replay`-mode Session (this story's
    frozen Intent) -- true as soon as ANY such Session has `completed_at` set, not
    specifically the one whose event just triggered this check."""
    row = conn.execute(
        select(progress_sessions.c.id)
        .where(
            progress_sessions.c.profile_id == profile_id,
            progress_sessions.c.mode != "replay",
            progress_sessions.c.completed_at.isnot(None),
        )
        .limit(1)
    ).first()
    return row is not None


def _check_streak7(conn: Any, profile_id: str, today: date) -> bool:
    return compute_streak(conn, profile_id, today) >= 7


def _check_stars100(conn: Any, profile_id: str) -> bool:
    return total_stars(conn, profile_id) >= 100


def _award_if_new(conn: Any, now_iso: str, profile_id: str, badge_key: str) -> bool:
    """Inserts `progress_badges` for (`profile_id`, `badge_key`) if it doesn't already
    exist, returning whether it was newly inserted -- the one place idempotency is
    enforced (matches `maybe_award_stars()`'s own existence-check-before-insert)."""
    existing = conn.execute(
        select(progress_badges.c.id).where(
            progress_badges.c.profile_id == profile_id,
            progress_badges.c.badge_key == badge_key,
        )
    ).first()
    if existing is not None:
        return False
    conn.execute(
        progress_badges.insert().values(
            id=new_id(),
            profile_id=profile_id,
            badge_key=badge_key,
            earned_at=now_iso,
        )
    )
    return True


def maybe_award_badges(
    conn: Any, now_iso: str, session_id: str, profile_id: str, mode: str
) -> list[str]:
    """Checks all three badges' conditions and writes any newly-true one's
    `progress_badges` row, returning the `badge_key`s newly earned by THIS call (`[]` if
    none). A no-op entirely when `mode` never checks (`BADGE_CHECK_MODES`) -- matches
    `maybe_award_stars()`'s own mode-gate posture; a `replay` Session never reaches a
    real check. `session_id` is accepted (matching this story's frozen Boundaries
    signature) but not otherwise used here -- every badge's own condition is
    Profile-wide, never Session-scoped."""
    if mode not in BADGE_CHECK_MODES:
        return []
    today = _today_from_iso(now_iso)
    newly: list[str] = []
    if _check_week1(conn, profile_id) and _award_if_new(conn, now_iso, profile_id, "week1"):
        newly.append("week1")
    if _check_streak7(conn, profile_id, today) and _award_if_new(
        conn, now_iso, profile_id, "streak7"
    ):
        newly.append("streak7")
    if _check_stars100(conn, profile_id) and _award_if_new(
        conn, now_iso, profile_id, "stars100"
    ):
        newly.append("stars100")
    return newly


def recent_badges(conn: Any, profile_id: str, limit: int = 3) -> list[str]:
    """The Profile's latest `limit` earned `badge_key`s by `earned_at` DESC (`id` DESC breaks
    ties) -- `GET /library/home/{profile_id}`'s `recent_badges`."""
    rows = conn.execute(
        select(progress_badges.c.badge_key)
        .where(progress_badges.c.profile_id == profile_id)
        .order_by(progress_badges.c.earned_at.desc(), progress_badges.c.id.desc())
        .limit(limit)
    )
    return [row.badge_key for row in rows]


@dataclass(frozen=True)
class BadgeState:
    badge_key: str
    earned: bool
    earned_at: str | None


def profile_badges(conn: Any, profile_id: str) -> list[BadgeState]:
    """All 3 fixed badges, in `BADGE_KEYS` order, each with whether/when this Profile
    earned it -- the "Huy hiệu của em" screen's full state (unearned ones render greyed
    out, per this story's frozen Boundaries)."""
    earned_at_by_key = {
        row.badge_key: row.earned_at
        for row in conn.execute(
            select(progress_badges.c.badge_key, progress_badges.c.earned_at).where(
                progress_badges.c.profile_id == profile_id
            )
        )
    }
    return [
        BadgeState(
            badge_key=key,
            earned=key in earned_at_by_key,
            earned_at=earned_at_by_key.get(key),
        )
        for key in BADGE_KEYS
    ]
