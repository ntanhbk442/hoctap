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
        cursor.execute("PRAGMA busy_timeout=5000")
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
