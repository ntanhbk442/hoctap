"""Child Profiles (read-only; the child picks one without a PIN)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, select

from hoctap.api.deps import get_engine
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.learning import badges as learning_badges
from hoctap.parent import service
from hoctap.parent.models import parent_profiles
from hoctap.parent.schemas import Profile

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[Profile], operation_id="list_profiles")
def list_profiles(engine: Annotated[Engine, Depends(get_engine)]) -> list[Profile]:
    return service.list_profiles(engine)


class BadgeOut(BaseModel):
    badge_key: str
    earned: bool
    earned_at: str | None = None


@router.get(
    "/{profile_id}/badges",
    response_model=list[BadgeOut],
    operation_id="get_profile_badges",
    responses={404: {"model": ErrorResponse, "description": "Unknown profile"}},
)
def get_profile_badges(
    profile_id: str, engine: Annotated[Engine, Depends(get_engine)]
) -> list[BadgeOut]:
    """Story 3.2: all 3 fixed badges (`week1`, `streak7`, `stars100`) with `earned`/
    `earned_at` -- the "Huy hiệu của em" screen's full state, unearned ones rendered
    greyed out by the frontend."""
    with engine.connect() as conn:
        exists = conn.execute(
            select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
        ).scalar_one_or_none()
        if exists is None:
            raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        states = learning_badges.profile_badges(conn, profile_id)
    return [
        BadgeOut(badge_key=s.badge_key, earned=s.earned, earned_at=s.earned_at) for s in states
    ]
