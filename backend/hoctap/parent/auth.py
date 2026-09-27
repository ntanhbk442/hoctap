"""Parent session cookie and the `require_parent` guard.

The cookie `hoctap_parent` carries a signed timestamp (itsdangerous). The signing key
lives in `<data_dir>/secret.key`, created on first start, never in the DB or the repo.
Idle expiry is 30 minutes; every authenticated request re-issues the cookie.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Request, Response
from itsdangerous import BadSignature, TimestampSigner

from hoctap.api.errors import AppError
from hoctap.ids import Clock, utc_now
from hoctap.parent import service

log = logging.getLogger(__name__)

COOKIE_NAME = "hoctap_parent"
IDLE_TIMEOUT = timedelta(minutes=30)
SECRET_FILE = "secret.key"
_PAYLOAD_PREFIX = "parent:"
_SALT = "hoctap.parent.session"

MSG_UNAUTHORIZED = "Cần nhập mã PIN."


def load_or_create_secret(data_dir: Path) -> bytes:
    """Reads `secret.key`, creating it (random, owner-only) if missing or empty.

    The key is written to a temp file, fsynced and moved into place, so a crash never
    leaves a partial key behind.
    """
    path = data_dir / SECRET_FILE
    data_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0 or not path.read_bytes().strip():
        tmp = path.with_name(f"{SECRET_FILE}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(secrets.token_hex(32))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        log.info("created secret key", extra={"path": str(path)})
    try:
        key = path.read_bytes().decode("ascii").strip()
    except UnicodeDecodeError:
        key = ""
    if len(key) < 32:
        raise RuntimeError(f"{path}: secret key is unreadable or too short")
    return key.encode("ascii")


class _ClockSigner(TimestampSigner):
    """TimestampSigner whose notion of "now" comes from the injectable clock."""

    def __init__(self, secret_key: bytes, clock: Clock) -> None:
        super().__init__(secret_key, salt=_SALT)
        self._clock = clock

    def get_timestamp(self) -> int:
        return int(self._clock().timestamp())


def _signer(request: Request) -> _ClockSigner:
    return _ClockSigner(request.app.state.secret_key, get_clock(request))


def get_clock(request: Request) -> Clock:
    return getattr(request.app.state, "clock", utc_now)


def _payload(version: int) -> bytes:
    return f"{_PAYLOAD_PREFIX}{version}".encode("ascii")


def issue_cookie(request: Request, response: Response, version: int | None = None) -> None:
    """Sets a fresh parent cookie bound to the current session version."""
    if version is None:
        version = service.session_version(request.app.state.engine)
        if version is None:
            raise AppError(403, "SETUP_REQUIRED", service.MSG_SETUP_REQUIRED)
    token = _signer(request).sign(_payload(version)).decode("ascii")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(IDLE_TIMEOUT.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def clear_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def cookie_valid(request: Request, version: int) -> bool:
    """True if the request carries an unexpired cookie signed for `version`."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        # max_age also rejects timestamps from the future (negative age).
        value = _signer(request).unsign(token, max_age=int(IDLE_TIMEOUT.total_seconds()))
    except BadSignature:  # includes SignatureExpired
        return False
    return value == _payload(version)


def logout_parent(request: Request, response: Response, now: datetime) -> None:
    """Clears the cookie. A valid cookie also ends every parent session (version + 1),
    so a copied cookie stops working; without one, nothing else changes."""
    engine = request.app.state.engine
    version = service.session_version(engine)
    if version is None:
        raise AppError(403, "SETUP_REQUIRED", service.MSG_SETUP_REQUIRED)
    if cookie_valid(request, version):
        service.end_sessions(engine, now)
    clear_cookie(request, response)


def require_parent(request: Request, response: Response) -> None:
    """Session guard for the parent routes behind the PIN (`/api/v1/parent/session`,
    `/api/v1/build/*`). Login and logout are not behind it; they are only setup-gated.

    403 SETUP_REQUIRED while no PIN exists, 401 UNAUTHORIZED without a valid cookie for
    the current session version. On success the cookie is re-issued so the idle expiry
    slides.
    """
    version = service.session_version(request.app.state.engine)
    if version is None:
        raise AppError(403, "SETUP_REQUIRED", service.MSG_SETUP_REQUIRED)
    if not cookie_valid(request, version):
        raise AppError(401, "UNAUTHORIZED", MSG_UNAUTHORIZED)
    issue_cookie(request, response, version)
