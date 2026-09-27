"""Content Review: overrides, review status, Error Reports, curated Concepts and their
links, plus the proposal target column.

Revision ID: 0007_review_tables
Revises: 0006_catalog_problems
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_review_tables"
down_revision: str | Sequence[str] | None = "0006_catalog_problems"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_review_overrides",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("part_key", sa.Text, nullable=False, server_default=""),
        sa.Column("field", sa.Text, nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("base_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("problem_id", "part_key", "field", name="uq_content_review_overrides"),
    )
    op.create_table(
        "content_review_status",
        sa.Column("problem_id", sa.Text, primary_key=True),
        sa.Column("approved_hash", sa.Text, nullable=True),
        sa.Column("hidden", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("hidden IN (0, 1)", name="ck_content_review_status_hidden"),
    )
    op.create_table(
        "content_review_error_reports",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("resolved_at", sa.Text, nullable=True),
        sa.CheckConstraint(
            "kind IN ('parent', 'child')", name="ck_content_review_error_reports_kind"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')", name="ck_content_review_error_reports_status"
        ),
    )
    op.create_index(
        "ix_content_review_error_reports_problem",
        "content_review_error_reports",
        ["problem_id", "status"],
    )
    op.create_table(
        "content_review_concepts",
        sa.Column("concept_id", sa.Text, primary_key=True),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("name_vi", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("grade BETWEEN 1 AND 5", name="ck_content_review_concepts_grade"),
    )
    op.create_table(
        "content_review_problem_concepts",
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("concept_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint(
            "problem_id", "concept_id", name="pk_content_review_problem_concepts"
        ),
    )
    op.create_index(
        "ix_content_review_problem_concepts_concept",
        "content_review_problem_concepts",
        ["concept_id"],
    )
    with op.batch_alter_table("content_review_concept_proposals") as batch:
        batch.add_column(sa.Column("target_concept_id", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("content_review_concept_proposals") as batch:
        batch.drop_column("target_concept_id")
    op.drop_index(
        "ix_content_review_problem_concepts_concept", table_name="content_review_problem_concepts"
    )
    op.drop_table("content_review_problem_concepts")
    op.drop_table("content_review_concepts")
    op.drop_index(
        "ix_content_review_error_reports_problem", table_name="content_review_error_reports"
    )
    op.drop_table("content_review_error_reports")
    op.drop_table("content_review_status")
    op.drop_table("content_review_overrides")
