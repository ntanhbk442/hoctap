"""Sessions (Story 2.4): `POST /sessions`, `GET /sessions/{id}/bundle`,
`POST /sessions/{id}/events` -- child-facing, no PIN/parent gate (same trust level as
`/profiles`, `/library/*`).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content import library as content_library
from hoctap.content.schema import Solution
from hoctap.content.views import ChildProblemView
from hoctap.learning import sessions as service
from hoctap.learning.problem_sets import LessonRef, ReplayRef, RetryRef
from hoctap.learning.summary import LOCAL_TZ

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Story 2.5's `attempt` grading does several reads (the effective Problem, the Retry
# Queue, prior `attempt` events) before its write, inside the SAME transaction as Story
# 2.4's event insert (AD-6). Under SQLite's WAL mode, a transaction that read before a
# CONCURRENT writer on another connection committed cannot then be promoted to a writer
# -- `SQLITE_BUSY_SNAPSHOT` ("database is locked"), which `PRAGMA busy_timeout` does NOT
# retry (the snapshot is stale, not merely contended; waiting cannot fix it -- verified
# directly against sqlite3, see this story's Implementation Notes). The whole batch is
# re-run in a FRESH transaction (a fresh read snapshot); any event another connection
# already committed in the meantime is picked up by `post_event()`'s own idempotent
# already-stored fast path, never re-graded or double-inserted.
_LOCK_RETRY_ATTEMPTS = 10
_LOCK_RETRY_DELAY_S = 0.05

EngineDep = Annotated[Engine, Depends(get_engine)]
NowDep = Annotated[datetime, Depends(get_now)]


def _is_uuid7(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 7
    except ValueError:
        return False


class LessonRefIn(BaseModel):
    kind: Literal["lesson"] = "lesson"
    book_id: str
    unit_key: str
    lesson_key: str


class ReplayRefIn(BaseModel):
    """Story 2.10's "Luyện lại bài sai": a new Session made of one earlier ("source")
    Session's own wrong Problem ids."""

    kind: Literal["replay"] = "replay"
    source_session_id: str


class RetryRefIn(BaseModel):
    """Story 3.3: a Session of the Profile's due Retry Queue Problems. Profile-scoped, so
    no extra fields; the created Session's mode is always `"retry"`."""

    kind: Literal["retry"] = "retry"


class StartSessionIn(BaseModel):
    profile_id: str
    ref: LessonRefIn | ReplayRefIn | RetryRefIn = Field(discriminator="kind")
    # Epic 3 review: the Session mode is DERIVED from `ref.kind` on the server (lesson ->
    # practice, or quiz for a quiz-sheet Lesson; replay -> replay; retry -> retry). The field
    # stays optional for compatibility, but a value that disagrees with the derived mode is
    # rejected (422 `MODE_REF_MISMATCH`). This reverses Story 2.10's "independent field".
    mode: Literal["practice", "replay", "retry"] | None = None
    # Story 4.3: the Assignment this Session is started from (Home's "Bài hôm nay" card).
    assignment_id: str | None = None


class SessionOut(BaseModel):
    id: str
    profile_id: str
    ref_kind: str
    problem_ids: list[str]
    chunk_size: int
    mode: str
    started_at: str


def _session_out(s: service.SessionOut) -> SessionOut:
    return SessionOut(
        id=s.id,
        profile_id=s.profile_id,
        ref_kind=s.ref_kind,
        problem_ids=s.problem_ids,
        chunk_size=s.chunk_size,
        mode=s.mode,
        started_at=s.started_at,
    )


