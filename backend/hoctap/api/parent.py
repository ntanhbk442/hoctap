"""Parent Area session: PIN login, logout and session check."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now
from hoctap.api.errors import ErrorResponse
from hoctap.parent import service
from hoctap.parent.auth import issue_cookie, logout_parent, require_parent
from hoctap.parent.schemas import ChangePinRequest, LoginRequest, SessionStatus

router = APIRouter(
    prefix="/parent",
    tags=["parent"],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in or wrong PIN"},
        403: {"model": ErrorResponse, "description": "Setup required"},
    },
)


@router.post(
    "/login",
    status_code=204,
    operation_id="parent_login",
    responses={429: {"model": ErrorResponse, "description": "Too many wrong PINs"}},
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> None:
    service.verify_pin(engine, body.pin, now)
    issue_cookie(request, response)


@router.post("/logout", status_code=204, operation_id="parent_logout")
def logout(
    request: Request, response: Response, now: Annotated[datetime, Depends(get_now)]
) -> None:
    logout_parent(request, response, now)


@router.get(
    "/session",
    response_model=SessionStatus,
    operation_id="get_parent_session",
    dependencies=[Depends(require_parent)],
)
def get_session() -> SessionStatus:
    return SessionStatus(authenticated=True)


@router.post(
    "/pin",
    status_code=204,
    operation_id="change_parent_pin",
    dependencies=[Depends(require_parent)],
    responses={
        422: {"model": ErrorResponse, "description": "New PINs do not match"},
        429: {"model": ErrorResponse, "description": "Too many wrong PINs"},
    },
)
def change_pin(
    body: ChangePinRequest,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
    now: Annotated[datetime, Depends(get_now)],
) -> None:
    service.change_pin(engine, body, now)
    issue_cookie(request, response)  # the new session version; other cookies are dead
