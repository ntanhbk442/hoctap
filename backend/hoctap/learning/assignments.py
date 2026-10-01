"""Assignments (Story 4.3, FR-20): a Lesson Anh sets for a local date.

Status is derived from the linked Session(s) in `progress_sessions` (`assignment_id`), never
stored (AD-6). Only a Session started from the Assignment counts; practising the same Lesson
elsewhere leaves it open.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from hoctap.api.errors import AppError
from hoctap.content.catalog.models import (
    content_catalog_books,
    content_catalog_lessons,
    content_catalog_units,
)
from hoctap.ids import new_id, to_iso
from hoctap.learning.models import progress_assignments, progress_events, progress_sessions
from hoctap.learning.problem_sets import CHUNK_SIZE, LessonRef, ref_key, resolve
from hoctap.learning.summary import LOCAL_TZ
from hoctap.parent.models import parent_profiles

TODO, DOING, DONE = "todo", "doing", "done"


@dataclass(frozen=True)
class AssignmentInfo:
    id: str
    profile_id: str
    book_id: str
    unit_key: str
    lesson_key: str
    assigned_date: str
    status: str
    part: int | None  # 1-based chunk to resume; only when DOING
    part_count: int | None
    session_id: str | None  # the unfinished linked Session; only when DOING
    carried_over: bool
    book_title_vi: str
    unit_label: str
    lesson_label: str
    lesson_title: str
    # Orchestrator's Independent Audit (spec-4-3 #1, 2026-10-01): whether the Assignment's
    # Lesson still `resolve()`s to at least one visible Problem RIGHT NOW. A Problem can be
    # hidden/retired/error-reported after the Assignment was created (a late parent hide, a
    # content error, a re-publish that drops it) -- `home_assignment()` must never hand the
    # child a dead Assignment that would 422 `EMPTY_PROBLEM_SET` at `start_session()` time,
    # so it skips any not-done row with `resolvable=False` instead of returning it. The
    # Dashboard still lists it (via `list_for_profile()`) with `resolvable=False` so Anh can
    # see it needs attention (delete it, or fix/unhide the content) instead of the queue
    # jamming silently forever.
    resolvable: bool = True


def local_today(now: datetime) -> date:
    return now.astimezone(LOCAL_TZ).date()


def _profile_exists(conn: Any, profile_id: str) -> None:
    found = conn.execute(
        select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
    ).scalar_one_or_none()
    if found is None:
        raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")


def create(
    conn: Any, now: datetime, profile_id: str, ref: LessonRef, assigned_date: date
) -> AssignmentInfo:
    _profile_exists(conn, profile_id)
    if assigned_date < local_today(now):
        raise AppError(422, "DATE_IN_PAST", "Ngày giao bài không được ở trong quá khứ.")
    if not resolve(conn, ref, profile_id, now=now):
        raise AppError(422, "EMPTY_PROBLEM_SET", "Bài học này chưa có bài tập nào để giao.")
    assignment_id = new_id()
    conn.execute(
        progress_assignments.insert().values(
            id=assignment_id,
            profile_id=profile_id,
            ref_kind=ref.kind,
            ref_key=ref_key(ref),
            book_id=ref.book_id,
            unit_key=ref.unit_key,
            lesson_key=ref.lesson_key,
            assigned_date=assigned_date.isoformat(),
            created_at=to_iso(now),
            deleted_at=None,
        )
    )
    row = _load_row(conn, assignment_id)
    return _info(conn, row, local_today(now))


def _load_row(conn: Any, assignment_id: str) -> Any:
    row = conn.execute(
        select(progress_assignments).where(
            progress_assignments.c.id == assignment_id,
            progress_assignments.c.deleted_at.is_(None),
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "ASSIGNMENT_NOT_FOUND", "Không tìm thấy bài được giao.")
    return row


def _linked_sessions(conn: Any, assignment_id: str) -> list[Any]:
    return list(
        conn.execute(
            select(progress_sessions)
            .where(progress_sessions.c.assignment_id == assignment_id)
            .order_by(progress_sessions.c.started_at.desc(), progress_sessions.c.id.desc())
        )
    )


def _part(conn: Any, session: Any) -> tuple[int, int]:
    problem_ids: list[str] = json.loads(session.problem_ids_json)
    part_count = max(1, math.ceil(len(problem_ids) / CHUNK_SIZE))
    attempted = {
        r.problem_id
        for r in conn.execute(
            select(progress_events.c.problem_id)
            .where(
                progress_events.c.session_id == session.id,
                progress_events.c.kind == "attempt",
            )
            .distinct()
        )
    }
    for index, pid in enumerate(problem_ids):
        if pid not in attempted:
            return index // CHUNK_SIZE + 1, part_count
    return part_count, part_count


def status(conn: Any, row: Any) -> tuple[str, int | None, int | None, str | None]:
    """(status, part, part_count, unfinished linked session id) of one Assignment row."""
    sessions = _linked_sessions(conn, row.id)
    if not sessions:
        return TODO, None, None, None
    if any(s.completed_at is not None for s in sessions):
        return DONE, None, None, None
    latest = sessions[0]
    part, part_count = _part(conn, latest)
    return DOING, part, part_count, latest.id


def _lesson_labels(conn: Any, row: Any) -> tuple[str, str, str, str]:
    book = conn.execute(
        select(content_catalog_books.c.title_vi).where(
            content_catalog_books.c.book_id == row.book_id
        )
    ).scalar_one_or_none()
    unit = conn.execute(
        select(content_catalog_units.c.label).where(
            content_catalog_units.c.book_id == row.book_id,
            content_catalog_units.c.unit_key == row.unit_key,
        )
    ).scalar_one_or_none()
    lesson = conn.execute(
        select(content_catalog_lessons.c.label, content_catalog_lessons.c.title).where(
            content_catalog_lessons.c.book_id == row.book_id,
            content_catalog_lessons.c.unit_key == row.unit_key,
            content_catalog_lessons.c.lesson_key == row.lesson_key,
        )
    ).one_or_none()
    return (
        book or row.book_id,
        unit or "",
        lesson.label if lesson else row.lesson_key,
        lesson.title if lesson else "",
    )


def _resolvable(conn: Any, row: Any) -> bool:
    """Whether `row`'s Lesson still resolves to at least one visible Problem right now
    (spec-4-3 orchestrator audit #1). Uses the same `resolve()` a Session start would, so
    this can never disagree with what `start_session()` is about to do."""
    ref = LessonRef(book_id=row.book_id, unit_key=row.unit_key, lesson_key=row.lesson_key)
    return bool(resolve(conn, ref, row.profile_id))


def _info(conn: Any, row: Any, today: date) -> AssignmentInfo:
    st, part, part_count, session_id = status(conn, row)
    book, unit, label, title = _lesson_labels(conn, row)
    return AssignmentInfo(
        id=row.id,
        profile_id=row.profile_id,
        book_id=row.book_id,
        unit_key=row.unit_key,
        lesson_key=row.lesson_key,
        assigned_date=row.assigned_date,
        status=st,
        part=part,
        part_count=part_count,
        session_id=session_id,
        carried_over=st != DONE and row.assigned_date < today.isoformat(),
        book_title_vi=book,
        unit_label=unit,
        lesson_label=label,
        lesson_title=title,
        # Done Assignments don't need re-checking (nothing will ever try to start them
        # again), and skipping the check keeps the common, already-finished case cheap.
        resolvable=True if st == DONE else _resolvable(conn, row),
    )


def list_for_profile(conn: Any, profile_id: str, today: date) -> list[AssignmentInfo]:
    rows = conn.execute(
        select(progress_assignments)
        .where(
            progress_assignments.c.profile_id == profile_id,
            progress_assignments.c.deleted_at.is_(None),
        )
        .order_by(progress_assignments.c.assigned_date.desc(), progress_assignments.c.id.desc())
    )
    return [_info(conn, r, today) for r in rows]


def delete(conn: Any, now: datetime, assignment_id: str) -> None:
    row = _load_row(conn, assignment_id)
    if status(conn, row)[0] == DONE:
        raise AppError(409, "ASSIGNMENT_DONE", "Bài đã xong, không thể xóa.")
    conn.execute(
        progress_assignments.update()
        .where(progress_assignments.c.id == assignment_id)
        .values(deleted_at=to_iso(now))
    )


def home_assignment(conn: Any, profile_id: str, today: date) -> AssignmentInfo | None:
    """The oldest not-done Assignment dated today or earlier (ties: created first)."""
    rows = conn.execute(
        select(progress_assignments)
        .where(
            progress_assignments.c.profile_id == profile_id,
            progress_assignments.c.deleted_at.is_(None),
            progress_assignments.c.assigned_date <= today.isoformat(),
        )
        .order_by(progress_assignments.c.assigned_date, progress_assignments.c.id)
    )
    for row in rows:
        if status(conn, row)[0] != DONE and _resolvable(conn, row):
            return _info(conn, row, today)
    return None


def check_startable(conn: Any, assignment_id: str, profile_id: str, ref: LessonRef) -> None:
    """Validation for `start_session(assignment_id=...)`: it must exist, belong to the
    Profile, be for this Lesson, and not be done."""
    row = conn.execute(
        select(progress_assignments).where(
            progress_assignments.c.id == assignment_id,
            progress_assignments.c.deleted_at.is_(None),
        )
    ).one_or_none()
    if row is None or row.profile_id != profile_id:
        raise AppError(404, "ASSIGNMENT_NOT_FOUND", "Không tìm thấy bài được giao.")
    if (row.book_id, row.unit_key, row.lesson_key) != (
        ref.book_id,
        ref.unit_key,
        ref.lesson_key,
    ):
        raise AppError(422, "ASSIGNMENT_REF_MISMATCH", "Bài học không khớp với bài được giao.")
    if status(conn, row)[0] == DONE:
        raise AppError(409, "ASSIGNMENT_DONE", "Bài này đã xong.")
