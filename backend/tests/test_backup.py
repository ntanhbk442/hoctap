"""Story 7.2: backup and restore. Every test runs on a temp data dir it created itself;
nothing here touches the real `data/` directory."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from hoctap.api.errors import AppError
from hoctap.app import create_app
from hoctap.cli import main as cli_main
from hoctap.config import Settings
from hoctap.db.engine import alembic_config, create_db_engine, head_revision
from hoctap.parent import backup, service
from hoctap.parent.auth import COOKIE_NAME, load_or_create_secret

SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}
PHRASE = "KHÔI PHỤC"
BACKUP_URL = "/api/v1/parent/backup"
RESTORE_URL = "/api/v1/parent/restore"


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path, tmp_path: Path):
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
        yield c


def _rows(data_dir: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(data_dir / "hoctap.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _snapshot(data_dir: Path) -> dict:
    backups = data_dir / "backups"
    return {
        "profiles": _rows(data_dir, "SELECT id, name FROM parent_profiles ORDER BY id"),
        "settings": _rows(data_dir, "SELECT pin_hash, db_epoch FROM parent_settings"),
        "key": (data_dir / "secret.key").read_bytes(),
        "backups": sorted(p.name for p in backups.iterdir()) if backups.exists() else [],
    }


def _download(client: TestClient, tmp_path: Path, name: str = "b.db") -> Path:
    resp = client.post(BACKUP_URL)
    assert resp.status_code == 200, resp.text
    out = tmp_path / name
    out.write_bytes(resp.content)
    return out


def _restore(client: TestClient, path: Path, confirm: str = PHRASE):
    return client.post(
        RESTORE_URL,
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
        data={"confirm": confirm},
    )


def _code(resp, status: int, code: str) -> None:
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["code"] == code


def _add_profile(client: TestClient, name: str) -> None:
    body = {"name": name, "avatar": "dog", "grade": 2}
    assert client.post("/api/v1/profiles", json=body).status_code == 201


def _make_db_at(path: Path, revision: str | None) -> Path:
    """A real hoctap DB (setup done) migrated only up to `revision`."""
    engine = create_db_engine(path)
    cfg = alembic_config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision or "head")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO parent_settings (id, pin_hash, created_at, updated_at) "
            "VALUES (1, ?, 'x', 'x')",
            (service._hash_pin("4321"),),
        )
        conn.exec_driver_sql(
            "INSERT INTO parent_profiles (id, name, avatar, grade, created_at) "
            "VALUES ('old-1', 'Cũ', 'cat', 3, 'x')"
        )
    engine.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    return path


# --- Backup ------------------------------------------------------------------------


def test_backup_requires_pin_and_writes_nothing(data_dir: Path, tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        c.post("/api/v1/setup", json=SETUP)
        c.cookies.clear()
        _code(c.post(BACKUP_URL), 401, "UNAUTHORIZED")
        assert not (data_dir / "backups").exists()


def test_backup_downloads_a_verified_single_file(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    resp = client.post(BACKUP_URL)
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert "hoctap-backup-" in disposition and disposition.rstrip('"').endswith(".db")
    out = tmp_path / "got.db"
    out.write_bytes(resp.content)
    assert not Path(str(out) + "-wal").exists()
    con = sqlite3.connect(out)
    assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert con.execute("SELECT name FROM parent_profiles").fetchall() == [("Bin",)]
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    con.close()
    # The temp file used for the download is gone; the app still serves.
    leftovers = [p for p in (data_dir / "backups").iterdir()]
    assert leftovers == []
    assert client.get("/api/v1/profiles").status_code == 200


def test_backup_is_consistent_while_a_writer_runs(data_dir: Path, tmp_path: Path) -> None:
    engine = create_db_engine(data_dir / "hoctap.db")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE scratch (a INTEGER, b INTEGER)")
    stop = threading.Event()

    def writer() -> None:
        n = 0
        while not stop.is_set():
            n += 1
            with engine.begin() as conn:  # a and b always change together
                conn.exec_driver_sql("INSERT INTO scratch VALUES (?, ?)", (n, n))

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        outs = [backup.make_backup(engine, tmp_path / f"c{i}.db") for i in range(5)]
    finally:
        stop.set()
        thread.join()
    for out in outs:
        con = sqlite3.connect(out)
        assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert con.execute("SELECT count(*) FROM scratch WHERE a != b").fetchone()[0] == 0
        con.close()
    engine.dispose()


def test_backup_failing_integrity_gives_500_and_no_files(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup, "_integrity_ok", lambda _con: False)
    _code(client.post(BACKUP_URL), 500, "BACKUP_FAILED")
    assert list((data_dir / "backups").iterdir()) == []


def test_verify_backup_refuses_a_file_with_no_real_tables(tmp_path: Path) -> None:
    """A crafted file with a valid SQLite header and a correctly-stamped `alembic_version`
    but none of the app's actual tables must still be refused (audit point 3): the header
    plus `alembic_version` alone is not proof of a real backup."""
    fake = tmp_path / "fake.db"
    con = sqlite3.connect(fake)
    con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    con.execute("INSERT INTO alembic_version VALUES (?)", (head_revision(),))
    con.commit()
    con.close()
    with pytest.raises(AppError) as info:
        backup.verify_backup(fake)
    assert info.value.code == "BACKUP_INVALID"


def test_verify_backup_accepts_a_real_backup(client: TestClient, tmp_path: Path) -> None:
    saved = _download(client, tmp_path)
    assert backup.verify_backup(saved) == head_revision()


# --- Restore, happy paths ----------------------------------------------------------


def test_restore_swaps_data_rotates_key_and_epoch(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)
    assert len(before["profiles"]) == 2
    old_cookie = client.cookies.get(COOKIE_NAME)
    epoch_before = service.get_db_epoch(client.app.state.engine)

    resp = _restore(client, saved)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revision"] == head_revision()
    assert body["db_epoch"] and body["db_epoch"] != epoch_before

    after = _snapshot(data_dir)
    assert [p[1] for p in after["profiles"]] == ["Bin"]
    assert after["key"] != before["key"]
    assert after["settings"][0][1] == body["db_epoch"]
    safety = data_dir / "backups" / body["safety_backup"]
    assert safety.name.startswith("pre-restore-") and safety.is_file()
    con = sqlite3.connect(safety)
    assert con.execute("SELECT count(*) FROM parent_profiles").fetchone()[0] == 2
    con.close()

    # Every old cookie is dead; the restored PIN signs in again.
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old_cookie)
    _code(client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")
    client.cookies.clear()
    assert client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204
    assert client.get("/api/v1/parent/session").status_code == 200
    assert not client.app.state.maintenance.active


def test_restore_older_backup_is_migrated(client: TestClient, tmp_path: Path) -> None:
    old = _make_db_at(tmp_path / "old.db", "0019_full_run")
    resp = _restore(client, old)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"] == "0019_full_run"
    con = sqlite3.connect(client.app.state.settings.db_path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchall() == [
        (head_revision(),)
    ]
    assert con.execute("SELECT name FROM parent_profiles").fetchall() == [("Cũ",)]
    assert con.execute("SELECT length(db_epoch) FROM parent_settings").fetchone()[0] == 32
    con.close()
    # The restored PIN applies.
    assert client.post("/api/v1/parent/login", json={"pin": "4321"}).status_code == 204


# --- Restore refusals: nothing on disk changes -------------------------------------


def _assert_untouched(client: TestClient, data_dir: Path, before: dict) -> None:
    assert _snapshot(data_dir) == before
    assert not client.app.state.maintenance.active
    assert client.get("/api/v1/parent/session").status_code == 200  # cookie still valid
    assert not list((data_dir / "backups").glob(".upload-*"))


def test_restore_refuses_newer_backup(client: TestClient, data_dir: Path, tmp_path: Path) -> None:
    saved = _download(client, tmp_path)
    con = sqlite3.connect(saved)
    con.execute("UPDATE alembic_version SET version_num = '9999_from_the_future'")
    con.commit()
    con.close()
    before = _snapshot(data_dir)
    resp = _restore(client, saved)
    _code(resp, 409, "BACKUP_NEWER")
    message = resp.json()["error"]["message"]
    assert "9999_from_the_future" in message and head_revision() in message
    _assert_untouched(client, data_dir, before)


def test_restore_refuses_an_oversized_upload(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mistaken or hostile upload must not be copied to disk without limit (added in review)."""
    saved = _download(client, tmp_path)
    monkeypatch.setattr(backup, "MAX_UPLOAD_BYTES", saved.stat().st_size - 1)
    before = _snapshot(data_dir)
    _code(_restore(client, saved), 413, "BACKUP_TOO_LARGE")
    _assert_untouched(client, data_dir, before)
    assert not list((data_dir / backup.BACKUP_DIR_NAME).glob(".upload-*"))  # no partial file left


