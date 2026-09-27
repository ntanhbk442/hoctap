"""Shared helpers for runtime rows: UUIDv7 ids and UTC timestamps."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def new_id() -> str:
    """A UUIDv7 as text (time-ordered)."""
    return str(uuid.uuid7())


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """UTC ISO-8601 text as stored in the database."""
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def from_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
