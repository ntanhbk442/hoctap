"""SQLite engine (WAL, foreign keys on) and Alembic migrations run at startup."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

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
    engine = create_engine(URL.create("sqlite", database=str(db_path)))
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
    """Upgrade the database to the Alembic head on the given engine."""
    cfg = alembic_config(engine)
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


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
