"""Child-facing Library aggregation (Story 2.3): Book -> Unit -> Lesson with the visible-
Problem count of each Lesson, and the "Học tiếp" Lesson resolution for a Grade.

Read-only over `content.catalog` and `content.effective`; writes nothing to any table.
`visible_to_child()` remains the single selector of what the child may see -- the counts
here are built from the same underlying data (`effective.load_effective()`'s `visible`
flag) in one query pass per Book, to avoid one `visible_to_child()` call per Lesson.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select

from hoctap.content import effective
from hoctap.content.catalog import service as catalog_service
from hoctap.content.catalog.models import content_catalog_lessons, content_catalog_units
from hoctap.content.views import ChildProblemView


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
    """visible-Problem count per (unit_key, lesson_key) of one Book, in one query pass."""
    counts: dict[tuple[str, str], int] = {}
    for state in effective.load_effective(conn, book_id=book_id, include_retired=False):
        if not state.visible:
            continue
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


def home_lesson(conn: Connection, grade: int) -> HomeLesson | None:
    """The first Lesson (Book order, then Unit `position`, then Lesson `position`) of
    `grade` with >=1 visible Problem; `None` when nothing is visible yet (honest empty
    state, e.g. a fresh install with nothing extracted)."""
    for book in grade_books(conn, grade):
        for unit in book.units:
            for lesson in unit.lessons:
                if lesson.problem_count > 0:
                    return HomeLesson(
                        book_id=book.book_id,
                        book_title_vi=book.title_vi,
                        unit_key=unit.unit_key,
                        lesson_key=lesson.lesson_key,
                        lesson_label=lesson.label,
                        lesson_title=lesson.title,
                    )
    return None


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
