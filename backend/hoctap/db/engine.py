"""SQLite engine (WAL, foreign keys on) and Alembic migrations run at startup."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

log = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent
ALEMBIC_INI = _DB_DIR / "alembic.ini"
ALEMBIC_DIR = _DB_DIR / "alembic"


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    try:
        # 30s (was 5s until Story 2.5): `learning.sessions.post_event()` now grades an
        # `attempt` synchronously inside the same write transaction as its insert (AD-6),
        # which can hold SQLite's single-writer lock noticeably longer under genuine
        # concurrent writes (e.g. two real threads racing the same event id) than the
        # single-statement insert Story 2.4 shipped with -- see this story's
        # Implementation Notes.
        cursor.execute("PRAGMA busy_timeout=30000")
        mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
        if not mode or str(mode[0]).lower() != "wal":
            log.warning("sqlite WAL not enabled", extra={"journal_mode": mode and mode[0]})
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Story 8.1 (2026-10-02, found while testing the exam Assignment flow): `NullPool`, not
    # SQLAlchemy's default `QueuePool` -- a pooled, REUSED raw sqlite3 connection can keep
    # observing a WAL snapshot from whenever ITS last read transaction began, even after a
    # DIFFERENT connection has since committed a write, until that pooled connection itself
    # starts a genuinely new transaction in a way that refreshes it. In this app's actual
    # request pattern (many short-lived `engine.connect()`/`engine.begin()` calls per HTTP
    # request, one call per request-handling function) that surfaced as a real, reproducible
    # bug: `POST /sessions/{id}/events` (`session_completed`) commits `completed_at` on one
    # connection, and the VERY NEXT `GET /library/home/{id}` request -- on a pooled
    # connection that happened to be reused -- read it back as still `NULL`, so a just-
    # completed Assignment kept showing as the still-due Home card
    # (`test_assignments.py::test_carry_over_and_queue`, previously passing, started
    # failing ~100% of runs once this story's Assignment code added one more request in the
    # same sequence and changed which pooled connection got reused). `NullPool` opens a
    # fresh raw connection per checkout and closes it on return -- no connection is ever
    # reused with a stale snapshot. The overhead of opening a new local SQLite file handle
    # per request is negligible for this app's single-process, local-file deployment target,
    # and is the commonly recommended pool strategy for SQLite for exactly this reason.
    engine = create_engine(URL.create("sqlite", database=str(db_path)), poolclass=NullPool)
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def alembic_config(engine: Engine) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # ConfigParser interpolates `%`, so escape it in paths and URLs.
    cfg.set_main_option("script_location", str(ALEMBIC_DIR).replace("%", "%%"))
    url = engine.url.render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def run_migrations(engine: Engine) -> None:
    """Upgrade the database to the Alembic head on the given engine.

    Orchestrator's Independent Audit (2026-10-02): SQLite only allows toggling `PRAGMA
    foreign_keys` when no transaction is open -- it is a silent no-op otherwise. Some
    migrations (anything beyond a plain `ADD COLUMN`, e.g. dropping/recreating a CHECK
    constraint) force SQLite's `batch_alter_table` fallback to fully recreate the table:
    create new, copy rows, DROP the old, rename. If another table has a real FOREIGN KEY
    onto the one being recreated, that DROP fails under FK enforcement the moment the
    database actually has a row referencing it -- which a fresh-per-test database never
    does, but any real, lived-in deployment always will (first caught when migration
    0022 crashed `hoctap serve` outright against this project's own development database).
    `engine.connect()` alone does not open a transaction (pysqlite does not implicitly
    BEGIN for a PRAGMA/DDL statement, only for DML), so toggling it HERE, before
    `connection.begin()` starts the migration's single transaction, actually takes effect
    for the whole run. `PRAGMA foreign_key_check` right before commit still catches a
    genuine data-integrity violation loudly rather than silently committing one.
    """
    cfg = alembic_config(engine)
    with engine.connect() as connection:
        # `exec_driver_sql` itself triggers SQLAlchemy's "autobegin" (a logical
        # Transaction() object), so an explicit `connection.begin()` after it would
        # conflict -- commit/rollback this one connection-wide transaction directly instead.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            connection.rollback()
            raise RuntimeError(f"migration left dangling foreign keys: {violations}")
        connection.commit()


def head_revision() -> str:
    """The Alembic head this app version migrates to."""
    from alembic.script import ScriptDirectory

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR).replace("%", "%%"))
    return ScriptDirectory.from_config(cfg).get_current_head() or ""


def is_known_revision(revision: str) -> bool:
    """True if `revision` is in this app's migration chain (so it is at or below the head)."""
    from alembic.script import ScriptDirectory

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR).replace("%", "%%"))
    try:
        return ScriptDirectory.from_config(cfg).get_revision(revision) is not None
    except Exception:  # noqa: BLE001 -- alembic raises several types for an unknown id
        return False
