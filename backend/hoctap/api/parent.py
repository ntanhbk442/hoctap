"""Parent Area session: PIN login, logout and session check."""

from __future__ import annotations

import shutil
import tempfile
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from starlette.background import BackgroundTask

from hoctap.api.deps import get_engine, get_now, get_settings
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.config import Settings
from hoctap.parent import backup, service
from hoctap.parent.auth import clear_cookie, issue_cookie, logout_parent, require_parent
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


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@router.post(
    "/backup",
    operation_id="parent_backup",
    dependencies=[Depends(require_parent)],
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "A verified single-file SQLite backup",
        },
        500: {"model": ErrorResponse, "description": "The copy failed its integrity check"},
    },
)
def make_backup(
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> FileResponse:
    """Consistent copy of the whole database, made while the app keeps running."""
    tmp_root = settings.data_dir / backup.BACKUP_DIR_NAME
    tmp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".download-", dir=tmp_root))
    name = backup.backup_filename(now)
    try:
        path = backup.make_backup(engine, work / name)
    except BaseException:
        _rmtree(work)
        raise
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
        background=BackgroundTask(_rmtree, work),
    )


class RestoreOut(BaseModel):
    safety_backup: str
    revision: str
    db_epoch: str


@router.post(
    "/restore",
    response_model=RestoreOut,
    operation_id="parent_restore",
    dependencies=[Depends(require_parent)],
    responses={
        409: {"model": ErrorResponse, "description": "BACKUP_NEWER, BUILD_RUNNING or busy"},
        422: {"model": ErrorResponse, "description": "BACKUP_INVALID or wrong confirmation"},
        500: {"model": ErrorResponse, "description": "RESTORE_FAILED (rolled back)"},
        503: {"model": ErrorResponse, "description": "MAINTENANCE"},
    },
)
def restore_backup(
    request: Request,
    response: Response,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
    confirm: Annotated[str, Form()] = "",
) -> RestoreOut:
    """Replaces the database with an uploaded backup. All parent cookies become invalid."""
    typed = unicodedata.normalize("NFC", confirm).strip().upper()
    if typed != unicodedata.normalize("NFC", backup.CONFIRM_PHRASE):
        raise AppError(422, "CONFIRM_REQUIRED", backup.MSG_CONFIRM)
    tmp_dir = settings.data_dir / backup.BACKUP_DIR_NAME
    tmp_dir.mkdir(parents=True, exist_ok=True)
    upload = tmp_dir / f".upload-{uuid.uuid4().hex}.db"
    try:
        written = 0
        with upload.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > backup.MAX_UPLOAD_BYTES:
                    raise AppError(413, "BACKUP_TOO_LARGE", backup.MSG_TOO_LARGE)
                out.write(chunk)
        result = backup.restore(request.app, upload)
    finally:
        upload.unlink(missing_ok=True)
    clear_cookie(request, response)  # the key was rotated: every old cookie is dead anyway
    return RestoreOut(
        safety_backup=result.safety_backup.name,
        revision=result.revision,
        db_epoch=result.db_epoch,
    )
