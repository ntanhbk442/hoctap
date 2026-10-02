"""Assignments (Story 4.3): Parent-only `POST/GET/DELETE /parent/assignments`."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import ErrorResponse
from hoctap.api.sessions import (
    ExamBookUnitScopeIn,
    ExamConceptScopeIn,
    ExamGradeScopeIn,
    exam_scope_from_in,
)
from hoctap.learning import assignments as service
from hoctap.learning.problem_sets import ExamRef, LessonRef
from hoctap.parent.auth import require_parent

router = APIRouter(
    prefix="/parent/assignments", tags=["parent"], dependencies=[Depends(require_parent)]
)

EngineDep = Annotated[Engine, Depends(get_engine)]
NowDep = Annotated[datetime, Depends(get_now)]


class AssignmentExamIn(BaseModel):
    """Story 8.1: the exam-assign payload, the SAME scope/count/time_limit_s shape
    `api.sessions.ExamRefIn` uses for an on-demand exam (one picker, both flows)."""

    scope: ExamConceptScopeIn | ExamBookUnitScopeIn | ExamGradeScopeIn = Field(
        discriminator="kind"
    )
    count: int = Field(gt=0)
    time_limit_s: int = Field(gt=0)


class AssignmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    # The existing Lesson-ref shape (all three set together) -- unchanged for backward
    # compatibility with Story 4.3's own flat body.
    book_id: str | None = None
    unit_key: str | None = None
    lesson_key: str | None = None
    # Story 8.1: the new exam-ref shape. Exactly one of (the Lesson trio) or `exam` must be
    # given -- never both, never neither (mirrors `ck_progress_assignments_ref_xor`).
    exam: AssignmentExamIn | None = None
    assigned_date: date

    @model_validator(mode="after")
    def _exactly_one_ref(self) -> AssignmentIn:
        lesson_fields = (self.book_id, self.unit_key, self.lesson_key)
        is_lesson = all(f is not None for f in lesson_fields)
        is_partial_lesson = any(f is not None for f in lesson_fields) and not is_lesson
        if is_partial_lesson:
            raise ValueError("book_id, unit_key and lesson_key must all be set together")
        if is_lesson == (self.exam is not None):
            raise ValueError("exactly one of (book_id/unit_key/lesson_key) or exam is required")
        return self


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    ref_kind: str  # "lesson" | "exam" (Story 8.1)
    book_id: str | None = None
    unit_key: str | None = None
    lesson_key: str | None = None
    assigned_date: str
    status: str  # todo | doing | done
    part: int | None = None
    part_count: int | None = None
    carried_over: bool
    book_title_vi: str
    unit_label: str
    lesson_label: str
    lesson_title: str
    # Story 8.1: set only when `ref_kind == "exam"`. The child's start-session request for
    # an assigned exam echoes these straight back as `ExamRefIn` (plus `assignment_id`).
    exam_scope: dict[str, object] | None = None
    exam_count: int | None = None
    exam_time_limit_s: int | None = None
    # Orchestrator's Independent Audit (spec-4-3 #1, 2026-10-01): false when the ref no
    # longer resolves to any visible Problem (hidden/retired/reported after assignment) --
    # such a row is never served to Home as "Bài hôm nay" (`home_assignment()` skips it),
    # but still lists here so the Dashboard can flag it for Anh to delete or fix.
    resolvable: bool = True


def assignment_out(a: service.AssignmentInfo) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        profile_id=a.profile_id,
        ref_kind=a.ref_kind,
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
        exam_scope=a.exam_scope,
        exam_count=a.exam_count,
        exam_time_limit_s=a.exam_time_limit_s,
        resolvable=a.resolvable,
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
    ref: LessonRef | ExamRef
    if body.exam is not None:
        ref = ExamRef(
            scope=exam_scope_from_in(body.exam.scope),
            count=body.exam.count,
            time_limit_s=body.exam.time_limit_s,
        )
    else:
        assert (
            body.book_id is not None
            and body.unit_key is not None
            and body.lesson_key is not None
        )
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
