"""Child Library (`GET /library/*`): Book -> Unit -> Lesson with visible-Problem counts,
one Lesson's visible Problems, and the "Học tiếp" resolution -- all read-only, no PIN or
parent gate (child-facing, same trust level as `/profiles`, AD-5/FR-7/FR-8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Connection, Engine, select

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content import effective, library
from hoctap.content.review.models import content_review_concepts, content_review_problem_concepts
from hoctap.content.schema import ConceptGuideDoc
from hoctap.content.views import ChildProblemView
from hoctap.learning import assignments as learning_assignments
from hoctap.learning import badges as learning_badges
from hoctap.learning import progress as learning_progress
from hoctap.learning import retry as learning_retry
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
    # Story 3.4: the weekly "Phiếu tự luyện cuối tuần" -- always starts as a `quiz` Session.
    is_quiz_sheet: bool = False


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
                        is_quiz_sheet=lc.is_quiz_sheet,
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


class HomeAssignmentOut(BaseModel):
    """Story 4.3's "Bài hôm nay" card. `session_id` is the unfinished linked Session to
    resume (set only while `status == "doing"`); otherwise the card starts one from the
    Lesson (or, Story 8.1, the exam), linked by `id`.

    `ref_kind == "exam"`: `book_id`/`unit_key`/`lesson_key`/`book_title_vi`/`unit_label`/
    `lesson_label`/`lesson_title` are all empty strings (there IS no Lesson); the child
    instead reads `exam_scope`/`exam_count`/`exam_time_limit_s` and echoes them straight
    back as `POST /sessions`' `ExamRefIn` (plus `assignment_id=id`) to start it."""

    id: str
    ref_kind: str = "lesson"
    book_id: str
    book_title_vi: str
    unit_key: str
    lesson_key: str
    lesson_label: str
    lesson_title: str
    assigned_date: str
    status: str
    part: int | None = None
    part_count: int | None = None
    session_id: str | None = None
    carried_over: bool = False
    exam_scope: dict[str, object] | None = None
    exam_count: int | None = None
    exam_time_limit_s: int | None = None


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
    # Story 3.2: the Profile's latest 3 earned `badge_key`s by `earned_at` DESC --
    # Home's latest-3 badges row.
    recent_badges: list[str] = []
    # Story 3.3: number of DUE Retry Queue Problems (last wrong Attempt on an earlier local
    # calendar day). Home shows the "Luyện lại" card only when > 0.
    retry_due_count: int = 0
    # Story 4.3: the one "Bài hôm nay" card (oldest not-done Assignment due today or earlier).
    assignment: HomeAssignmentOut | None = None


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
        lesson = library.home_lesson(
            conn,
            grade,
            lambda book_id: learning_progress.attempted_lesson_counts(conn, book_id, profile_id),
        )
        unfinished = learning_sessions.find_unfinished_session(conn, profile_id)
        today = now.astimezone(LOCAL_TZ).date()
        due = learning_assignments.home_assignment(conn, profile_id, today)
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
            recent_badges=learning_badges.recent_badges(conn, profile_id),
            retry_due_count=len(learning_retry.due_problem_ids(conn, profile_id, today)),
            assignment=None
            if due is None
            else HomeAssignmentOut(
                id=due.id,
                ref_kind=due.ref_kind,
                book_id=due.book_id or "",
                book_title_vi=due.book_title_vi,
                unit_key=due.unit_key or "",
                lesson_key=due.lesson_key or "",
                lesson_label=due.lesson_label,
                lesson_title=due.lesson_title,
                assigned_date=due.assigned_date,
                status=due.status,
                part=due.part,
                part_count=due.part_count,
                session_id=due.session_id,
                carried_over=due.carried_over,
                exam_scope=due.exam_scope,
                exam_count=due.exam_count,
                exam_time_limit_s=due.exam_time_limit_s,
            ),
        )


class LibraryConcept(BaseModel):
    concept_id: str
    name_vi: str
    grade: int
    problem_count: int


class ConceptDetailOut(LibraryConcept):
    # Only an approved Guide (Story 5.1's `EffectiveGuide.approved`); null otherwise, so a
    # draft's existence is never hinted at.
    guide: ConceptGuideDoc | None = None


def _visible_concept_counts(conn: Connection, concept_ids: list[str]) -> dict[str, int]:
    if not concept_ids:
        return {}
    link = content_review_problem_concepts
    links: dict[str, list[str]] = {}
    for row in conn.execute(select(link).where(link.c.concept_id.in_(concept_ids))):
        links.setdefault(row.concept_id, []).append(row.problem_id)
    all_ids = sorted({p for ids in links.values() for p in ids})
    visible = {v.problem_id for v in effective.visible_to_child(conn, all_ids)}
    return {c: sum(1 for p in ids if p in visible) for c, ids in links.items()}


@router.get(
    "/concepts",
    response_model=list[LibraryConcept],
    operation_id="list_library_concepts",
)
def list_concepts(grade: Annotated[int, Query()], engine: EngineDep) -> list[LibraryConcept]:
    """The curated Concepts of a Grade with their visible-Problem counts (Story 5.2)."""
    c = content_review_concepts
    with engine.connect() as conn:
        rows = conn.execute(select(c).where(c.c.grade == grade).order_by(c.c.concept_id)).all()
        counts = _visible_concept_counts(conn, [r.concept_id for r in rows])
        return [
            LibraryConcept(
                concept_id=r.concept_id,
                name_vi=r.name_vi,
                grade=r.grade,
                problem_count=counts.get(r.concept_id, 0),
            )
            for r in rows
        ]


@router.get(
    "/concepts/{concept_id}",
    response_model=ConceptDetailOut,
    operation_id="get_library_concept",
    responses={404: {"model": ErrorResponse, "description": "CONCEPT_NOT_FOUND"}},
)
def get_concept(concept_id: str, engine: EngineDep) -> ConceptDetailOut:
    """One Concept and its Guide, only when approved (Story 5.2)."""
    c = content_review_concepts
    with engine.connect() as conn:
        row = conn.execute(select(c).where(c.c.concept_id == concept_id)).one_or_none()
        if row is None:
            raise AppError(404, "CONCEPT_NOT_FOUND", "Không tìm thấy khái niệm này.")
        guide = effective.effective_concept_guide(conn, concept_id)
        return ConceptDetailOut(
            concept_id=row.concept_id,
            name_vi=row.name_vi,
            grade=row.grade,
            problem_count=_visible_concept_counts(conn, [concept_id]).get(concept_id, 0),
            guide=guide.doc if guide is not None and guide.approved else None,
        )
