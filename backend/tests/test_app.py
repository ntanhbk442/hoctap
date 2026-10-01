"""Covers every row of the Story 1.1 I/O matrix plus config and CLI basics."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from hoctap.api.errors import AppError
from hoctap.app import create_app
from hoctap.cli import main as cli_main
from hoctap.config import ConfigError, Settings, load_settings
from hoctap.db.engine import alembic_config, create_db_engine
from hoctap.ids import new_id, to_iso, utc_now

INDEX_HTML = "<!doctype html><html><body><div id='root'>Học Tập</div></body></html>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (d / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    return d


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "fresh" / "data"


@pytest.fixture
def client(data_dir: Path, dist: Path):
    app = create_app(Settings(data_dir=data_dir, frontend_dist=dist))
    with TestClient(app) as c:
        yield c


def _assert_envelope(resp, status: int, code: str) -> None:
    assert resp.status_code == status
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


# --- Health -------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.1.0"}


# --- SPA route ----------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/some/client/route", "/parent/review"])
def test_spa_routes_serve_index(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Học Tập" in resp.text


def test_static_files_served(client: TestClient) -> None:
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
    assert client.get("/manifest.webmanifest").status_code == 200


def test_missing_asset_is_404_not_index(client: TestClient) -> None:
    _assert_envelope(client.get("/assets/missing.js"), 404, "NOT_FOUND")


def test_path_traversal_blocked(client: TestClient) -> None:
    resp = client.get("/..%2Fsecret.txt")
    assert resp.status_code == 404
    assert "nope" not in resp.text


def test_dotted_client_route_serves_index(client: TestClient) -> None:
    resp = client.get("/lesson/1.2")
    assert resp.status_code == 200
    assert "Học Tập" in resp.text


def test_nul_byte_path_is_404(client: TestClient) -> None:
    _assert_envelope(client.get("/a%00b"), 404, "NOT_FOUND")


@pytest.mark.parametrize("path", ["/", "/sw.js", "/manifest.webmanifest"])
def test_no_cache_on_shell_files(client: TestClient, dist: Path, path: str) -> None:
    (dist / "sw.js").write_text("// sw", encoding="utf-8")
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cacheable(client: TestClient) -> None:
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "cache-control" not in resp.headers


# --- Unknown API ----------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/nope", "/api/v1/nope/deeper", "/api", "/api/v2/x"])
def test_unknown_api_is_json_404(client: TestClient, path: str) -> None:
    resp = client.get(path)
    _assert_envelope(resp, 404, "NOT_FOUND")
    assert "<html" not in resp.text.lower()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/v1/nope", "/api"])
def test_unknown_api_other_method_is_json_404(client: TestClient, method: str, path: str) -> None:
    _assert_envelope(client.request(method, path), 404, "NOT_FOUND")


def test_wrong_method_on_known_api_is_json_405(client: TestClient) -> None:
    _assert_envelope(client.post("/api/v1/health"), 405, "METHOD_NOT_ALLOWED")


# --- Error handlers ---------------------------------------------------------------


def test_app_error_and_unhandled_error_envelopes(data_dir: Path, dist: Path) -> None:
    app = create_app(Settings(data_dir=data_dir, frontend_dist=dist))

    @app.get("/api/v1/_test/conflict")
    def conflict() -> None:
        raise AppError(409, "X_CONFLICT", "m")

    @app.get("/api/v1/_test/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    # Test routes are added after the SPA catch-all, so move them in front of it.
    app.router.routes.sort(key=lambda r: not getattr(r, "path", "").startswith("/api/v1/_test"))

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/_test/conflict")
        _assert_envelope(resp, 409, "X_CONFLICT")
        assert resp.json()["error"]["message"] == "m"
        _assert_envelope(c.get("/api/v1/_test/boom"), 500, "INTERNAL_ERROR")


# --- No build -------------------------------------------------------------------


def test_no_build_returns_503(
    tmp_path: Path, data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "missing-dist"))
    with TestClient(app) as c:
        with caplog.at_level("WARNING"):
            _assert_envelope(c.get("/"), 503, "FRONTEND_NOT_BUILT")
            _assert_envelope(c.get("/some/client/route"), 503, "FRONTEND_NOT_BUILT")
        # The API still works without a frontend build.
        assert c.get("/api/v1/health").status_code == 200
        _assert_envelope(c.get("/api/v1/nope"), 404, "NOT_FOUND")
    assert any("frontend not built" in r.getMessage() for r in caplog.records)
    log_lines = (data_dir / "logs" / "hoctap.log").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["message"] == "frontend not built" for line in log_lines)


# --- Fresh data dir ---------------------------------------------------------------


def test_fresh_data_dir_created_with_wal_and_migrations(data_dir: Path, dist: Path) -> None:
    assert not data_dir.exists()
    app = create_app(Settings(data_dir=data_dir, frontend_dist=dist))
    with TestClient(app):
        pass
    db = data_dir / "hoctap.db"
    assert db.is_file()
    assert (data_dir / "logs" / "hoctap.log").is_file()
    con = sqlite3.connect(db)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("SELECT version_num FROM alembic_version").fetchall() == [
            ("0020_db_epoch",)
        ]
        columns = {r[1] for r in con.execute("PRAGMA table_info(parent_profiles)")}
        assert "auto_play" in columns
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {
            "alembic_version",
            "parent_settings",
            "parent_profiles",
            "content_catalog_books",
            "build_jobs",
            "build_costs",
            "build_page_results",
            "content_catalog_units",
            "content_catalog_lessons",
            "content_catalog_problems",
            "content_review_concept_proposals",
            "content_review_problem_proposals",
            "content_review_overrides",
            "content_review_status",
            "content_review_error_reports",
            "content_review_concepts",
            "content_review_problem_concepts",
            "build_gate",
            "content_review_spot_check_samples",
            "content_review_spot_checks",
            "build_runs",
            "progress_sessions",
            "progress_events",
            "progress_retry_items",
            "progress_stars",
            "progress_badges",
            "progress_assignments",
            "content_catalog_concept_guides",
            "content_review_guide_overrides",
            "content_review_guide_status",
        }
    finally:
        con.close()

    # Restart on an existing database is a no-op upgrade.
    with TestClient(create_app(Settings(data_dir=data_dir, frontend_dist=dist))) as c:
        assert c.get("/api/v1/health").status_code == 200


# Story 2.9 review, finding #5: a migration-level test that a pre-existing `parent_profiles`
# row (inserted back when the column didn't exist yet) backfills `auto_play` to `true` via
# the new `0013_auto_play` migration's `server_default`, not `NULL` -- exercising the actual
# upgrade path a real installed database goes through, not just a fresh-DB create.
def test_migration_0013_backfills_auto_play_true_for_existing_profiles(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "data" / "hoctap.db")
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0012_retry_items")
        profile_id = new_id()
        now = to_iso(utc_now())
        connection.exec_driver_sql(
            "INSERT INTO parent_profiles (id, name, avatar, grade, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (profile_id, "Bin", "cat", 1, now),
        )

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    with engine.begin() as connection:
        row = connection.exec_driver_sql(
            "SELECT auto_play FROM parent_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    assert row is not None
    assert row[0] == 1  # SQLite booleans are stored as 0/1 -- 1 means backfilled to `true`.


# Orchestrator's Independent Audit (spec-4-2 #2, 2026-10-01): the established upgrade-path
# pattern (see `test_migration_0013_...` above) -- stage a DB at the PRIOR head, upgrade,
# and inspect the result -- had no counterpart for `0017_assignments`, which only had a
# fresh-DB-from-scratch test. Also exercises the downgrade, matching `test_review.py`'s own
# `test_migration_0007_up_and_down` style.
def test_migration_0017_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "data" / "hoctap.db")
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0016_retry_queue_due")
        profile_id = new_id()
        now = to_iso(utc_now())
        connection.exec_driver_sql(
            "INSERT INTO parent_profiles (id, name, avatar, grade, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (profile_id, "Bin", "cat", 1, now),
        )
        session_id = new_id()
        connection.exec_driver_sql(
            "INSERT INTO progress_sessions "
            "(id, profile_id, ref_kind, ref_key, mode, problem_ids_json, chunk_size, "
            "started_at, completed_at) VALUES (?, ?, 'lesson', 'lesson:x', 'practice', "
            "'[]', 10, ?, NULL)",
            (session_id, profile_id, now),
        )

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0017_assignments")
        tables = {
            r[0]
            for r in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "progress_assignments" in tables
        cols = {
            r[1] for r in connection.exec_driver_sql("PRAGMA table_info(progress_sessions)")
        }
        assert "assignment_id" in cols
        # The pre-existing row survives the upgrade with a NULL `assignment_id`.
        row = connection.exec_driver_sql(
            "SELECT assignment_id FROM progress_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert row is not None and row[0] is None

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0016_retry_queue_due")
        tables = {
            r[0]
            for r in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "progress_assignments" not in tables
        cols = {
            r[1] for r in connection.exec_driver_sql("PRAGMA table_info(progress_sessions)")
        }
        assert "assignment_id" not in cols

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


# Orchestrator's Independent Audit (spec-5-1 #3, 2026-10-01): same gap class, now for
# `0018_concept_guides` -- no upgrade-path test existed (the 4th time this exact class of
# gap has been found: Stories 2.5, 2.9, Epic 4's 0017, now 0018). Follows
# `test_migration_0017_up_and_down`'s established pattern exactly: stage a DB at the prior
# head, upgrade, inspect the new tables/columns, downgrade, and re-upgrade to head.
def test_migration_0018_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "data" / "hoctap.db")
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0017_assignments")
        now = to_iso(utc_now())
        connection.exec_driver_sql(
            "INSERT INTO content_review_concepts (concept_id, grade, name_vi, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("g1.so-sanh-so", 1, "So sánh số", now),
        )

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0018_concept_guides")
        tables = {
            r[0]
            for r in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "content_catalog_concept_guides",
            "content_review_guide_overrides",
            "content_review_guide_status",
        } <= tables
        now = to_iso(utc_now())
        connection.exec_driver_sql(
            "INSERT INTO content_catalog_concept_guides "
            "(concept_id, body_json, source, input_hash, model, generated_at) "
            "VALUES (?, '{}', 'book', 'h', 'claude', ?)",
            ("g1.so-sanh-so", now),
        )
        row = connection.exec_driver_sql(
            "SELECT source FROM content_catalog_concept_guides WHERE concept_id = ?",
            ("g1.so-sanh-so",),
        ).fetchone()
        assert row == ("book",)
        # The pre-existing Concept row survives the upgrade untouched.
        name = connection.exec_driver_sql(
            "SELECT name_vi FROM content_review_concepts WHERE concept_id = ?",
            ("g1.so-sanh-so",),
        ).fetchone()
        assert name == ("So sánh số",)

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0017_assignments")
        tables = {
            r[0]
            for r in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert not (
            {
                "content_catalog_concept_guides",
                "content_review_guide_overrides",
                "content_review_guide_status",
            }
            & tables
        )
        # The Concept row (owned by an earlier migration) is unaffected by the downgrade.
        name = connection.exec_driver_sql(
            "SELECT name_vi FROM content_review_concepts WHERE concept_id = ?",
            ("g1.so-sanh-so",),
        ).fetchone()
        assert name == ("So sánh số",)

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


# `test_migration_0017_up_and_down`'s established pattern exactly: stage a DB at the prior
# head, upgrade, inspect the new columns/constraints, downgrade (checking the `run_kind`
# `'full'` row-deletion behaviour), and re-upgrade to head.
def test_migration_0019_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "data" / "hoctap.db")
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0018_concept_guides")
        now = to_iso(utc_now())
        pilot_id = new_id()
        connection.exec_driver_sql(
            "INSERT INTO build_runs (id, book_id, first_page, last_page, status, stage, "
            "pages_total, pages_done, cost_usd, cost_unknown_count, failed_pages_json, "
            "error, resumed_from, started_at, updated_at, finished_at) "
            "VALUES (?, 'b1', 1, 5, 'done', NULL, 5, 5, 0, 0, '[]', NULL, NULL, ?, ?, NULL)",
            (pilot_id, now, now),
        )

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0019_full_run")
        cols = {r[1] for r in connection.exec_driver_sql("PRAGMA table_info(build_runs)")}
        assert {
            "run_kind",
            "full_id",
            "max_total_usd",
            "stop_reason",
            "unstarted_json",
            "options_json",
        } <= cols
        # The pre-existing pilot row survives the upgrade with the new default `run_kind`.
        row = connection.exec_driver_sql(
            "SELECT run_kind, unstarted_json FROM build_runs WHERE id = ?", (pilot_id,)
        ).fetchone()
        assert row == ("pilot", "[]")
        # A `stopped_*` status (new in this migration) is now accepted by the check
        # constraint, and a `full` run can be inserted with the new columns populated.
        full_id = new_id()
        connection.exec_driver_sql(
            "INSERT INTO build_runs (id, book_id, first_page, last_page, status, stage, "
            "pages_total, pages_done, cost_usd, cost_unknown_count, failed_pages_json, "
            "error, resumed_from, started_at, updated_at, finished_at, run_kind, full_id, "
            "max_total_usd, stop_reason, unstarted_json, options_json) "
            "VALUES (?, 'b1', 1, 5, 'stopped_budget', NULL, 5, 2, 1.5, 0, '[]', NULL, NULL, "
            "?, ?, NULL, 'full', 'group-1', 10.0, 'budget', '[]', NULL)",
            (full_id, now, now),
        )
        row = connection.exec_driver_sql(
            "SELECT run_kind, full_id, status FROM build_runs WHERE id = ?", (full_id,)
        ).fetchone()
        assert row == ("full", "group-1", "stopped_budget")

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0018_concept_guides")
        cols = {r[1] for r in connection.exec_driver_sql("PRAGMA table_info(build_runs)")}
        assert not (
            {
                "run_kind",
                "full_id",
                "max_total_usd",
                "stop_reason",
                "unstarted_json",
                "options_json",
            }
            & cols
        )
        # The downgrade deletes `run_kind='full'` rows outright, so only the pilot survives.
        ids = {r[0] for r in connection.exec_driver_sql("SELECT id FROM build_runs")}
        assert ids == {pilot_id}

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


def test_migration_0020_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "data" / "hoctap.db")
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0019_full_run")
        now = to_iso(utc_now())
        connection.exec_driver_sql(
            "INSERT INTO parent_settings (id, pin_hash, created_at, updated_at) "
            "VALUES (1, 'x', ?, ?)",
            (now, now),
        )

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0020_db_epoch")
        cols = {r[1] for r in connection.exec_driver_sql("PRAGMA table_info(parent_settings)")}
        assert "db_epoch" in cols
        # The pre-existing row got a real random token, not the column default.
        epoch = connection.exec_driver_sql(
            "SELECT db_epoch FROM parent_settings WHERE id = 1"
        ).scalar()
        assert isinstance(epoch, str) and len(epoch) == 32 and epoch != "0"

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0019_full_run")
        cols = {r[1] for r in connection.exec_driver_sql("PRAGMA table_info(parent_settings)")}
        assert "db_epoch" not in cols

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


def test_engine_enables_foreign_keys(client: TestClient) -> None:
    with client.app.state.engine.connect() as conn:  # type: ignore[attr-defined]
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


# --- Config ---------------------------------------------------------------------


def test_config_file_and_env(tmp_path: Path) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text(
        '[server]\nhost = "0.0.0.0"\nport = 9000\nlog_level = "debug"\ndata_dir = "mydata"\n',
        encoding="utf-8",
    )
    s = load_settings(cfg, env={})
    assert (s.host, s.port, s.log_level) == ("0.0.0.0", 9000, "DEBUG")
    assert s.data_dir == (tmp_path / "mydata").resolve()

    s = load_settings(cfg, env={"HOCTAP_PORT": "8123", "HOCTAP_DATA_DIR": str(tmp_path / "d")})
    assert s.port == 8123
    assert s.data_dir == tmp_path / "d"
    assert s.host == "0.0.0.0"


def test_config_defaults_without_file(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "absent.toml", env={})
    assert (s.host, s.port, s.log_level) == ("127.0.0.1", 8000, "INFO")
    assert s.data_dir.name == "data"


def test_config_rejects_bad_port(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "absent.toml", env={"HOCTAP_PORT": "abc"})


def test_config_from_hoctap_config_env(tmp_path: Path) -> None:
    cfg = tmp_path / "custom.toml"
    cfg.write_text("[server]\nport = 9100\n", encoding="utf-8")
    assert load_settings(env={"HOCTAP_CONFIG": str(cfg)}).port == 9100


def test_config_missing_hoctap_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"HOCTAP_CONFIG": str(tmp_path / "missing.toml")})


@pytest.mark.parametrize(
    "content",
    [
        "[server\nport = 1",  # malformed TOML
        "server = 5\n",  # [server] not a table
        "[server]\ndata_dir = 5\n",
        "[server]\nport = true\n",
        "[server]\nport = 80.5\n",
    ],
)
def test_config_invalid_file(tmp_path: Path, content: str) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(cfg, env={})


def test_config_non_utf8_file(tmp_path: Path) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_bytes(b'host = "\xff"\n')
    with pytest.raises(ConfigError):
        load_settings(cfg, env={})


# --- CLI ------------------------------------------------------------------------


def test_cli_bad_env_port_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOCTAP_PORT", "abc")
    assert cli_main(["serve"]) == 2


def test_cli_bad_port_flag_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOCTAP_PORT", raising=False)
    assert cli_main(["serve", "--port", "0"]) == 2


def test_export_openapi_unwritable_returns_1(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert cli_main(["export-openapi", "--out", str(blocker / "openapi.json")]) == 1


def test_export_openapi(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert cli_main(["export-openapi", "--out", str(out)]) == 0
    schema = json.loads(out.read_text(encoding="utf-8"))
    assert "/api/v1/health" in schema["paths"]
    assert "ErrorResponse" in schema["components"]["schemas"]


# --- Story 1.11: HTTPS config -----------------------------------------------------


def test_config_tls_defaults() -> None:
    from hoctap.config import REPO_ROOT

    settings = load_settings(REPO_ROOT / "does-not-exist.toml", env={})
    assert settings.tls_port == 8443
    assert settings.tls_cert_dir == REPO_ROOT / "data" / "certs"
    assert settings.tls_cert_file == REPO_ROOT / "data" / "certs" / "cert.pem"
    assert settings.tls_key_file == REPO_ROOT / "data" / "certs" / "key.pem"


def test_config_tls_from_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text(
        '[server]\ntls_port = 9443\ntls_cert_dir = "my-certs"\n', encoding="utf-8"
    )
    settings = load_settings(cfg, env={})
    assert settings.tls_port == 9443
    assert settings.tls_cert_dir == tmp_path / "my-certs"


def test_config_tls_port_invalid_in_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text("[server]\ntls_port = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(cfg, env={})


def test_config_tls_env_overrides(tmp_path: Path) -> None:
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text('[server]\ntls_port = 9443\n', encoding="utf-8")
    settings = load_settings(
        cfg, env={"HOCTAP_TLS_PORT": "8888", "HOCTAP_TLS_CERT_DIR": str(tmp_path / "env-certs")}
    )
    assert settings.tls_port == 8888
    assert settings.tls_cert_dir == tmp_path / "env-certs"


def test_config_tls_env_port_invalid() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"HOCTAP_TLS_PORT": "not-a-port"})


# --- Story 1.11: `hoctap serve` TLS behaviour ---------------------------------------


@pytest.fixture
def serve_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOCTAP_CONFIG", str(tmp_path / "hoctap.toml"))
    (tmp_path / "hoctap.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(tmp_path / "cli-data"))
    monkeypatch.setenv("HOCTAP_TLS_CERT_DIR", str(tmp_path / "certs"))
    return tmp_path


class _RecordingUvicornRun:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def __call__(self, _app: object, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_serve_no_certs_plain_http(
    serve_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_run = _RecordingUvicornRun()
    monkeypatch.setattr("uvicorn.run", fake_run)
    assert cli_main(["serve"]) == 0
    assert "ssl_certfile" not in fake_run.kwargs
    assert "ssl_keyfile" not in fake_run.kwargs
    assert fake_run.kwargs["port"] == 8000
    out = capsys.readouterr().out
    assert "HTTPS" in out and "off" in out.lower()


def test_serve_certs_present_uses_tls_port_and_ssl_kwargs(
    serve_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cert_dir = serve_env / "certs"
    cert_dir.mkdir()
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    cert_file.write_text("cert", encoding="utf-8")
    key_file.write_text("key", encoding="utf-8")

    fake_run = _RecordingUvicornRun()
    monkeypatch.setattr("uvicorn.run", fake_run)
    assert cli_main(["serve"]) == 0
    assert fake_run.kwargs["ssl_certfile"] == str(cert_file)
    assert fake_run.kwargs["ssl_keyfile"] == str(key_file)
    assert fake_run.kwargs["port"] == 8443
    out = capsys.readouterr().out
    assert "HTTPS" in out and "on" in out.lower()


def test_serve_explicit_port_overrides_tls_port(
    serve_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cert_dir = serve_env / "certs"
    cert_dir.mkdir()
    (cert_dir / "cert.pem").write_text("cert", encoding="utf-8")
    (cert_dir / "key.pem").write_text("key", encoding="utf-8")

    fake_run = _RecordingUvicornRun()
    monkeypatch.setattr("uvicorn.run", fake_run)
    assert cli_main(["serve", "--port", "9999"]) == 0
    assert fake_run.kwargs["port"] == 9999
    assert fake_run.kwargs["ssl_certfile"]  # TLS still active


def test_serve_one_file_missing_falls_back_with_warning(
    serve_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cert_dir = serve_env / "certs"
    cert_dir.mkdir()
    key_file = cert_dir / "key.pem"
    key_file.write_text("key", encoding="utf-8")  # only key.pem, no cert.pem

    fake_run = _RecordingUvicornRun()
    monkeypatch.setattr("uvicorn.run", fake_run)
    assert cli_main(["serve"]) == 0
    assert "ssl_certfile" not in fake_run.kwargs
    assert fake_run.kwargs["port"] == 8000
    captured = capsys.readouterr()
    assert "cert.pem" in captured.err
    assert "HTTPS" in captured.out and "off" in captured.out.lower()
