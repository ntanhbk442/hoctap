"""`build_runs`: one row per background pilot run started from the Parent Area's
Extraction screen (Story 1.10). `builder.jobs.RunManager` is the only writer.

Revision ID: 0010_build_runs
Revises: 0009_build_jobs_run_kind
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_build_runs"
down_revision: str | Sequence[str] | None = "0009_build_jobs_run_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "build_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("book_id", sa.Text, nullable=False),
        sa.Column("first_page", sa.Integer, nullable=False),
        sa.Column("last_page", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=True),
        sa.Column("pages_total", sa.Integer, nullable=False),
        sa.Column("pages_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("cost_unknown_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_pages_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("resumed_from", sa.Text, nullable=True),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("finished_at", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'pausing', 'paused', 'done', 'failed', 'cancelled')",
            name="ck_build_runs_status",
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN "
            "('render', 'extract', 'validate', 'verify', 'crop', 'publish')",
            name="ck_build_runs_stage",
        ),
    )
    op.create_index("ix_build_runs_status", "build_runs", ["status"])
    op.create_index("ix_build_runs_book_id", "build_runs", ["book_id"])


def downgrade() -> None:
    op.drop_index("ix_build_runs_book_id", table_name="build_runs")
    op.drop_index("ix_build_runs_status", table_name="build_runs")
    op.drop_table("build_runs")
