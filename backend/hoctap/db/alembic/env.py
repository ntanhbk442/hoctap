"""Alembic environment. Uses a connection passed in by `run_migrations()` when present."""

from __future__ import annotations

from alembic import context
from sqlalchemy.engine import URL

from hoctap.config import load_settings
from hoctap.db.engine import create_db_engine

config = context.config

# No ORM models yet; later stories set this to the shared MetaData.
target_metadata = None


def _settings_url() -> str:
    return URL.create("sqlite", database=str(load_settings().db_path)).render_as_string()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url") or _settings_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    # Manual `alembic` runs: use the configured database (hoctap.toml / HOCTAP_*).
    connectable = create_db_engine(load_settings().db_path)
    try:
        with connectable.connect() as conn:
            context.configure(
                connection=conn, target_metadata=target_metadata, render_as_batch=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
