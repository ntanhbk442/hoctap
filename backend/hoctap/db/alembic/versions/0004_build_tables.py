"""Build pipeline tables (`build_jobs`, `build_costs`, `build_page_results`).

Revision ID: 0004_build_tables
Revises: 0003_catalog_books
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_build_tables"
down_revision: str | Sequence[str] | None = "0003_catalog_books"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "build_jobs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("page_ref", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("output_json", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("status IN ('done', 'failed')", name="ck_build_jobs_status"),
        sa.UniqueConstraint("page_ref", "stage", "input_hash", name="uq_build_jobs_key"),
    )
    op.create_index("ix_build_jobs_stage_status", "build_jobs", ["stage", "status"])
    op.create_table(
        "build_costs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("page_ref", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cache_creation_input_tokens", sa.Integer, nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("cost_unknown", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_build_costs_page_ref", "build_costs", ["page_ref"])
    op.create_table(
        "build_page_results",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("page_ref", sa.Text, nullable=False),
        sa.Column("book_id", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("draft_index", sa.Integer, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("problem_id", sa.Text, nullable=True),
        sa.Column("duplicate", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_json", sa.Text, nullable=True),
        sa.Column("draft_json", sa.Text, nullable=False),
        sa.Column("errors_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("status IN ('valid', 'invalid')", name="ck_build_page_results_status"),
        sa.UniqueConstraint("page_ref", "draft_index", name="uq_build_page_results_draft"),
    )
    op.create_index("ix_build_page_results_problem_id", "build_page_results", ["problem_id"])


def downgrade() -> None:
    op.drop_index("ix_build_page_results_problem_id", table_name="build_page_results")
    op.drop_table("build_page_results")
    op.drop_index("ix_build_costs_page_ref", table_name="build_costs")
    op.drop_table("build_costs")
    op.drop_index("ix_build_jobs_stage_status", table_name="build_jobs")
    op.drop_table("build_jobs")
