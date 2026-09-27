"""First-run setup: create the PIN and the first Child Profile."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import ErrorResponse
from hoctap.parent import service
from hoctap.parent.auth import issue_cookie
from hoctap.parent.schemas import Profile, SetupRequest, SetupStatus

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatus, operation_id="get_setup_status")
def get_setup_status(engine: Annotated[Engine, Depends(get_engine)]) -> SetupStatus:
    return service.setup_status(engine)


@router.post(
    "",
    status_code=201,
    response_model=Profile,
    operation_id="complete_setup",
    responses={409: {"model": ErrorResponse, "description": "Setup already done"}},
)
def complete_setup(
    body: SetupRequest,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> Profile:
    profile = service.complete_setup(engine, body, now)
    issue_cookie(request, response)
    return profile
