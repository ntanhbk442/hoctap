"""Child Profiles: the list is open (the child picks one without a PIN); writes need the
parent cookie."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, select

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.learning import badges as learning_badges
from hoctap.parent import service
from hoctap.parent.auth import require_parent
from hoctap.parent.models import parent_profiles
from hoctap.parent.schemas import Profile, ProfileIn, ProfilePatch

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[Profile], operation_id="list_profiles")
def list_profiles(engine: Annotated[Engine, Depends(get_engine)]) -> list[Profile]:
    return service.list_profiles(engine)


_guarded = [Depends(require_parent)]


@router.post(
    "",
    status_code=201,
    response_model=Profile,
    operation_id="create_profile",
    dependencies=_guarded,
    responses={409: {"model": ErrorResponse, "description": "PROFILE_LIMIT: 4 Profiles exist"}},
)
def create_profile(
    body: ProfileIn,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> Profile:
    return service.create_profile(engine, body, now)


@router.patch(
    "/{profile_id}",
    response_model=Profile,
    operation_id="update_profile",
    dependencies=_guarded,
    responses={404: {"model": ErrorResponse, "description": "Unknown profile"}},
)
def update_profile(
    profile_id: str, body: ProfilePatch, engine: Annotated[Engine, Depends(get_engine)]
) -> Profile:
    return service.update_profile(engine, profile_id, body)


@router.delete(
    "/{profile_id}",
    status_code=204,
    operation_id="delete_profile",
    dependencies=_guarded,
    responses={
        404: {"model": ErrorResponse, "description": "Unknown profile"},
        409: {"model": ErrorResponse, "description": "LAST_PROFILE: cannot remove the last one"},
    },
)
def delete_profile(profile_id: str, engine: Annotated[Engine, Depends(get_engine)]) -> None:
    service.delete_profile(engine, profile_id)


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
    return [BadgeOut(badge_key=s.badge_key, earned=s.earned, earned_at=s.earned_at) for s in states]
