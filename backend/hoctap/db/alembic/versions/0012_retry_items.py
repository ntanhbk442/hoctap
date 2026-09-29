"""`progress_retry_items` (Story 2.5): the Retry Queue, Profile-wide, resolved once every
Part of a Problem has since been answered correctly. Only `hoctap.learning` writes it.

Revision ID: 0012_retry_items
Revises: 0011_progress
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_retry_items"
down_revision: str | Sequence[str] | None = "0011_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_retry_items",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("added_at", sa.Text, nullable=False),
        sa.Column("resolved_at", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_progress_retry_items_profile_problem",
        "progress_retry_items",
        ["profile_id", "problem_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_progress_retry_items_profile_problem", table_name="progress_retry_items"
    )
    op.drop_table("progress_retry_items")
