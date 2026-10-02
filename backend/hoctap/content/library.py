"""Child-facing Library aggregation (Story 2.3): Book -> Unit -> Lesson with the visible-
Problem count of each Lesson, and the "Học tiếp" Lesson resolution for a Grade.

Read-only over `content.catalog` and `content.effective`; writes nothing to any table.
`visible_to_child()` remains the single selector of what the child may see -- the counts
here are built from the same underlying data (`effective.load_effective()`'s `visible`
flag) in one query pass per Book, to avoid one `visible_to_child()` call per Lesson.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, select

from hoctap.content import effective
from hoctap.content.catalog import service as catalog_service
from hoctap.content.catalog.models import (
    content_catalog_lessons,
    content_catalog_problems,
    content_catalog_units,
)
from hoctap.content.review.models import (
    content_review_error_reports,
    content_review_overrides,
    content_review_status,
)
from hoctap.content.views import ChildProblemView


def _chunks(ids: Sequence[str], size: int = 500) -> list[Sequence[str]]:
    return [ids[i : i + size] for i in range(0, len(ids), size)]


@dataclass(frozen=True)
class LessonCount:
    lesson_key: str
    label: str
    title: str
    position: int
    problem_count: int  # visible to the child; always the honest count (Story 2.4 tracks progress)
    is_quiz_sheet: bool = False  # Story 3.4: the weekly "Phiếu tự luyện cuối tuần"


@dataclass(frozen=True)
class UnitGroup:
    unit_key: str
    label: str
    title: str
    position: int
    lessons: list[LessonCount]


@dataclass(frozen=True)
class BookGroup:
    book_id: str
    edition: str
    grade: int
    volume: int
    title_vi: str
    units: list[UnitGroup]


def _visible_counts(conn: Connection, book_id: str) -> dict[tuple[str, str], int]:
    """visible-Problem count per (unit_key, lesson_key) of one Book.

    Performance fix (2026-10-02): this used to run EVERY Problem of the Book through
    `effective.load_effective()` -- a full merge, Pydantic validation and content-hash
    computation per Problem -- just to count how many are visible. With a real, full-size
    catalogue (hundreds of Problems per Book) that made the Library screen (a core,
    frequently-opened child surface) take several seconds to load.

    `EffectiveProblem.visible` is `not retired and doc is not None and not hidden and not
    open_reports['parent'] and not has_conflict and not awaiting_approval`. For a Problem
    with NO override and `needs_review=False`: `has_conflict` is always False (`merge()`
    only ever produces a conflict from an override) and `awaiting_approval` is always
    False (it's gated on `needs_review` first) -- so `visible` reduces to the three cheap,
    already-fetched columns (`retired_at`, `hidden`, open `parent` report), with no need
    to touch `doc_json`/overrides/validation at all. Only Problems that DO have an
    override or ARE `needs_review` still need the real, slow `load_effective()` check (a
    small minority -- the rest of this catalogue's correctness guarantees are completely
    unchanged for that subset, and every OTHER consumer of `effective.py` is untouched by
    this function's own internals).
    """
    t = content_catalog_problems
    rows = conn.execute(
        select(t.c.problem_id, t.c.unit_key, t.c.lesson_key, t.c.needs_review)
        .where(t.c.book_id == book_id, t.c.retired_at.is_(None))
        .order_by(t.c.problem_id)
    ).all()
    if not rows:
        return {}
    ids = [r.problem_id for r in rows]

    s, er, ov = content_review_status, content_review_error_reports, content_review_overrides
    hidden_ids: set[str] = set()
    for chunk in _chunks(ids):
        hidden_ids |= {
            row.problem_id
            for row in conn.execute(
                select(s.c.problem_id).where(s.c.problem_id.in_(chunk), s.c.hidden == 1)
            )
        }
    open_parent_report_ids: set[str] = set()
    for chunk in _chunks(ids):
        open_parent_report_ids |= {
            row.problem_id
            for row in conn.execute(
                select(er.c.problem_id).where(
                    er.c.problem_id.in_(chunk), er.c.kind == "parent", er.c.status == "open"
                )
            )
        }
    override_ids: set[str] = set()
    for chunk in _chunks(ids):
        override_ids |= {
            row.problem_id
            for row in conn.execute(
                select(ov.c.problem_id).where(ov.c.problem_id.in_(chunk)).distinct()
            )
        }

    counts: dict[tuple[str, str], int] = {}
    needs_slow_check: list[Any] = []
    for row in rows:
        if row.problem_id in hidden_ids or row.problem_id in open_parent_report_ids:
            continue
        if row.needs_review or row.problem_id in override_ids:
            needs_slow_check.append(row)
            continue
        key = (row.unit_key, row.lesson_key)
        counts[key] = counts.get(key, 0) + 1

    if needs_slow_check:
        slow_ids = [r.problem_id for r in needs_slow_check]
        for state in effective.load_effective(conn, problem_ids=slow_ids):
            if state.visible:
                key = (state.unit_key, state.lesson_key)
                counts[key] = counts.get(key, 0) + 1
    return counts


def grade_books(conn: Connection, grade: int) -> list[BookGroup]:
    """Every Book of `grade` (both Editions), Book order matching the catalogue's own
    order (`catalog.service.list_books()`: edition, then grade, then volume); each Unit and
    Lesson in `position` order; each Lesson's visible-Problem count."""
    books = [b for b in catalog_service.list_books(conn) if b.grade == grade]
    out: list[BookGroup] = []
    for book in books:
        counts = _visible_counts(conn, book.book_id)
        units_rows = conn.execute(
            select(content_catalog_units)
            .where(content_catalog_units.c.book_id == book.book_id)
            .order_by(content_catalog_units.c.position)
        ).all()
        lessons_rows = conn.execute(
            select(content_catalog_lessons)
            .where(content_catalog_lessons.c.book_id == book.book_id)
            .order_by(content_catalog_lessons.c.position)
        ).all()
        by_unit: dict[str, list[LessonCount]] = {}
        for row in lessons_rows:
            by_unit.setdefault(row.unit_key, []).append(
                LessonCount(
                    lesson_key=row.lesson_key,
                    label=row.label,
                    title=row.title,
                    position=row.position,
                    problem_count=counts.get((row.unit_key, row.lesson_key), 0),
                    is_quiz_sheet=bool(row.is_quiz_sheet),
                )
            )
        units = [
            UnitGroup(
                unit_key=row.unit_key,
                label=row.label,
                title=row.title,
                position=row.position,
                lessons=by_unit.get(row.unit_key, []),
            )
            for row in units_rows
        ]
        out.append(
            BookGroup(
                book_id=book.book_id,
                edition=book.edition,
                grade=book.grade,
                volume=book.volume,
                title_vi=book.title_vi,
                units=units,
            )
        )
    return out


@dataclass(frozen=True)
class HomeLesson:
    book_id: str
    book_title_vi: str
    unit_key: str
    lesson_key: str
    lesson_label: str
    lesson_title: str


def home_lesson(
    conn: Connection,
    grade: int,
    attempted_counts: Callable[[str], dict[tuple[str, str], int]] | None = None,
) -> HomeLesson | None:
    """The "Học tiếp" Lesson of `grade`: the first Lesson (Book order, then Unit `position`,
    then Lesson `position`) with a visible Problem the Profile has not attempted yet;
    falling back to the first Lesson with >=1 visible Problem when everything is attempted;
    `None` when nothing is visible yet (honest empty state, e.g. a fresh install).

    `attempted_counts(book_id)` returns the Profile's attempted-and-visible Problem count
    per (unit_key, lesson_key) -- injected by the caller (`learning.progress`) so this
    module never imports `learning`. Omitted, no progress is known and the first Lesson
    with a visible Problem wins."""
    first: HomeLesson | None = None
    for book in grade_books(conn, grade):
        attempted = attempted_counts(book.book_id) if attempted_counts else {}
        for unit in book.units:
            for lesson in unit.lessons:
                if lesson.problem_count <= 0:
                    continue
                candidate = HomeLesson(
                    book_id=book.book_id,
                    book_title_vi=book.title_vi,
                    unit_key=unit.unit_key,
                    lesson_key=lesson.lesson_key,
                    lesson_label=lesson.label,
                    lesson_title=lesson.title,
                )
                if attempted.get((unit.unit_key, lesson.lesson_key), 0) < lesson.problem_count:
                    return candidate
                if first is None:
                    first = candidate
    return first


def lesson_problems(
    conn: Connection, book_id: str, unit_key: str, lesson_key: str
) -> list[ChildProblemView]:
    """The visible Problems of one Lesson, `child_view()` shape -- delegates directly to
    `visible_to_child()`, no new Problem projection."""
    return effective.visible_to_child(
        conn, book_id=book_id, unit_key=unit_key, lesson_key=lesson_key
    )


def lesson_is_quiz_sheet(conn: Connection, book_id: str, unit_key: str, lesson_key: str) -> bool:
    """Story 3.4: whether one Lesson is a quiz sheet (`content_catalog_lessons.is_quiz_sheet`).
    An unknown Lesson is simply not a quiz sheet."""
    value = conn.execute(
        select(content_catalog_lessons.c.is_quiz_sheet).where(
            content_catalog_lessons.c.book_id == book_id,
            content_catalog_lessons.c.unit_key == unit_key,
            content_catalog_lessons.c.lesson_key == lesson_key,
        )
    ).scalar_one_or_none()
    return bool(value)