@router.post(
    "",
    response_model=SessionOut,
    status_code=201,
    operation_id="start_session",
    responses={
        404: {"model": ErrorResponse, "description": "Unknown profile or Assignment"},
        409: {"model": ErrorResponse, "description": "ASSIGNMENT_DONE"},
        422: {
            "model": ErrorResponse,
            "description": (
                "Empty Problem set, MODE_REF_MISMATCH, or (replay) an unknown/foreign/"
                "all-correct source Session"
            ),
        },
    },
)
def start_session(body: StartSessionIn, engine: EngineDep, now: NowDep) -> SessionOut:
    ref: LessonRef | ReplayRef | RetryRef
    if body.ref.kind == "retry":
        ref = RetryRef()
        mode = "retry"
    elif body.ref.kind == "lesson":
        ref = LessonRef(
            book_id=body.ref.book_id, unit_key=body.ref.unit_key, lesson_key=body.ref.lesson_key
        )
        mode = "practice"
    else:
        ref = ReplayRef(source_session_id=body.ref.source_session_id)
        mode = "replay"
    if body.mode is not None and body.mode != mode:
        raise AppError(
            422,
            "MODE_REF_MISMATCH",
            "Chế độ học không khớp với loại bài được chọn.",
        )
    with engine.begin() as conn:
        # Story 3.4: the mode of a quiz-sheet Lesson is decided here, never by the client
        # (`StartSessionIn.mode` has no `quiz` value); a client-sent "practice" is accepted.
        if isinstance(ref, LessonRef) and content_library.lesson_is_quiz_sheet(
            conn, ref.book_id, ref.unit_key, ref.lesson_key
        ):
            mode = "quiz"
        return _session_out(
            service.start_session(
                conn, now, body.profile_id, ref, mode=mode, assignment_id=body.assignment_id
            )
        )


class BundleProblemOut(BaseModel):
    problem: ChildProblemView
    crop_urls: list[str]
    page_urls: list[str]
    audio: dict[str, str]
    attempted: bool


class BundleOut(BaseModel):
    session_id: str
    # Story 3.4: the Session's server-decided mode (the player switches to quiz play).
    mode: str
    chunk: int
    chunk_count: int
    chunk_label: str
    problems: list[BundleProblemOut]


def _bundle_out(b: service.BundleOut) -> BundleOut:
    return BundleOut(
        session_id=b.session_id,
        mode=b.mode,
        chunk=b.chunk,
        chunk_count=b.chunk_count,
        chunk_label=b.chunk_label,
        problems=[
            BundleProblemOut(
                problem=p.view,
                crop_urls=p.crop_urls,
                page_urls=p.page_urls,
                audio=p.audio,
                attempted=p.attempted,
            )
            for p in b.problems
        ],
    )


@router.get(
    "/{session_id}/bundle",
    response_model=BundleOut,
    operation_id="get_session_bundle",
    responses={
        403: {"model": ErrorResponse, "description": "Profile doesn't own this Session"},
        404: {"model": ErrorResponse, "description": "Unknown Session"},
        422: {"model": ErrorResponse, "description": "Chunk out of range"},
    },
)
def get_bundle(
    session_id: str,
    profile_id: Annotated[str, Query()],
    engine: EngineDep,
    chunk: Annotated[int, Query(ge=1)] = 1,
) -> BundleOut:
    with engine.connect() as conn:
        return _bundle_out(service.get_bundle(conn, session_id, profile_id, chunk))


class SummaryOut(BaseModel):
    session_id: str
    first_try_correct: int
    total: int
    wrong_problem_ids: list[str]
    streak: int
    stars_earned: int
    new_badges: list[str]


@router.get(
    "/{session_id}/summary",
    response_model=SummaryOut,
    operation_id="get_session_summary",
    responses={
        403: {"model": ErrorResponse, "description": "Profile doesn't own this Session"},
        404: {"model": ErrorResponse, "description": "Unknown Session"},
        422: {"model": ErrorResponse, "description": "Session not yet completed"},
    },
)
def get_summary(
    session_id: str, profile_id: Annotated[str, Query()], engine: EngineDep, now: NowDep
) -> SummaryOut:
    today = now.astimezone(LOCAL_TZ).date()
    with engine.connect() as conn:
        summary = service.get_session_summary(conn, session_id, profile_id, today)
    return SummaryOut(
        session_id=session_id,
        first_try_correct=summary.first_try_correct,
        total=summary.total,
        wrong_problem_ids=summary.wrong_problem_ids,
        streak=summary.streak,
        stars_earned=summary.stars_earned,
        new_badges=summary.new_badges,
    )


