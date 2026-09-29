"""Child Library (`GET /library/*`): Book -> Unit -> Lesson with visible-Problem counts,
one Lesson's visible Problems, and the "Học tiếp" resolution -- all read-only, no PIN or
parent gate (child-facing, same trust level as `/profiles`, AD-5/FR-7/FR-8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Engine, select

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content import library
from hoctap.content.views import ChildProblemView
from hoctap.learning import progress as learning_progress
from hoctap.learning import scoring as learning_scoring
from hoctap.learning import sessions as learning_sessions
from hoctap.learning.summary import LOCAL_TZ, compute_streak
from hoctap.parent.models import parent_profiles

router = APIRouter(prefix="/library", tags=["library"])

EngineDep = Annotated[Engine, Depends(get_engine)]
NowDep = Annotated[datetime, Depends(get_now)]


class LibraryLesson(BaseModel):
    lesson_key: str
    label: str
    title: str
    position: int
    problem_count: int
    # Story 2.4: the real "attempted at least once" numerator (see `learning.progress`),
    # honest -- not "correct" (no grader exists yet). 0 when `profile_id` isn't given.
    attempted: int = 0


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


def _book_out(book: library.BookGroup, attempted: dict[tuple[str, str], int]) -> LibraryBook:
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
                        attempted=attempted.get((u.unit_key, lc.lesson_key), 0),
                    )
                    for lc in u.lessons
                ],
            )
            for u in book.units
        ],
    )


@router.get(
    "/grades/{grade}/books",
    response_model=list[LibraryBook],
    operation_id="list_library_books",
    responses={404: {"model": ErrorResponse, "description": "Unknown profile"}},
)
def get_grade_books(
    grade: int, engine: EngineDep, profile_id: Annotated[str | None, Query()] = None
) -> list[LibraryBook]:
    """`profile_id` is optional: omitted, every Lesson's `attempted` is honestly 0 (no
    Profile to count for); given, `attempted` is the real "done at least once" numerator
    (Story 2.4, `learning.progress`) -- never "correct", no grader exists yet. An unknown
    `profile_id` 404s (matching `/library/home/{profile_id}`'s own convention) rather than
    silently returning a real book/lesson tree with an all-zero `attempted` column."""
    with engine.connect() as conn:
        if profile_id is not None:
            exists = conn.execute(
                select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
            ).scalar_one_or_none()
            if exists is None:
                raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        books = library.grade_books(conn, grade)
        return [
            _book_out(
                b,
                learning_progress.attempted_lesson_counts(conn, b.book_id, profile_id)
                if profile_id
                else {},
            )
            for b in books
        ]


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


class ContinueSessionOut(BaseModel):
    """Story 2.11's "Tiếp tục" card: just enough to resume -- the Session id. Its frozen
    `problem_ids_json`/chunk state live entirely server-side (Story 2.4's AD-9), so
    "resuming" is simply navigating to the existing `SessionPlayer` route for this id; no
    other field is needed."""

    session_id: str


class LibraryHomeOut(BaseModel):
    profile_id: str
    grade: int
    lesson: HomeLessonOut | None = None
    # Story 2.11: the most recent unfinished (non-replay) Session for this Profile, if any.
    continue_session: ContinueSessionOut | None = None
    # Story 3.1: the Profile's all-time total Stars (`SUM` over `progress_stars`) and
    # current Streak (`compute_streak()`, unchanged from Story 2.10 -- surfaced here, not
    # recomputed) -- Home's persistent Star total + Streak display.
    total_stars: int = 0
    streak: int = 0


@router.get(
    "/home/{profile_id}",
    response_model=LibraryHomeOut,
    operation_id="get_library_home",
    responses={404: {"model": ErrorResponse, "description": "Unknown profile"}},
)
def get_home(profile_id: str, engine: EngineDep, now: NowDep) -> LibraryHomeOut:
    with engine.connect() as conn:
        grade = conn.execute(
            select(parent_profiles.c.grade).where(parent_profiles.c.id == profile_id)
        ).scalar_one_or_none()
        if grade is None:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        lesson = library.home_lesson(conn, grade)
        unfinished = learning_sessions.find_unfinished_session(conn, profile_id)
        today = now.astimezone(LOCAL_TZ).date()
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
            continue_session=None
            if unfinished is None
            else ContinueSessionOut(session_id=unfinished.id),
            total_stars=learning_scoring.total_stars(conn, profile_id),
            streak=compute_streak(conn, profile_id, today),
        )
