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

import contextlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import Engine

from hoctap.api.errors import AppError
from hoctap.config import Settings
from hoctap.db.engine import head_revision, is_known_revision, run_migrations
from hoctap.ids import utc_now
from hoctap.parent import service
from hoctap.parent.auth import SECRET_FILE, load_or_create_secret

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
CONFIRM_PHRASE = "KHÔI PHỤC"
SQLITE_HEADER = b"SQLite format 3\x00"
DRAIN_TIMEOUT_S = 15.0
# A database-only backup is a few MB; this only stops a mistaken or hostile upload from
# filling the disk that holds the data.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
LOCK_FILE_NAME = "hoctap.lock"
RESTORE_MARKER_NAME = "restore.inprogress"
ROLLBACK_FAILED_MARKER_NAME = "restore.rollback_failed"

MSG_INVALID = "Tệp này không phải bản sao lưu hợp lệ. Không có gì bị thay đổi."
MSG_NEWER = (
    "Bản sao lưu này được tạo bởi phiên bản mới hơn của ứng dụng (%(theirs)s, ứng dụng hiện "
    "có %(ours)s). Hãy cập nhật ứng dụng trước. Không có gì bị thay đổi."
)
MSG_BUILD_RUNNING = (
    "Đang có lượt dựng nội dung chạy. Hãy đợi xong rồi khôi phục. Không có gì bị thay đổi."
)
MSG_DB_LOCKED = (
    "Có một tiến trình khác (dựng nội dung hoặc một lần khôi phục khác) đang dùng cơ sở dữ "
    "liệu. Hãy thử lại sau ít phút. Không có gì bị thay đổi."
)
MSG_TOO_LARGE = "Tệp quá lớn để là bản sao lưu. Không có gì bị thay đổi."
MSG_CONFIRM = "Cần gõ đúng cụm “KHÔI PHỤC” để xác nhận."
MSG_BACKUP_FAILED = "Không tạo được bản sao lưu."
MSG_RESTORE_FAILED = "Khôi phục không thành công; dữ liệu hiện tại đã được giữ nguyên."
MSG_RESTORE_BUSY = "Máy đang bận, chưa thể khôi phục. Hãy thử lại sau ít phút."
MSG_RESTORE_RUNNING = "Đang có một lần khôi phục khác."
MSG_MAINTENANCE = "Đang khôi phục dữ liệu. Vui lòng thử lại sau ít giây."


# --- Cross-process lock -------------------------------------------------------------
#
# `restore()` and the CLI builder (`hoctap build ...`, `hoctap restore`) are separate OS
# processes that can both end up writing to the same `db_path`. An in-process
# `threading.Lock` (`app.state.restore_lock`) cannot see across processes, so a build
# started right after restore's `is_busy()` check could still race `_swap()`. This file
# lock on a pidless lockfile under `data_dir` is the thing both sides actually share.


def _lock_fd(fd: int, *, blocking: bool) -> bool:
    if fcntl is not None:
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
            return True
        except OSError:
            if blocking:
                raise
            return False
    assert msvcrt is not None, "neither fcntl nor msvcrt is available"
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            if not blocking:
                return False
            time.sleep(0.05)


