"""Assignments (Story 4.3): Parent-only `POST/GET/DELETE /parent/assignments`."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import ErrorResponse
from hoctap.learning import assignments as service
from hoctap.learning.problem_sets import LessonRef
from hoctap.parent.auth import require_parent

router = APIRouter(
    prefix="/parent/assignments", tags=["parent"], dependencies=[Depends(require_parent)]
)

EngineDep = Annotated[Engine, Depends(get_engine)]
NowDep = Annotated[datetime, Depends(get_now)]


class AssignmentIn(BaseModel):
    profile_id: str
    book_id: str
    unit_key: str
    lesson_key: str
    assigned_date: date


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    book_id: str
    unit_key: str
    lesson_key: str
    assigned_date: str
    status: str  # todo | doing | done
    part: int | None = None
    part_count: int | None = None
    carried_over: bool
    book_title_vi: str
    unit_label: str
    lesson_label: str
    lesson_title: str


def assignment_out(a: service.AssignmentInfo) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        profile_id=a.profile_id,
        book_id=a.book_id,
        unit_key=a.unit_key,
        lesson_key=a.lesson_key,
        assigned_date=a.assigned_date,
        status=a.status,
        part=a.part,
        part_count=a.part_count,
        carried_over=a.carried_over,
        book_title_vi=a.book_title_vi,
        unit_label=a.unit_label,
        lesson_label=a.lesson_label,
        lesson_title=a.lesson_title,
    )


@router.post(
    "",
    status_code=201,
    response_model=AssignmentOut,
    operation_id="create_assignment",
    responses={
        404: {"model": ErrorResponse, "description": "PROFILE_NOT_FOUND"},
        422: {"model": ErrorResponse, "description": "DATE_IN_PAST or EMPTY_PROBLEM_SET"},
    },
)
def create_assignment(body: AssignmentIn, engine: EngineDep, now: NowDep) -> AssignmentOut:
    ref = LessonRef(book_id=body.book_id, unit_key=body.unit_key, lesson_key=body.lesson_key)
    with engine.begin() as conn:
        return assignment_out(service.create(conn, now, body.profile_id, ref, body.assigned_date))


@router.get(
    "",
    response_model=list[AssignmentOut],
    operation_id="list_assignments",
    responses={404: {"model": ErrorResponse, "description": "PROFILE_NOT_FOUND"}},
)
def list_assignments(profile_id: str, engine: EngineDep, now: NowDep) -> list[AssignmentOut]:
    with engine.connect() as conn:
        service._profile_exists(conn, profile_id)
        return [
            assignment_out(a)
            for a in service.list_for_profile(conn, profile_id, service.local_today(now))
        ]


@router.delete(
    "/{assignment_id}",
    status_code=204,
    operation_id="delete_assignment",
    responses={
        404: {"model": ErrorResponse, "description": "ASSIGNMENT_NOT_FOUND"},
        409: {"model": ErrorResponse, "description": "ASSIGNMENT_DONE"},
    },
)
def delete_assignment(assignment_id: str, engine: EngineDep, now: NowDep) -> None:
    with engine.begin() as conn:
        service.delete(conn, now, assignment_id)
