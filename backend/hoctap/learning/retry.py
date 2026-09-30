"""Retry Queue rules (Story 3.3, AD-6): entry/refresh, "due" and exit.

- Entry is unchanged (any wrong Part `attempt`, or a `fallback` "chưa đúng"; never from a
  `replay` Session -- the caller gates that). `add_retry_item()` opens a row, or, when one is
  already open, refreshes its `last_wrong_at`.
- Clock: `added_at`/`last_wrong_at` are the DEVICE time (`occurred_at`) of the wrong event,
  normalised to UTC ISO by the caller. Every "since" comparison below uses the DEVICE time
  of the qualifying event too (never the server `received_at`/`awarded_at`), so both sides
  of each comparison come from the same clock.
- Due: an open item is due once `last_wrong_at` (Asia/Ho_Chi_Minh) falls on an earlier
  calendar date than today's.
- Exit (`maybe_resolve_retry_item()`, called after Stars/`self_marked` are written): graded
  Problem -> 2 distinct Sessions with a `progress_stars` row of 3; `fallback` ->
  `self_marked(correct=true)` in 2 distinct non-replay Sessions; a correct quiz Session
  (see `_qualifying_sessions()`) counts too. Only events at or after
  `max(added_at, last_wrong_at)` count, so a repeat wrong attempt resets progress.
  `progress_stars` never has rows for `replay` Sessions, so replays cannot qualify.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from hoctap.content.effective import visible_to_child
from hoctap.ids import from_iso, new_id, to_iso
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


def device_time_iso(occurred_at: str, fallback_iso: str) -> str:
    """The event's device `occurred_at` as UTC ISO text (the same `to_iso` form as every
    other stored timestamp); the server `fallback_iso` if it does not parse."""
    try:
        return to_iso(from_iso(occurred_at))
    except ValueError:
        return fallback_iso


def add_retry_item(conn: Any, profile_id: str, problem_id: str, at_iso: str) -> None:
    """Opens the Problem's Retry Queue row, or refreshes `last_wrong_at` on the open one."""
    existing = _open_row(conn, profile_id, problem_id)
    if existing is not None:
        # Device clocks can deliver events out of order (offline outbox): never move back.
        newest = max(from_iso(at_iso), from_iso(existing.last_wrong_at or existing.added_at))
        conn.execute(
            progress_retry_items.update()
            .where(progress_retry_items.c.id == existing.id)
            .values(last_wrong_at=to_iso(newest))
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
    """Due open items' Problem ids, ordered by `last_wrong_at` ascending. Problems the child
    can no longer see (hidden, parent-reported, retired) are neither counted nor served."""
    rows = conn.execute(
        select(progress_retry_items).where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).all()
    due = [r for r in rows if is_due(r.last_wrong_at, r.added_at, today)]
    due.sort(key=lambda r: (r.last_wrong_at or r.added_at, r.added_at))
    if not due:
        return []
    visible = {v.problem_id for v in visible_to_child(conn, [r.problem_id for r in due])}
    return [r.problem_id for r in due if r.problem_id in visible]


def _qualifying_sessions(conn: Any, profile_id: str, problem_id: str, since: datetime) -> int:
    """Distinct Sessions that count towards exit, using each Session's DEVICE time for this
    Problem (its latest `attempt`/`self_marked` `occurred_at`, or the `quiz_submitted`
    `occurred_at` for a quiz) against `since`. Three sources, unioned by Session id so a
    Session is never counted twice:
    - a `progress_stars` row of 3 (practice/retry/first-time quiz);
    - a correct `self_marked` in a non-replay Session (fallback Problems);
    - a quiz Session whose stored `quiz_submitted` result marks the Problem correct. This is
      what lets a quiz RETAKE count (it writes no `progress_stars` row, by design)."""
    qualifying: set[str] = set()
    star_sessions = {
        r.session_id
        for r in conn.execute(
            select(progress_stars.c.session_id).where(
                progress_stars.c.profile_id == profile_id,
                progress_stars.c.problem_id == problem_id,
                progress_stars.c.stars == 3,
            )
        )
    }
    latest: dict[str, datetime] = {}
    rows = conn.execute(
        select(
            progress_events.c.session_id,
            progress_events.c.kind,
            progress_events.c.payload_json,
            progress_events.c.occurred_at,
            progress_sessions.c.mode,
        )
        .join(progress_sessions, progress_sessions.c.id == progress_events.c.session_id)
        .where(
            progress_events.c.profile_id == profile_id,
            progress_events.c.kind.in_(("attempt", "self_marked", "quiz_submitted")),
            progress_sessions.c.mode != "replay",
            (progress_events.c.problem_id == problem_id)
            | (progress_events.c.kind == "quiz_submitted"),
        )
    )
    for r in rows:
        try:
            at = from_iso(r.occurred_at)
        except ValueError:
            continue
        if r.kind == "attempt":
            if r.session_id in star_sessions:
                latest[r.session_id] = max(at, latest.get(r.session_id, at))
        elif r.kind == "self_marked":
            if json.loads(r.payload_json).get("correct") is True and at >= since:
                qualifying.add(r.session_id)
        else:
            results = json.loads(r.payload_json).get("results") or []
            if any(x.get("problem_id") == problem_id and x.get("correct") is True for x in results):
                if at >= since:
                    qualifying.add(r.session_id)
    qualifying.update(sid for sid, at in latest.items() if at >= since)
    return len(qualifying)


def maybe_resolve_retry_item(
    conn: Any, now_iso: str, profile_id: str, problem_id: str
) -> None:
    """Resolves the open row once it has `REQUIRED_SESSIONS` qualifying Sessions since the
    latest wrong attempt (`max(added_at, last_wrong_at)`)."""
    row = _open_row(conn, profile_id, problem_id)
    if row is None:
        return
    since = max(from_iso(row.added_at), from_iso(row.last_wrong_at or row.added_at))
    if _qualifying_sessions(conn, profile_id, problem_id, since) >= REQUIRED_SESSIONS:
        conn.execute(
            progress_retry_items.update()
            .where(progress_retry_items.c.id == row.id)
            .values(resolved_at=now_iso)
        )
