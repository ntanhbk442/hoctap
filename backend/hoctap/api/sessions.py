"""Sessions (Story 2.4): `POST /sessions`, `GET /sessions/{id}/bundle`,
`POST /sessions/{id}/events` -- child-facing, no PIN/parent gate (same trust level as
`/profiles`, `/library/*`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content.views import ChildProblemView
from hoctap.learning import sessions as service
from hoctap.learning.problem_sets import LessonRef

router = APIRouter(prefix="/sessions", tags=["sessions"])

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


class StartSessionIn(BaseModel):
    profile_id: str
    ref: LessonRefIn


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
        404: {"model": ErrorResponse, "description": "Unknown profile"},
        422: {"model": ErrorResponse, "description": "Empty Problem set"},
    },
)
def start_session(body: StartSessionIn, engine: EngineDep, now: NowDep) -> SessionOut:
    ref = LessonRef(
        book_id=body.ref.book_id, unit_key=body.ref.unit_key, lesson_key=body.ref.lesson_key
    )
    with engine.begin() as conn:
        return _session_out(service.start_session(conn, now, body.profile_id, ref))


class BundleProblemOut(BaseModel):
    problem: ChildProblemView
    crop_urls: list[str]
    page_urls: list[str]
    audio: dict[str, str]
    attempted: bool


class BundleOut(BaseModel):
    session_id: str
    chunk: int
    chunk_count: int
    chunk_label: str
    problems: list[BundleProblemOut]


def _bundle_out(b: service.BundleOut) -> BundleOut:
    return BundleOut(
        session_id=b.session_id,
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


class EventIn(BaseModel):
    id: str
    kind: str
    problem_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


class PostEventsIn(BaseModel):
    profile_id: str
    events: list[EventIn] = Field(min_length=1)


class EventOut(BaseModel):
    id: str
    session_id: str
    kind: str
    problem_id: str | None
    occurred_at: str
    received_at: str


def _event_out(e: service.EventOut) -> EventOut:
    return EventOut(
        id=e.id,
        session_id=e.session_id,
        kind=e.kind,
        problem_id=e.problem_id,
        occurred_at=e.occurred_at,
        received_at=e.received_at,
    )


@router.post(
    "/{session_id}/events",
    response_model=list[EventOut],
    status_code=201,
    operation_id="post_session_events",
    responses={
        403: {"model": ErrorResponse, "description": "Profile doesn't own this Session"},
        404: {"model": ErrorResponse, "description": "Unknown Session"},
        422: {"model": ErrorResponse, "description": "Invalid event id, kind, or problem_id"},
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

    out: list[EventOut] = []
    with engine.begin() as conn:
        for in_event in in_events:
            out.append(
                _event_out(service.post_event(conn, now, session_id, body.profile_id, in_event))
            )
    return out
