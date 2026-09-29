"""Parent progress dashboard (Story 4.2): read-only, PIN-guarded. Every figure comes from
`hoctap.learning.metrics`; nothing is computed here."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.learning import metrics
from hoctap.learning.summary import LOCAL_TZ
from hoctap.parent.auth import require_parent

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_parent)])


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DayOut(_Out):
    date: str
    future: bool
    sessions: int
    minutes: int
    first_try_correct: int
    problems: int
    self_check: int
    accuracy: float | None


class WeekOut(_Out):
    sessions: int
    minutes: int
    first_try_correct: int
    problems: int
    self_check: int
    accuracy: float | None


class DashboardUnit(_Out):
    unit_key: str
    label: str
    title: str
    attempted: int
    total: int


class DashboardBook(_Out):
    book_id: str
    title_vi: str
    attempted: int
    total: int
    units: list[DashboardUnit]


class WeakConceptOut(_Out):
    concept_id: str
    name_vi: str
    attempts: int
    first_try_correct: int
    accuracy: float


class MistakePartOut(_Out):
    part_key: str
    child_answer: str
    correct_answer: str


class MistakeOut(_Out):
    problem_id: str
    display_label: str
    completed_at: str
    parts: list[MistakePartOut]


class DashboardBadge(_Out):
    badge_key: str
    earned: bool
    earned_at: str | None


class DashboardOut(_Out):
    profile_id: str
    name: str
    grade: int
    week_start: str
    week_end: str
    stars: int
    streak: int
    badges: list[DashboardBadge]
    retry_due_count: int
    retry_open_count: int
    days: list[DayOut]
    week: WeekOut
    books: list[DashboardBook]
    weak_concepts: list[WeakConceptOut]
    recent_mistakes: list[MistakeOut]


@router.get(
    "/dashboard/{profile_id}",
    response_model=DashboardOut,
    operation_id="get_parent_dashboard",
    responses={404: {"model": ErrorResponse, "description": "PROFILE_NOT_FOUND"}},
)
def get_dashboard(
    profile_id: str,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> DashboardOut:
    today = now.astimezone(LOCAL_TZ).date()
    with engine.connect() as conn:
        try:
            result = metrics.dashboard(conn, profile_id, today)
        except metrics.ProfileNotFound:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.") from None
    return DashboardOut.model_validate(result)