class EventIn(BaseModel):
    id: str
    kind: str
    problem_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


class PostEventsIn(BaseModel):
    profile_id: str
    events: list[EventIn] = Field(min_length=1)


class QuizPartSolution(BaseModel):
    part_key: str
    solution: Solution


class QuizResultOut(BaseModel):
    """One Problem's verdict in a `quiz_submitted` response: ✔ (`correct`) or ↻, its Stars
    (3 or 0), and, for ↻ only, the Solutions of the Parts that were not right."""

    problem_id: str
    display_label: str
    correct: bool
    stars: int
    solutions: list[QuizPartSolution]


class EventOut(BaseModel):
    id: str
    session_id: str
    kind: str
    problem_id: str | None
    occurred_at: str
    received_at: str
    # Grading fields (Story 2.5): present only for `attempt` events.
    correct: bool | None = None
    wrong_keys: list[str] | None = None
    hint: str | None = None
    solution: Solution | None = None
    # Story 3.4: only on `quiz_submitted` -- every Problem's verdict, and whether this
    # submission awarded Stars at all (`False` for a retake of an already-submitted Lesson).
    quiz_results: list[QuizResultOut] | None = None
    quiz_stars_awarded: bool | None = None


def _event_out(e: service.EventOut) -> EventOut:
    return EventOut(
        id=e.id,
        session_id=e.session_id,
        kind=e.kind,
        problem_id=e.problem_id,
        occurred_at=e.occurred_at,
        received_at=e.received_at,
        correct=e.correct,
        wrong_keys=e.wrong_keys,
        hint=e.hint,
        solution=e.solution,
        quiz_results=None
        if e.quiz_results is None
        else [QuizResultOut.model_validate(r) for r in e.quiz_results],
        quiz_stars_awarded=e.quiz_stars_awarded,
    )


@router.post(
    "/{session_id}/events",
    response_model=list[EventOut],
    status_code=201,
    operation_id="post_session_events",
    responses={
        403: {"model": ErrorResponse, "description": "Profile doesn't own this Session"},
        404: {"model": ErrorResponse, "description": "Unknown Session"},
        422: {
            "model": ErrorResponse,
            "description": "Invalid event id, kind, problem_id, or (attempt) part_key",
        },
    },
)
def post_events(
    session_id: str, body: PostEventsIn, engine: EngineDep, now: NowDep
) -> list[EventOut]:
    for event in body.events:
        if not _is_uuid7(event.id):
            raise AppError(422, "INVALID_EVENT_ID", "Mã sự kiện không hợp lệ (cần UUIDv7).")
    in_events = [
        service.EventIn(
            id=event.id,
            kind=event.kind,
            problem_id=event.problem_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )
        for event in body.events
    ]
    # Validate the WHOLE batch (existence/ownership of the Session, every event's kind and
    # problem_id membership) BEFORE opening the write transaction below: a batch is either
    # fully attempted or rejected outright, never partially inserted then rolled back by a
    # later invalid sibling (see `service.validate_events_batch()`'s own docstring).
    with engine.connect() as conn:
        service.validate_events_batch(conn, session_id, body.profile_id, in_events)

    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        try:
            out: list[EventOut] = []
            with engine.begin() as conn:
                for in_event in in_events:
                    out.append(
                        _event_out(
                            service.post_event(conn, now, session_id, body.profile_id, in_event)
                        )
                    )
            return out
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == _LOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_LOCK_RETRY_DELAY_S * (attempt + 1))
    raise AssertionError("unreachable")  # pragma: no cover
