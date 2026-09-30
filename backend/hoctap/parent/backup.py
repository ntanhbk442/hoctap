"""Backup and restore of the whole database (Story 7.2, NFR-7, AD-14).

A backup is one consistent `.db` file made with SQLite's online backup API while the app
keeps serving (never a file copy of the live `.db`/`-wal`), then checked with
`PRAGMA integrity_check`. A restore validates the upload first, refuses during a build,
takes a safety backup, swaps the file in maintenance mode, migrates, rotates the cookie
key and the `db_epoch`, and on any failure after the swap starts puts the safety backup
back.

Backups hold the PIN hash; they are private files. They never include `secret.key`,
`assets/`, `build/`, `logs/` or the source PDFs.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import Engine

from hoctap.api.errors import AppError
from hoctap.db.engine import head_revision, is_known_revision, run_migrations
from hoctap.ids import utc_now
from hoctap.parent import service
from hoctap.parent.auth import SECRET_FILE, load_or_create_secret

log = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
CONFIRM_PHRASE = "KHÔI PHỤC"
SQLITE_HEADER = b"SQLite format 3\x00"
DRAIN_TIMEOUT_S = 15.0
# A database-only backup is a few MB; this only stops a mistaken or hostile upload from
# filling the disk that holds the data.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024

MSG_INVALID = "Tệp này không phải bản sao lưu hợp lệ. Không có gì bị thay đổi."
MSG_NEWER = (
    "Bản sao lưu này được tạo bởi phiên bản mới hơn của ứng dụng (%(theirs)s, ứng dụng hiện "
    "có %(ours)s). Hãy cập nhật ứng dụng trước. Không có gì bị thay đổi."
)
MSG_BUILD_RUNNING = (
    "Đang có lượt dựng nội dung chạy. Hãy đợi xong rồi khôi phục. Không có gì bị thay đổi."
)
MSG_TOO_LARGE = "Tệp quá lớn để là bản sao lưu. Không có gì bị thay đổi."
MSG_CONFIRM = "Cần gõ đúng cụm “KHÔI PHỤC” để xác nhận."
MSG_BACKUP_FAILED = "Không tạo được bản sao lưu."
MSG_RESTORE_FAILED = "Khôi phục không thành công; dữ liệu hiện tại đã được giữ nguyên."
MSG_RESTORE_BUSY = "Máy đang bận, chưa thể khôi phục. Hãy thử lại sau ít phút."
MSG_RESTORE_RUNNING = "Đang có một lần khôi phục khác."
MSG_MAINTENANCE = "Đang khôi phục dữ liệu. Vui lòng thử lại sau ít giây."


class Maintenance:
    """Maintenance flag plus an in-flight request counter, shared with the middleware."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.active = False
        self._inflight = 0

    def enter(self) -> bool:
        """Registers a request; False while maintenance is on."""
        with self._cond:
            if self.active:
                return False
            self._inflight += 1
            return True

    def leave(self) -> None:
        with self._cond:
            self._inflight -= 1
            self._cond.notify_all()

    def begin(self, own: int, timeout: float) -> bool:
        """Turns maintenance on and waits until only `own` requests (the caller) remain."""
        with self._cond:
            self.active = True
            drained = self._cond.wait_for(lambda: self._inflight <= own, timeout)
            if not drained:
                self.active = False
            return drained

    def end(self) -> None:
        with self._cond:
            self.active = False
            self._cond.notify_all()


def backup_filename(now: datetime | None = None) -> str:
    stamp = (now or utc_now()).strftime("%Y%m%d-%H%M%S")
    return f"hoctap-backup-{stamp}.db"


def _integrity_ok(con: sqlite3.Connection) -> bool:
    rows = con.execute("PRAGMA integrity_check").fetchall()
    return len(rows) == 1 and rows[0][0] == "ok"


