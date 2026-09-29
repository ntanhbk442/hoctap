"""`parent_profiles.auto_play` (Story 2.9): gates auto-playing a Problem's instruction on
open. Default on for every existing and new Profile; no Parent-Area toggle ships with this
story.

Revision ID: 0013_auto_play
Revises: 0012_retry_items
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_auto_play"
down_revision: str | Sequence[str] | None = "0012_retry_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parent_profiles",
        sa.Column("auto_play", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("parent_profiles", "auto_play")