def _unlock_fd(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    assert msvcrt is not None, "neither fcntl nor msvcrt is available"
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def db_lock(data_dir: Path, *, blocking: bool) -> Iterator[bool]:
    """Exclusive, cross-process lock over `data_dir`'s database.

    The CLI builder holds it (`blocking=True`, waits) for as long as it has the database
    open and writing. `restore()` only tries it (`blocking=False`) right before `_swap()`,
    inside the maintenance window, so it fails fast instead of racing a build. Yields
    whether the lock was acquired -- always True when `blocking=True`.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / LOCK_FILE_NAME
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        acquired = _lock_fd(fd, blocking=blocking)
        try:
            yield acquired
        finally:
            if acquired:
                _unlock_fd(fd)
    finally:
        os.close(fd)


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
            # A valid SQLite header plus a correctly-stamped `alembic_version` is not
            # enough on its own -- a crafted file could have both and no real data. Check
            # for a table every real backup has.
            known_table = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'parent_settings'"
            ).fetchall()
            if not known_table:
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


# --- Crash recovery for a restore interrupted mid-swap -------------------------------
#
# Between `_swap()`'s `os.replace()` and the end of the rotate-key/bump-epoch block, a
# SIGKILL/OOM-kill/power-loss leaves `lifespan()`'s plain "open whatever is at db_path and
# migrate it" with no idea a restore was in flight. Worst case: the crash lands after the
# swap but before the key rotation, and the restored DB goes live with the OLD secret.key
# still valid. A marker written just before `_swap()` -- removed only once the whole
# restore (or its rollback) has finished -- lets `lifespan()` detect this and replay the
# rollback before anything else touches the database.


def _restore_marker_path(data_dir: Path) -> Path:
    return data_dir / RESTORE_MARKER_NAME


def _write_restore_marker(data_dir: Path, safety: Path, old_key: bytes) -> None:
    marker = _restore_marker_path(data_dir)
    tmp = marker.with_name(f"{RESTORE_MARKER_NAME}.{os.getpid()}.tmp")
    payload = json.dumps({"safety_backup": str(safety), "old_secret_key_hex": old_key.hex()})
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, marker)


def _clear_restore_marker(data_dir: Path) -> None:
    _restore_marker_path(data_dir).unlink(missing_ok=True)


def _write_rollback_failed_marker(data_dir: Path, safety: Path) -> None:
    """A rollback that itself failed is the one failure mode an operator must not miss by
    just not watching logs: leave a sentinel file alongside the data they can find later."""
    try:
        (data_dir / ROLLBACK_FAILED_MARKER_NAME).write_text(
            f"restore rollback failed at {utc_now().isoformat()}; "
            f"the safety backup is at {safety}\n",
            encoding="ascii",
        )
    except OSError:
        log.exception("could not even write the rollback-failed marker in %s", data_dir)


def _restore_file_and_key(settings: Settings, safety: Path, old_key: bytes) -> None:
    """Copies `safety` back over the live database and restores `old_key` as `secret.key`.
    Shared by in-process rollback (`_rollback`) and startup crash-recovery
    (`replay_interrupted_restore`); never touches `app.state` so both can call it."""
    _drop_sidecars(settings.db_path)
    staged = settings.db_path.with_name(settings.db_path.name + ".restoring")
    try:
        shutil.copyfile(safety, staged)
        os.replace(staged, settings.db_path)
    finally:
        staged.unlink(missing_ok=True)
    _write_secret(settings.data_dir, old_key)


def replay_interrupted_restore(settings: Settings) -> bool:
    """Called once at startup, before the database is opened. If `restore.inprogress` is
    present, a previous restore was interrupted mid-swap by something `restore()`'s own
    `except BaseException` could not catch (a real process kill). Replays the rollback --
    safety backup back over the live file, old `secret.key` restored -- so the app never
    boots with a half-swapped database or (narrower, but real) a stale un-rotated key.
    Returns True if a rollback was replayed; raises if the marker is present but the
    rollback itself cannot be completed, since starting up on an unknown-state database
    is worse than refusing to start.
    """
    marker = _restore_marker_path(settings.data_dir)
    if not marker.is_file():
        return False
    log.warning("found %s; a restore was interrupted, replaying its rollback", marker)
    safety = marker  # fallback for the sentinel message if parsing itself fails
    try:
        payload = json.loads(marker.read_text(encoding="ascii"))
        safety = Path(payload["safety_backup"])
        old_key = bytes.fromhex(payload["old_secret_key_hex"])
        if not safety.is_file():
            raise FileNotFoundError(f"safety backup missing: {safety}")
        _restore_file_and_key(settings, safety, old_key)
    except Exception:
        log.exception("could not replay the interrupted restore; marker left at %s", marker)
        _write_rollback_failed_marker(settings.data_dir, safety)
        raise
    marker.unlink(missing_ok=True)
    log.warning("replayed the interrupted restore's rollback; safety backup was %s", safety)
    return True


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

    Order: validate -> refuse during a build -> safety backup -> maintenance -> re-check
    busy and take the cross-process db lock -> write the `restore.inprogress` marker ->
    dispose engine, swap file, drop stale -wal/-shm -> migrate -> rotate key -> new
    db_epoch -> clear the marker -> leave maintenance. Any failure after the swap starts
    restores the safety backup (and the old key) and re-raises as 500 RESTORE_FAILED;
    failures before it change nothing.

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
        try:
            # The early `is_busy()` check above can be stale by now: `make_backup()` and
            # the drain in `maintenance.begin()` both take real time, long enough for a
            # separate `hoctap build` process to start writing. Re-check right here, at
            # the last possible moment before the file is touched, and take the same
            # filesystem lock the CLI builder holds for as long as it writes -- a failed
            # non-blocking acquire means a build (or another restore) is active right now,
            # a window the DB-row check alone cannot close.
            with db_lock(settings.data_dir, blocking=False) as locked:
                if not locked or app.state.run_manager.is_busy():
                    raise AppError(409, "DB_LOCKED", MSG_DB_LOCKED)
                old_key: bytes = app.state.secret_key
                _write_restore_marker(settings.data_dir, safety, old_key)
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
                        log.error(
                            "restore failed; rolling back", extra={"error": type(exc).__name__}
                        )
                        _rollback(app, safety, old_key)
                        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                            raise
                        raise AppError(500, "RESTORE_FAILED", MSG_RESTORE_FAILED) from exc
                finally:
                    _clear_restore_marker(settings.data_dir)
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
    """Puts the safety backup and the old cookie key back. Never raises past logging; on
    failure also leaves a sentinel file, since an operator not watching logs otherwise has
    nothing but the original 500 to go on."""
    settings = app.state.settings
    try:
        app.state.engine.dispose()
        _restore_file_and_key(settings, safety, old_key)
        app.state.secret_key = old_key
    except Exception:  # noqa: BLE001
        log.exception("restore rollback failed; the safety backup is at %s", safety)
        _write_rollback_failed_marker(settings.data_dir, safety)