def _drop_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def make_backup(engine: Engine, dest: Path) -> Path:
    """Writes a consistent, integrity-checked copy of the live database to `dest`.

    The copy is built in `<dest>.part` and moved into place only once it verified, so a
    failure never leaves a half-written file at `dest`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.unlink(missing_ok=True)
    try:
        raw = engine.raw_connection()
        try:
            src = raw.driver_connection
            assert isinstance(src, sqlite3.Connection)
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
                # A single self-contained file: no WAL mode flag, no -wal/-shm beside it.
                dst.execute("PRAGMA journal_mode=DELETE")
                ok = _integrity_ok(dst)
            finally:
                dst.close()
        finally:
            raw.close()
        if not ok:
            raise sqlite3.DatabaseError("integrity_check failed on the backup copy")
        os.replace(tmp, dest)
    except (sqlite3.Error, OSError) as exc:
        log.error("backup failed", extra={"error": type(exc).__name__})
        raise AppError(500, "BACKUP_FAILED", MSG_BACKUP_FAILED) from exc
    finally:
        tmp.unlink(missing_ok=True)
        _drop_sidecars(tmp)
    return dest


def verify_backup(path: Path) -> str:
    """Checks that `path` is a usable backup and returns its Alembic revision.

    422 BACKUP_INVALID: not SQLite, corrupt, or no `alembic_version`.
    409 BACKUP_NEWER: its revision is unknown to this app (made by a newer version).
    Nothing is modified except that SQLite may create and remove `-wal`/`-shm` beside it.
    """
    invalid = AppError(422, "BACKUP_INVALID", MSG_INVALID)
    try:
        with path.open("rb") as fh:
            if fh.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                raise invalid
    except OSError as exc:
        raise invalid from exc
    revision: str | None = None
    try:
        con = sqlite3.connect(path)
        try:
            if not _integrity_ok(con):
                raise invalid
            rows = con.execute("SELECT version_num FROM alembic_version").fetchall()
            if len(rows) == 1 and isinstance(rows[0][0], str) and rows[0][0]:
                revision = rows[0][0]
        finally:
            con.close()
    except (sqlite3.Error, ValueError) as exc:
        raise invalid from exc
    finally:
        _drop_sidecars(path)
    if revision is None:
        raise invalid
    if not is_known_revision(revision):
        raise AppError(
            409,
            "BACKUP_NEWER",
            MSG_NEWER % {"theirs": revision, "ours": head_revision()},
        )
    return revision


def _write_secret(data_dir: Path, value: bytes) -> None:
    path = data_dir / SECRET_FILE
    tmp = path.with_name(f"{SECRET_FILE}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(value)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True)
class RestoreResult:
    safety_backup: Path
    revision: str
    db_epoch: str


def restore(
    app: FastAPI,
    upload: Path,
    *,
    drain_timeout: float = DRAIN_TIMEOUT_S,
    own_requests: int = 1,
    after_swap: Callable[[], None] | None = None,
) -> RestoreResult:
    """Replaces the live database with the backup at `upload`.

    Order: validate -> refuse during a build -> safety backup -> maintenance -> dispose
    engine, swap file, drop stale -wal/-shm -> migrate -> rotate key -> new db_epoch ->
    leave maintenance. Any failure after the swap starts restores the safety backup (and
    the old key) and re-raises as 500 RESTORE_FAILED; failures before it change nothing.

    `own_requests` is the number of in-flight requests to ignore while draining (the HTTP
    restore call itself; the CLI passes 0). `after_swap` is a test hook run right after
    the file was replaced.
    """
    settings = app.state.settings
    engine: Engine = app.state.engine
    maintenance: Maintenance = app.state.maintenance
    lock: threading.Lock = app.state.restore_lock
    if not lock.acquire(blocking=False):
        raise AppError(409, "RESTORE_IN_PROGRESS", MSG_RESTORE_RUNNING)
    try:
        revision = verify_backup(upload)
        if app.state.run_manager.is_busy():
            raise AppError(409, "BUILD_RUNNING", MSG_BUILD_RUNNING)

        stamp = utc_now().strftime("%Y%m%d-%H%M%S")
        safety = settings.data_dir / BACKUP_DIR_NAME / f"pre-restore-{stamp}.db"
        make_backup(engine, safety)

        if not maintenance.begin(own_requests, drain_timeout):
            raise AppError(409, "RESTORE_BUSY", MSG_RESTORE_BUSY)
        old_key: bytes = app.state.secret_key
        try:
            try:
                _swap(settings.db_path, upload, engine, after_swap)
                run_migrations(engine)
                _write_secret(settings.data_dir, secrets.token_hex(32).encode("ascii"))
                app.state.secret_key = load_or_create_secret(settings.data_dir)
                epoch = service.bump_db_epoch(engine) or ""
                if not _integrity_ok_engine(engine):
                    raise sqlite3.DatabaseError("integrity_check failed after restore")
            except BaseException as exc:
                log.error("restore failed; rolling back", extra={"error": type(exc).__name__})
                _rollback(app, safety, old_key)
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                raise AppError(500, "RESTORE_FAILED", MSG_RESTORE_FAILED) from exc
        finally:
            maintenance.end()
        log.info("restore done", extra={"revision": revision})
        return RestoreResult(safety_backup=safety, revision=revision, db_epoch=epoch)
    finally:
        lock.release()


def _integrity_ok_engine(engine: Engine) -> bool:
    raw = engine.raw_connection()
    try:
        con = raw.driver_connection
        assert isinstance(con, sqlite3.Connection)
        return _integrity_ok(con)
    finally:
        raw.close()


def _swap(
    db_path: Path, upload: Path, engine: Engine, after_swap: Callable[[], None] | None
) -> None:
    engine.dispose()  # closes every pooled connection; the drained app opens none meanwhile
    _drop_sidecars(db_path)
    staged = db_path.with_name(db_path.name + ".restoring")
    try:
        shutil.copyfile(upload, staged)
        os.replace(staged, db_path)
    finally:
        staged.unlink(missing_ok=True)
    if after_swap is not None:
        after_swap()


def _rollback(app: FastAPI, safety: Path, old_key: bytes) -> None:
    """Puts the safety backup and the old cookie key back. Never raises past logging."""
    settings = app.state.settings
    try:
        app.state.engine.dispose()
        _drop_sidecars(settings.db_path)
        staged = settings.db_path.with_name(settings.db_path.name + ".restoring")
        try:
            shutil.copyfile(safety, staged)
            os.replace(staged, settings.db_path)
        finally:
            staged.unlink(missing_ok=True)
        _write_secret(settings.data_dir, old_key)
        app.state.secret_key = old_key
    except Exception:  # noqa: BLE001
        log.exception("restore rollback failed; the safety backup is at %s", safety)
