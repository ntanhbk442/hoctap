"""Parent module services: first-run setup, PIN check with lockout, Child Profiles.

Only this module writes `parent_*` tables, each mutation in one transaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import Connection, Engine, case, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from hoctap.api.errors import AppError
from hoctap.ids import from_iso, new_id, to_iso
from hoctap.learning.progress import delete_profile_progress
from hoctap.parent.models import parent_profiles, parent_settings
from hoctap.parent.schemas import (
    ChangePinRequest,
    Pin,
    Profile,
    ProfileIn,
    ProfilePatch,
    SetupRequest,
    SetupStatus,
)

SETTINGS_ID = 1
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=5)
# bcrypt work factor; tests lower it to keep the suite fast.
BCRYPT_ROUNDS = 12

MSG_PIN_MISMATCH = "Hai mã PIN không khớp"
MSG_PIN_INCORRECT = "Mã PIN chưa đúng"
MSG_PIN_LOCKED = "Nhập sai mã PIN quá nhiều lần. Vui lòng thử lại sau 5 phút."
MSG_SETUP_DONE = "Ứng dụng đã được thiết lập."
MSG_SETUP_REQUIRED = "Cần thiết lập mã PIN trước."
MSG_PROFILE_LIMIT = "Chỉ có thể tạo tối đa 4 hồ sơ."
MSG_PROFILE_NOT_FOUND = "Không tìm thấy hồ sơ."
MSG_LAST_PROFILE = "Không thể xoá hồ sơ cuối cùng."
MAX_PROFILES = 4


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("ascii"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _check_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode("ascii"), pin_hash.encode("ascii"))


def _settings_exist(conn: Connection) -> bool:
    row = conn.execute(select(parent_settings.c.id).where(parent_settings.c.id == SETTINGS_ID))
    return row.first() is not None


def is_setup_done(engine: Engine) -> bool:
    with engine.connect() as conn:
        return _settings_exist(conn)


def setup_status(engine: Engine) -> SetupStatus:
    return SetupStatus(setup_required=not is_setup_done(engine))


def complete_setup(engine: Engine, req: SetupRequest, now: datetime) -> Profile:
    """Stores the PIN hash and the first Child Profile in one transaction."""
    if is_setup_done(engine):
        raise AppError(409, "SETUP_DONE", MSG_SETUP_DONE)
    if req.pin != req.pin_confirm:
        raise AppError(422, "PIN_MISMATCH", MSG_PIN_MISMATCH)
    pin_hash = _hash_pin(req.pin)  # slow; kept outside the write transaction
    stamp = to_iso(now)
    profile = Profile(
        id=new_id(), name=req.profile.name, avatar=req.profile.avatar, grade=req.profile.grade
    )
    try:
        with engine.begin() as conn:
            if _settings_exist(conn):
                raise AppError(409, "SETUP_DONE", MSG_SETUP_DONE)
            conn.execute(
                insert(parent_settings).values(
                    id=SETTINGS_ID,
                    pin_hash=pin_hash,
                    failed_attempts=0,
                    locked_until=None,
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
            conn.execute(insert(parent_profiles).values(**profile.model_dump(), created_at=stamp))
    except IntegrityError as exc:  # a concurrent setup won the race
        raise AppError(409, "SETUP_DONE", MSG_SETUP_DONE) from exc
    return profile


def _not_locked(now_iso: str):  # noqa: ANN202
    t = parent_settings.c
    return (t.id == SETTINGS_ID) & (t.locked_until.is_(None) | (t.locked_until <= now_iso))


def verify_pin(engine: Engine, pin: str, now: datetime) -> None:
    """Checks the PIN with the brute-force guard. Returns on success, raises otherwise.

    After MAX_FAILED_ATTEMPTS wrong PINs in a row, every attempt (even a correct one)
    gets 429 PIN_LOCKED until LOCKOUT has passed; then the counter starts again.

    Each write is one atomic UPDATE guarded by "not locked", so parallel wrong attempts
    are each counted exactly once, and attempts during a lock change nothing.
    Timestamps are fixed-format UTC ISO text (`to_iso`), so text comparison is safe.
    """
    with engine.connect() as conn:
        row = conn.execute(
            select(parent_settings.c.pin_hash, parent_settings.c.locked_until).where(
                parent_settings.c.id == SETTINGS_ID
            )
        ).first()
    if row is None:
        raise AppError(403, "SETUP_REQUIRED", MSG_SETUP_REQUIRED)
    if row.locked_until is not None and now < from_iso(row.locked_until):
        raise AppError(429, "PIN_LOCKED", MSG_PIN_LOCKED)

    correct = _check_pin(pin, row.pin_hash)  # slow; no transaction held
    now_iso = to_iso(now)
    t = parent_settings.c
    if correct:
        stmt = (
            update(parent_settings)
            .where(_not_locked(now_iso))
            .values(failed_attempts=0, locked_until=None, updated_at=now_iso)
            .returning(t.id)
        )
    else:
        # An expired lock restarts the count; SET expressions see the old row values.
        new_count = case((t.locked_until.is_not(None), 1), else_=t.failed_attempts + 1)
        stmt = (
            update(parent_settings)
            .where(_not_locked(now_iso))
            .values(
                failed_attempts=new_count,
                locked_until=case(
                    (new_count >= MAX_FAILED_ATTEMPTS, to_iso(now + LOCKOUT)), else_=None
                ),
                updated_at=now_iso,
            )
            .returning(t.id)
        )
    with engine.begin() as conn:
        updated = conn.execute(stmt).first()
    if updated is None:  # a concurrent attempt locked it meanwhile
        raise AppError(429, "PIN_LOCKED", MSG_PIN_LOCKED)
    if not correct:
        raise AppError(401, "PIN_INCORRECT", MSG_PIN_INCORRECT)


def session_version(engine: Engine) -> int | None:
    """The current parent session version, or None while setup is not done."""
    with engine.connect() as conn:
        return conn.execute(
            select(parent_settings.c.session_version).where(parent_settings.c.id == SETTINGS_ID)
        ).scalar_one_or_none()


def end_sessions(engine: Engine, now: datetime) -> None:
    """Invalidates every issued parent cookie (logout)."""
    with engine.begin() as conn:
        conn.execute(
            update(parent_settings)
            .where(parent_settings.c.id == SETTINGS_ID)
            .values(session_version=parent_settings.c.session_version + 1, updated_at=to_iso(now))
        )


def list_profiles(engine: Engine) -> list[Profile]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                parent_profiles.c.id,
                parent_profiles.c.name,
                parent_profiles.c.avatar,
                parent_profiles.c.grade,
                parent_profiles.c.auto_play,
            ).order_by(parent_profiles.c.created_at, parent_profiles.c.id)
        ).all()
    return [
        Profile(id=r.id, name=r.name, avatar=r.avatar, grade=r.grade, auto_play=bool(r.auto_play))
        for r in rows
    ]


def _profile_from_row(r) -> Profile:  # noqa: ANN001
    return Profile(
        id=r.id, name=r.name, avatar=r.avatar, grade=r.grade, auto_play=bool(r.auto_play)
    )


def create_profile(engine: Engine, data: ProfileIn, now: datetime) -> Profile:
    """Adds a Profile; the 4-Profile cap is checked by the INSERT itself (atomic)."""
    profile = Profile(id=new_id(), name=data.name, avatar=data.avatar, grade=data.grade)
    values = {**profile.model_dump(), "created_at": to_iso(now)}
    count = select(func.count()).select_from(parent_profiles).scalar_subquery()
    source = select(*[_lit(k, v) for k, v in values.items()]).where(count < MAX_PROFILES)
    with engine.begin() as conn:
        result = conn.execute(insert(parent_profiles).from_select(list(values), source))
        if result.rowcount != 1:
            raise AppError(409, "PROFILE_LIMIT", MSG_PROFILE_LIMIT)
    return profile


def _lit(name: str, value):  # noqa: ANN001, ANN202
    from sqlalchemy import literal

    return literal(value, parent_profiles.c[name].type).label(name)


def update_profile(engine: Engine, profile_id: str, patch: ProfilePatch) -> Profile:
    changes = patch.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        if changes:
            found = conn.execute(
                update(parent_profiles).where(parent_profiles.c.id == profile_id).values(**changes)
            ).rowcount
            if found != 1:
                raise AppError(404, "PROFILE_NOT_FOUND", MSG_PROFILE_NOT_FOUND)
        row = conn.execute(
            select(
                parent_profiles.c.id,
                parent_profiles.c.name,
                parent_profiles.c.avatar,
                parent_profiles.c.grade,
                parent_profiles.c.auto_play,
            ).where(parent_profiles.c.id == profile_id)
        ).first()
    if row is None:
        raise AppError(404, "PROFILE_NOT_FOUND", MSG_PROFILE_NOT_FOUND)
    return _profile_from_row(row)


def delete_profile(engine: Engine, profile_id: str) -> None:
    """Removes a Profile and all of its progress in one transaction (no undo)."""
    with engine.begin() as conn:
        exists = conn.execute(
            select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
        ).first()
        if exists is None:
            raise AppError(404, "PROFILE_NOT_FOUND", MSG_PROFILE_NOT_FOUND)
        total = conn.execute(select(func.count()).select_from(parent_profiles)).scalar_one()
        if total <= 1:
            raise AppError(409, "LAST_PROFILE", MSG_LAST_PROFILE)
        delete_profile_progress(conn, profile_id)
        conn.execute(delete(parent_profiles).where(parent_profiles.c.id == profile_id))


def change_pin(engine: Engine, req: ChangePinRequest, now: datetime) -> None:
    """Checks the current PIN (with the lockout counter), stores the new hash and ends
    every parent session. The caller re-issues its own cookie afterwards."""
    if req.new_pin != req.new_pin_confirm:
        raise AppError(422, "PIN_MISMATCH", MSG_PIN_MISMATCH)
    verify_pin(engine, req.current_pin, now)
    set_pin(engine, req.new_pin, now)


def set_pin(engine: Engine, pin: str, now: datetime) -> None:
    """Replaces the PIN, clears the lockout and bumps `session_version`."""
    pin_hash = _hash_pin(pin)
    with engine.begin() as conn:
        updated = conn.execute(
            update(parent_settings)
            .where(parent_settings.c.id == SETTINGS_ID)
            .values(
                pin_hash=pin_hash,
                failed_attempts=0,
                locked_until=None,
                session_version=parent_settings.c.session_version + 1,
                updated_at=to_iso(now),
            )
        ).rowcount
    if updated != 1:
        raise AppError(403, "SETUP_REQUIRED", MSG_SETUP_REQUIRED)


def reset_pin(engine: Engine, pin: str, now: datetime) -> None:
    """Host-side forgotten-PIN reset (CLI only; no HTTP route). Validates like `Pin`."""
    from pydantic import TypeAdapter

    TypeAdapter(Pin).validate_python(pin)
    set_pin(engine, pin, now)
