"""Retry Queue rules (Story 3.3, AD-6): entry/refresh, "due" and exit.

- Entry is unchanged (any wrong Part `attempt`, or a `fallback` "chưa đúng"; never from a
  `replay` Session -- the caller gates that). `add_retry_item()` opens a row, or, when one is
  already open, refreshes its `last_wrong_at`.
- Due: an open item is due once `last_wrong_at` (Asia/Ho_Chi_Minh) falls on an earlier
  calendar date than today's.
- Exit (`maybe_resolve_retry_item()`, called after Stars/`self_marked` are written): graded
  Problem -> 2 distinct Sessions with a `progress_stars` row of 3 since the row opened;
  `fallback` -> `self_marked(correct=true)` in 2 distinct non-replay Sessions since it opened.
  `progress_stars` never has rows for `replay` Sessions, so replays cannot qualify.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import func, select

from hoctap.ids import from_iso, new_id
from hoctap.learning.models import (
    progress_events,
    progress_retry_items,
    progress_sessions,
    progress_stars,
)
from hoctap.learning.summary import LOCAL_TZ

REQUIRED_SESSIONS = 2


def _open_row(conn: Any, profile_id: str, problem_id: str) -> Any:
    return conn.execute(
        select(progress_retry_items).where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.problem_id == problem_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).first()


def add_retry_item(conn: Any, profile_id: str, problem_id: str, at_iso: str) -> None:
    """Opens the Problem's Retry Queue row, or refreshes `last_wrong_at` on the open one."""
    existing = _open_row(conn, profile_id, problem_id)
    if existing is not None:
        conn.execute(
            progress_retry_items.update()
            .where(progress_retry_items.c.id == existing.id)
            .values(last_wrong_at=at_iso)
        )
        return
    conn.execute(
        progress_retry_items.insert().values(
            id=new_id(),
            profile_id=profile_id,
            problem_id=problem_id,
            added_at=at_iso,
            resolved_at=None,
            last_wrong_at=at_iso,
        )
    )


def is_due(last_wrong_at: str | None, added_at: str, today: date) -> bool:
    return from_iso(last_wrong_at or added_at).astimezone(LOCAL_TZ).date() < today


def due_problem_ids(conn: Any, profile_id: str, today: date) -> list[str]:
    """Due open items' Problem ids, ordered by `last_wrong_at` ascending."""
    rows = conn.execute(
        select(progress_retry_items).where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).all()
    due = [r for r in rows if is_due(r.last_wrong_at, r.added_at, today)]
    due.sort(key=lambda r: (r.last_wrong_at or r.added_at, r.added_at))
    return [r.problem_id for r in due]


def _qualifying_star_sessions(conn: Any, profile_id: str, problem_id: str, since: str) -> int:
    return int(
        conn.execute(
            select(func.count(func.distinct(progress_stars.c.session_id))).where(
                progress_stars.c.profile_id == profile_id,
                progress_stars.c.problem_id == problem_id,
                progress_stars.c.stars == 3,
                progress_stars.c.awarded_at > since,
            )
        ).scalar_one()
    )


def _qualifying_self_mark_sessions(
    conn: Any, profile_id: str, problem_id: str, since: str
) -> int:
    rows = conn.execute(
        select(progress_events.c.session_id, progress_events.c.payload_json)
        .join(progress_sessions, progress_sessions.c.id == progress_events.c.session_id)
        .where(
            progress_events.c.profile_id == profile_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "self_marked",
            progress_events.c.received_at > since,
            progress_sessions.c.mode != "replay",
        )
    )
    sessions = {
        r.session_id for r in rows if json.loads(r.payload_json).get("correct") is True
    }
    return len(sessions)


def maybe_resolve_retry_item(
    conn: Any, now_iso: str, profile_id: str, problem_id: str
) -> None:
    """Resolves the open row once it has `REQUIRED_SESSIONS` qualifying Sessions."""
    row = _open_row(conn, profile_id, problem_id)
    if row is None:
        return
    # A graded Problem never has self-marks and a fallback Problem never earns 3 Stars,
    # so summing the two counts is equivalent to picking the rule by Problem type.
    count = _qualifying_star_sessions(
        conn, profile_id, problem_id, row.added_at
    ) + _qualifying_self_mark_sessions(conn, profile_id, problem_id, row.added_at)
    if count >= REQUIRED_SESSIONS:
        conn.execute(
            progress_retry_items.update()
            .where(progress_retry_items.c.id == row.id)
            .values(resolved_at=now_iso)
        )

