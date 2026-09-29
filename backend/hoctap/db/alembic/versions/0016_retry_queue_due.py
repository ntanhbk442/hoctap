"""`progress_retry_items.last_wrong_at` (Story 3.3, AD-6): the timestamp of the most recent
wrong Attempt / "chưa đúng" while the item stayed open -- drives "due next calendar day".
Backfilled from `added_at`.

Revision ID: 0016_retry_queue_due
Revises: 0015_progress_badges
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_retry_queue_due"
down_revision: str | Sequence[str] | None = "0015_progress_badges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("progress_retry_items") as batch:
        batch.add_column(sa.Column("last_wrong_at", sa.Text, nullable=True))
    op.execute("UPDATE progress_retry_items SET last_wrong_at = added_at")


def downgrade() -> None:
    with op.batch_alter_table("progress_retry_items") as batch:
        batch.drop_column("last_wrong_at")