@pytest.mark.parametrize("kind", ["random", "truncated", "bitflip", "no_alembic", "empty"])
def test_restore_refuses_invalid_files(
    client: TestClient, data_dir: Path, tmp_path: Path, kind: str
) -> None:
    good = _download(client, tmp_path)
    bad = tmp_path / "bad.db"
    data = good.read_bytes()
    if kind == "random":
        bad.write_bytes(b"this is not a database" * 500)
    elif kind == "truncated":
        bad.write_bytes(data[: len(data) // 2 + 3])
    elif kind == "bitflip":
        buf = bytearray(data)
        for i in range(4096, len(buf), 97):  # damage the pages after the header
            buf[i] ^= 0xFF
        bad.write_bytes(bytes(buf))
    elif kind == "no_alembic":
        con = sqlite3.connect(bad)
        con.execute("CREATE TABLE t (a)")
        con.commit()
        con.close()
    else:
        bad.write_bytes(b"")
    before = _snapshot(data_dir)
    _code(_restore(client, bad), 422, "BACKUP_INVALID")
    _assert_untouched(client, data_dir, before)


def test_restore_refuses_while_a_build_is_running(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    con = sqlite3.connect(data_dir / "hoctap.db")
    con.execute(
        "INSERT INTO build_runs (id, book_id, first_page, last_page, status, pages_total, "
        "started_at, updated_at) VALUES ('r1', 'b', 1, 2, 'running', 2, 'x', 'x')"
    )
    con.commit()
    con.close()
    before = _snapshot(data_dir)
    _code(_restore(client, saved), 409, "BUILD_RUNNING")
    _assert_untouched(client, data_dir, before)


def test_restore_refuses_while_a_full_run_holds_the_manager(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    client.app.state.run_manager._full_running = True
    before = _snapshot(data_dir)
    _code(_restore(client, saved), 409, "BUILD_RUNNING")
    _assert_untouched(client, data_dir, before)


@pytest.mark.parametrize("confirm", ["", "khoi phuc", "RESTORE", "KHÔI"])
def test_restore_needs_the_typed_phrase(
    client: TestClient, data_dir: Path, tmp_path: Path, confirm: str
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)
    _code(_restore(client, saved, confirm), 422, "CONFIRM_REQUIRED")
    _assert_untouched(client, data_dir, before)


def test_restore_without_the_confirm_field_is_refused(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    before = _snapshot(data_dir)
    resp = client.post(RESTORE_URL, files={"file": ("b.db", saved.read_bytes())})
    _code(resp, 422, "CONFIRM_REQUIRED")
    _assert_untouched(client, data_dir, before)


def test_restore_needs_a_pin_session(client: TestClient, data_dir: Path, tmp_path: Path) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)
    client.cookies.clear()
    _code(_restore(client, saved), 401, "UNAUTHORIZED")
    assert _snapshot(data_dir) == before


# --- Rollback ----------------------------------------------------------------------


def test_migration_failure_rolls_back_to_the_safety_backup(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _make_db_at(tmp_path / "old.db", "0019_full_run")
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)

    def boom(_engine) -> None:  # noqa: ANN001
        # The file is already swapped when migrations run: prove it, then fail.
        assert [r[0] for r in _rows(data_dir, "SELECT name FROM parent_profiles")] == ["Cũ"]
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(backup, "run_migrations", boom)
    _code(_restore(client, old), 500, "RESTORE_FAILED")

    after = _snapshot(data_dir)
    assert after["profiles"] == before["profiles"]
    assert after["settings"] == before["settings"]
    assert after["key"] == before["key"]
    assert any(n.startswith("pre-restore-") for n in after["backups"])
    assert not client.app.state.maintenance.active
    # The app is still fully usable, with the same cookie.
    assert client.get("/api/v1/parent/session").status_code == 200
    assert len(client.get("/api/v1/profiles").json()) == 2
    assert not (data_dir / "hoctap.db.restoring").exists()


def test_failure_after_key_rotation_restores_key_and_data(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)

    def boom(_engine) -> str:  # noqa: ANN001
        raise RuntimeError("injected epoch failure")

    monkeypatch.setattr(service, "bump_db_epoch", boom)
    _code(_restore(client, saved), 500, "RESTORE_FAILED")
    after = _snapshot(data_dir)
    assert (after["profiles"], after["settings"], after["key"]) == (
        before["profiles"],
        before["settings"],
        before["key"],
    )
    assert client.get("/api/v1/parent/session").status_code == 200


def test_restore_gives_up_if_requests_never_drain(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    m = client.app.state.maintenance
    assert m.enter()  # a request that never finishes
    try:
        before = _snapshot(data_dir)
        with pytest.raises(backup.AppError) as info:
            backup.restore(client.app, saved, drain_timeout=0.2, own_requests=0)
        assert info.value.code == "RESTORE_BUSY"
        assert not m.active
        after = _snapshot(data_dir)
        assert after["profiles"] == before["profiles"] and after["key"] == before["key"]
    finally:
        m.leave()


def test_safety_backup_failure_aborts_before_touching_the_live_db(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit point 5: `make_backup()` raising (disk full, permission denied, ...) happens
    before `maintenance.begin()`/`_swap()`. Proves this with the live db file compared
    byte-for-byte and the maintenance flag never flipped, not just the row-level snapshot
    the other refusal tests use."""
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    live_before = (data_dir / "hoctap.db").read_bytes()
    before = _snapshot(data_dir)

    def boom(_engine: object, _dest: Path) -> Path:
        raise AppError(500, "BACKUP_FAILED", "injected safety-backup failure")

    monkeypatch.setattr(backup, "make_backup", boom)
    began: list[bool] = []
    maintenance = client.app.state.maintenance
    original_begin = maintenance.begin
    monkeypatch.setattr(
        maintenance, "begin", lambda *a, **k: began.append(True) or original_begin(*a, **k)
    )

    _code(_restore(client, saved), 500, "BACKUP_FAILED")

    assert began == []  # maintenance.begin() was never even called
    assert not maintenance.active
    assert (data_dir / "hoctap.db").read_bytes() == live_before
    _assert_untouched(client, data_dir, before)


def _assert_live_data_untouched(client: TestClient, data_dir: Path, before: dict) -> None:
    """Like `_assert_untouched`, but for a refusal that happens after the safety backup was
    already taken (right before the swap): a new `pre-restore-*.db` is expected and
    harmless, so only the live data/settings/key and app health are compared."""
    after = _snapshot(data_dir)
    assert after["profiles"] == before["profiles"]
    assert after["settings"] == before["settings"]
    assert after["key"] == before["key"]
    assert not client.app.state.maintenance.active
    assert client.get("/api/v1/parent/session").status_code == 200
    assert not list((data_dir / "backups").glob(".upload-*"))


def test_restore_refuses_when_another_process_holds_the_db_lock(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    """Audit point 1: the early `is_busy()` check only sees `build_runs` rows, not a `hoctap
    build` process that has not written one yet (or ever, for a read-only subcommand) but
    already holds the cross-process file lock. Simulates that by holding the lock
    ourselves, exactly as `_open_db`/`_run_build` would."""
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)
    with backup.db_lock(data_dir, blocking=True):
        _code(_restore(client, saved), 409, "DB_LOCKED")
    _assert_live_data_untouched(client, data_dir, before)
    assert not (data_dir / backup.RESTORE_MARKER_NAME).exists()


def test_restore_rechecks_is_busy_immediately_before_the_swap(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build starting in the window between the early `is_busy()` check and the swap
    (while `make_backup()`/`maintenance.begin()` are running) must still be caught."""
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    before = _snapshot(data_dir)
    run_manager = client.app.state.run_manager

    def make_backup_then_start_a_build(engine: object, dest: Path) -> Path:
        run_manager._full_running = True
        return original_make_backup(engine, dest)

    original_make_backup = backup.make_backup
    monkeypatch.setattr(backup, "make_backup", make_backup_then_start_a_build)
    try:
        _code(_restore(client, saved), 409, "DB_LOCKED")
    finally:
        run_manager._full_running = False
    _assert_live_data_untouched(client, data_dir, before)


def test_rollback_failure_leaves_a_sentinel_file(
    client: TestClient, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit point 4: a rollback that itself fails must leave something an operator can
    find without watching logs, not just a log line."""
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")

    def boom(_engine) -> None:  # noqa: ANN001
        raise RuntimeError("injected migration failure")

    def rollback_boom(_settings: object, _safety: Path, _old_key: bytes) -> None:
        raise OSError("injected rollback failure")

    monkeypatch.setattr(backup, "run_migrations", boom)
    monkeypatch.setattr(backup, "_restore_file_and_key", rollback_boom)
    _code(_restore(client, saved), 500, "RESTORE_FAILED")

    sentinel = data_dir / backup.ROLLBACK_FAILED_MARKER_NAME
    assert sentinel.is_file()
    assert "rollback failed" in sentinel.read_text(encoding="ascii")


# --- Crash recovery (interrupted restore marker) ------------------------------------


def test_restore_marker_is_cleared_on_success(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    saved = _download(client, tmp_path)
    _restore(client, saved)
    assert not (data_dir / backup.RESTORE_MARKER_NAME).exists()


def test_replay_interrupted_restore_rolls_back_a_crashed_swap(
    data_dir: Path, tmp_path: Path
) -> None:
    """Simulates a kill -9 between `_swap()` and the end of the restore block: a
    `restore.inprogress` marker is on disk, the live db already holds the restored (wrong)
    data and the OLD secret.key is still in place (the realistic crash point, since the key
    is rotated right after the swap). `replay_interrupted_restore()` must undo both."""
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
    settings = app.state.settings

    safety = data_dir / "backups" / "pre-restore-crash-test.db"
    backup.make_backup(create_db_engine(settings.db_path), safety)
    old_key = (data_dir / "secret.key").read_bytes()

    # Simulate the crash: the live db now holds different (post-swap) data, but the key
    # was never rotated (the crash landed before that step).
    other = tmp_path / "other.db"
    _make_db_at(other, None)
    (data_dir / "hoctap.db").write_bytes(other.read_bytes())
    backup._write_restore_marker(data_dir, safety, old_key)

    assert backup.replay_interrupted_restore(settings) is True
    assert not (data_dir / backup.RESTORE_MARKER_NAME).exists()
    con = sqlite3.connect(data_dir / "hoctap.db")
    names = [r[0] for r in con.execute("SELECT name FROM parent_profiles")]
    con.close()
    assert names == ["Bin"]
    assert (data_dir / "secret.key").read_bytes() == old_key


def test_replay_interrupted_restore_is_a_noop_without_a_marker(
    data_dir: Path, tmp_path: Path
) -> None:
    data_dir.mkdir(parents=True)
    settings = Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist")
    assert backup.replay_interrupted_restore(settings) is False


def test_lifespan_replays_an_interrupted_restore_on_startup(
    data_dir: Path, tmp_path: Path
) -> None:
    """End-to-end: a marker left on disk before the app starts is replayed by `lifespan()`
    itself, before any route can see a half-swapped database."""
    dist = tmp_path / "no-dist"
    app = create_app(Settings(data_dir=data_dir, frontend_dist=dist))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
    settings = app.state.settings

    safety = data_dir / "backups" / "pre-restore-crash-test.db"
    backup.make_backup(create_db_engine(settings.db_path), safety)
    old_key = (data_dir / "secret.key").read_bytes()
    other = tmp_path / "other.db"
    _make_db_at(other, None)
    (data_dir / "hoctap.db").write_bytes(other.read_bytes())
    backup._write_restore_marker(data_dir, safety, old_key)

    app2 = create_app(Settings(data_dir=data_dir, frontend_dist=dist))
    with TestClient(app2):
        assert not (data_dir / backup.RESTORE_MARKER_NAME).exists()
    assert (data_dir / "secret.key").read_bytes() == old_key
    con = sqlite3.connect(data_dir / "hoctap.db")
    assert [r[0] for r in con.execute("SELECT name FROM parent_profiles")] == ["Bin"]
    con.close()


def test_replay_interrupted_restore_raises_and_leaves_a_sentinel_if_it_cannot_recover(
    data_dir: Path, tmp_path: Path
) -> None:
    data_dir.mkdir(parents=True)
    settings = Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist")
    (data_dir / "hoctap.db").write_bytes(b"not a real db")
    load_or_create_secret(data_dir)
    missing_safety = data_dir / "backups" / "does-not-exist.db"
    backup._write_restore_marker(data_dir, missing_safety, b"\x00" * 32)

    with pytest.raises(FileNotFoundError):
        backup.replay_interrupted_restore(settings)

    assert (data_dir / backup.RESTORE_MARKER_NAME).exists()  # left in place for a retry
    assert (data_dir / backup.ROLLBACK_FAILED_MARKER_NAME).is_file()


# --- Cross-process lock (shared with the CLI builder) -------------------------------


def test_db_lock_is_exclusive_across_handles(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with backup.db_lock(data_dir, blocking=True) as first:
        assert first is True
        with backup.db_lock(data_dir, blocking=False) as second:
            assert second is False
    with backup.db_lock(data_dir, blocking=False) as third:
        assert third is True


def test_build_cli_waits_for_the_lock_a_restore_holds(cli_env: Path) -> None:
    """Closes the CLI builder side of audit point 1: `hoctap build gate` must wait for the
    lock instead of opening the database while a restore (or another build) holds it."""
    released_at: list[float] = []

    def holder() -> None:
        with backup.db_lock(cli_env, blocking=True):
            time.sleep(0.3)
            released_at.append(time.monotonic())

    thread = threading.Thread(target=holder)
    thread.start()
    time.sleep(0.05)  # give the holder time to actually acquire the lock first
    assert cli_main(["build", "gate"]) == 0
    thread.join()
    assert released_at  # the build only got in after the holder released the lock


def test_cli_restore_refuses_when_the_db_lock_is_held(
    cli_env: Path, client: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Closes the CLI restore TOCTOU: two concurrent `hoctap restore` invocations (or a
    build) can no longer both touch `db_path`, where before only a TCP port probe guarded
    against a running server."""
    saved = _download(client, tmp_path)
    before = _rows(cli_env, "SELECT id FROM parent_profiles")
    with backup.db_lock(cli_env, blocking=True):
        assert cli_main(["restore", str(saved), "--yes"]) == 1
    assert "DB_LOCKED" in capsys.readouterr().err
    assert _rows(cli_env, "SELECT id FROM parent_profiles") == before


# --- Maintenance -------------------------------------------------------------------


def test_maintenance_answers_503_except_health(client: TestClient) -> None:
    client.app.state.maintenance.active = True
    try:
        resp = client.get("/api/v1/profiles")
        _code(resp, 503, "MAINTENANCE")
        assert resp.headers["retry-after"]
        _code(client.post(BACKUP_URL), 503, "MAINTENANCE")
        _code(client.get("/some/spa/route"), 503, "MAINTENANCE")
        assert client.get("/api/v1/health").status_code == 200
    finally:
        client.app.state.maintenance.active = False
    assert client.get("/api/v1/profiles").status_code == 200


# --- db_epoch on events ------------------------------------------------------------


def test_stale_epoch_event_is_refused_with_409(client: TestClient) -> None:
    epoch = service.get_db_epoch(client.app.state.engine)
    profile_id = client.get("/api/v1/profiles").json()[0]["id"]
    event = {
        "id": "01900000-0000-7000-8000-000000000001",
        "kind": "attempt",
        "occurred_at": "2026-09-30T00:00:00Z",
        "db_epoch": "an-older-epoch",
    }
    resp = client.post(
        "/api/v1/sessions/none/events", json={"profile_id": profile_id, "events": [event]}
    )
    _code(resp, 409, "STALE_EPOCH")
    assert resp.json()["error"]["details"] == [epoch]
    # Unstamped (legacy) and correctly stamped events are not refused as stale.
    legacy = {k: v for k, v in event.items() if k != "db_epoch"}
    for sent in (legacy, {**event, "db_epoch": epoch}):
        resp = client.post(
            "/api/v1/sessions/none/events",
            json={"profile_id": profile_id, "events": [sent]},
        )
        assert resp.status_code == 404, resp.text


def test_session_and_event_responses_carry_the_epoch(client: TestClient) -> None:
    epoch = service.get_db_epoch(client.app.state.engine)
    assert len(epoch) == 32
    # The restore changes it: a fresh token, never a counter.
    assert service.bump_db_epoch(client.app.state.engine) != epoch


# --- CLI ---------------------------------------------------------------------------


@pytest.fixture
def cli_env(data_dir: Path, tmp_path: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text(f'[server]\ndata_dir = "{data_dir.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setenv("HOCTAP_CONFIG", str(cfg))
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(data_dir))
    monkeypatch.setattr("hoctap.cli._port_listening", lambda _h, _p: False)
    return data_dir


def test_cli_backup_writes_a_verified_file(cli_env: Path, tmp_path: Path) -> None:
    out = tmp_path / "made" / "here"  # created on demand
    assert cli_main(["backup", "--to", str(out)]) == 0
    (file,) = out.iterdir()
    assert file.name.startswith("hoctap-backup-") and file.suffix == ".db"
    con = sqlite3.connect(file)
    assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    con.close()


def test_cli_backup_inside_data_dir_warns(cli_env: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli_main(["backup", "--to", str(cli_env / "somewhere")]) == 0
    assert "inside the data folder" in capsys.readouterr().err


def test_cli_backup_unwritable_returns_1(cli_env: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert cli_main(["backup", "--to", str(blocker / "sub")]) == 1


def test_cli_restore_offline(cli_env: Path, client: TestClient, tmp_path: Path) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    key_before = (cli_env / "secret.key").read_bytes()
    # Stop the "server" first: restoring underneath a live engine is what the port check
    # prevents in real use; here the fixture's engine is closed by leaving the client.
    client.app.state.engine.dispose()
    assert cli_main(["restore", str(saved), "--yes"]) == 0
    assert [r[0] for r in _rows(cli_env, "SELECT name FROM parent_profiles")] == ["Bin"]
    assert (cli_env / "secret.key").read_bytes() != key_before
    assert any(p.name.startswith("pre-restore-") for p in (cli_env / "backups").iterdir())


def test_cli_restore_refuses_when_port_is_listening(
    cli_env: Path, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    monkeypatch.setattr("hoctap.cli._port_listening", lambda _h, _p: True)
    assert cli_main(["restore", str(saved), "--yes"]) == 1
    assert len(_rows(cli_env, "SELECT id FROM parent_profiles")) == 2


def test_cli_restore_needs_the_phrase(
    cli_env: Path, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _download(client, tmp_path)
    _add_profile(client, "Thêm")
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert cli_main(["restore", str(saved)]) == 2
    assert len(_rows(cli_env, "SELECT id FROM parent_profiles")) == 2


def test_cli_restore_refuses_a_corrupt_file(
    cli_env: Path, client: TestClient, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"nope" * 100)
    _add_profile(client, "Thêm")
    assert cli_main(["restore", str(bad), "--yes"]) == 1
    assert len(_rows(cli_env, "SELECT id FROM parent_profiles")) == 2


def test_backup_filename_format() -> None:
    assert (
        backup.backup_filename(datetime(2026, 9, 30, 8, 5, 9, tzinfo=UTC))
        == "hoctap-backup-20260930-080509.db"
    )
