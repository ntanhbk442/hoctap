"""Child Library (`GET /library/*`): Book -> Unit -> Lesson with visible-Problem counts,
one Lesson's visible Problems, and the "Học tiếp" resolution -- all read-only, no PIN or
parent gate (child-facing, same trust level as `/profiles`, AD-5/FR-7/FR-8).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, select

from hoctap.api.deps import get_engine
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content import library
from hoctap.content.views import ChildProblemView
from hoctap.parent.models import parent_profiles

router = APIRouter(prefix="/library", tags=["library"])

EngineDep = Annotated[Engine, Depends(get_engine)]


class LibraryLesson(BaseModel):
    lesson_key: str
    label: str
    title: str
    position: int
    problem_count: int


class LibraryUnit(BaseModel):
    unit_key: str
    label: str
    title: str
    position: int
    lessons: list[LibraryLesson]


class LibraryBook(BaseModel):
    book_id: str
    edition: str
    grade: int
    volume: int
    title_vi: str
    units: list[LibraryUnit]


def _book_out(book: library.BookGroup) -> LibraryBook:
    return LibraryBook(
        book_id=book.book_id,
        edition=book.edition,
        grade=book.grade,
        volume=book.volume,
        title_vi=book.title_vi,
        units=[
            LibraryUnit(
                unit_key=u.unit_key,
                label=u.label,
                title=u.title,
                position=u.position,
                lessons=[
                    LibraryLesson(
                        lesson_key=lc.lesson_key,
                        label=lc.label,
                        title=lc.title,
                        position=lc.position,
                        problem_count=lc.problem_count,
                    )
                    for lc in u.lessons
                ],
            )
            for u in book.units
        ],
    )


@router.get(
    "/grades/{grade}/books", response_model=list[LibraryBook], operation_id="list_library_books"
)
def get_grade_books(grade: int, engine: EngineDep) -> list[LibraryBook]:
    with engine.connect() as conn:
        return [_book_out(b) for b in library.grade_books(conn, grade)]


@router.get(
    "/lessons/{book_id}/{unit_key}/{lesson_key}",
    response_model=list[ChildProblemView],
    operation_id="get_library_lesson_problems",
)
def get_lesson_problems(
    book_id: str, unit_key: str, lesson_key: str, engine: EngineDep
) -> list[ChildProblemView]:
    """Intentionally always 200: `[]` covers both "this Book/Unit/Lesson doesn't exist" and
    "it exists but has no visible Problems" -- both are the same "nothing to show" answer to
    the child, and `visible_to_child()`'s filter can't (and shouldn't) distinguish an unknown
    key from a real one with zero matches. Not an oversight; no 404 is used here."""
    with engine.connect() as conn:
        return library.lesson_problems(conn, book_id, unit_key, lesson_key)


class HomeLessonOut(BaseModel):
    book_id: str
    book_title_vi: str
    unit_key: str
    lesson_key: str
    lesson_label: str
    lesson_title: str


class LibraryHomeOut(BaseModel):
    profile_id: str
    grade: int
    lesson: HomeLessonOut | None = None


@router.get(
    "/home/{profile_id}",
    response_model=LibraryHomeOut,
    operation_id="get_library_home",
    responses={404: {"model": ErrorResponse, "description": "Unknown profile"}},
)
def get_home(profile_id: str, engine: EngineDep) -> LibraryHomeOut:
    with engine.connect() as conn:
        grade = conn.execute(
            select(parent_profiles.c.grade).where(parent_profiles.c.id == profile_id)
        ).scalar_one_or_none()
        if grade is None:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        lesson = library.home_lesson(conn, grade)
        return LibraryHomeOut(
            profile_id=profile_id,
            grade=grade,
            lesson=None
            if lesson is None
            else HomeLessonOut(
                book_id=lesson.book_id,
                book_title_vi=lesson.book_title_vi,
                unit_key=lesson.unit_key,
                lesson_key=lesson.lesson_key,
                lesson_label=lesson.lesson_label,
                lesson_title=lesson.lesson_title,
            ),
        )
