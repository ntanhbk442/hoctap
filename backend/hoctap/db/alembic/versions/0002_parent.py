"""Parent settings (PIN) and Child Profiles.

Revision ID: 0002_parent
Revises: 0001_baseline
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_parent"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parent_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pin_hash", sa.Text, nullable=False),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.Text, nullable=True),
        sa.Column("session_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_parent_settings_single_row"),
    )
    op.create_table(
        "parent_profiles",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("avatar", sa.Text, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("grade BETWEEN 1 AND 5", name="ck_parent_profiles_grade"),
    )


def downgrade() -> None:
    op.drop_table("parent_profiles")
    op.drop_table("parent_settings")
