"""`progress_assignments` and `progress_sessions.assignment_id` (Story 4.3, FR-20).

Revision ID: 0017_assignments
Revises: 0016_retry_queue_due
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_assignments"
down_revision: str | Sequence[str] | None = "0016_retry_queue_due"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_assignments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("ref_kind", sa.Text, nullable=False),
        sa.Column("ref_key", sa.Text, nullable=False),
        sa.Column("book_id", sa.Text, nullable=False),
        sa.Column("unit_key", sa.Text, nullable=False),
        sa.Column("lesson_key", sa.Text, nullable=False),
        sa.Column("assigned_date", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("deleted_at", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_progress_assignments_profile_date",
        "progress_assignments",
        ["profile_id", "assigned_date"],
    )
    with op.batch_alter_table("progress_sessions") as batch:
        batch.add_column(sa.Column("assignment_id", sa.Text, nullable=True))
    op.create_index("ix_progress_sessions_assignment_id", "progress_sessions", ["assignment_id"])


def downgrade() -> None:
    op.drop_index("ix_progress_sessions_assignment_id", table_name="progress_sessions")
    with op.batch_alter_table("progress_sessions") as batch:
        batch.drop_column("assignment_id")
    op.drop_index("ix_progress_assignments_profile_date", table_name="progress_assignments")
    op.drop_table("progress_assignments")
