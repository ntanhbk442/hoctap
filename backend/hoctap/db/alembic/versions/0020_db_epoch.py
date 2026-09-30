"""Backup and restore (Story 7.2): `parent_settings.db_epoch`, a random token that changes
on every restore so tablets can drop outbox events stamped with an older database.

Revision ID: 0020_db_epoch
Revises: 0019_full_run
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_db_epoch"
down_revision: str | Sequence[str] | None = "0019_full_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parent_settings",
        sa.Column("db_epoch", sa.Text, nullable=False, server_default="0"),
    )
    op.execute("UPDATE parent_settings SET db_epoch = lower(hex(randomblob(16)))")


def downgrade() -> None:
    with op.batch_alter_table("parent_settings") as batch:
        batch.drop_column("db_epoch")
