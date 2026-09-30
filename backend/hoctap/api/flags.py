"""Child 🚩 (`POST /problems/{id}/flag`): no PIN, takes a `profile_id`. It can only add an
open `child` Error Report through the review service; the Problem stays visible."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.content.review import service
from hoctap.parent.models import parent_profiles

router = APIRouter(prefix="/problems", tags=["flags"])


class FlagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str


class FlagOut(BaseModel):
    ok: bool = True


@router.post(
    "/{problem_id}/flag",
    response_model=FlagOut,
    operation_id="flag_problem",
    responses={
        404: {"model": ErrorResponse, "description": "PROFILE_NOT_FOUND or PROBLEM_NOT_FOUND"}
    },
)
def flag_problem(
    problem_id: str,
    body: FlagIn,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> FlagOut:
    with engine.begin() as conn:
        exists = conn.execute(
            select(parent_profiles.c.id).where(parent_profiles.c.id == body.profile_id)
        ).scalar_one_or_none()
        if exists is None:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        service.add_error_report(conn, problem_id, "child", "", now)
    return FlagOut()
