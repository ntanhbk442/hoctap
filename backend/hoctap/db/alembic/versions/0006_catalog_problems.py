"""Published content: `content_catalog_{units,lessons,problems}` and the Concept proposals
(`content_review_concept_proposals`, `content_review_problem_proposals`).

Revision ID: 0006_catalog_problems
Revises: 0005_verify_columns
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_catalog_problems"
down_revision: str | Sequence[str] | None = "0005_verify_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_catalog_units",
        sa.Column(
            "book_id", sa.Text, sa.ForeignKey("content_catalog_books.book_id"), nullable=False
        ),
        sa.Column("unit_key", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("book_id", "unit_key", name="pk_content_catalog_units"),
    )
    op.create_table(
        "content_catalog_lessons",
        sa.Column(
            "book_id", sa.Text, sa.ForeignKey("content_catalog_books.book_id"), nullable=False
        ),
        sa.Column("unit_key", sa.Text, nullable=False),
        sa.Column("lesson_key", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("is_quiz_sheet", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "book_id", "unit_key", "lesson_key", name="pk_content_catalog_lessons"
        ),
        sa.CheckConstraint("is_quiz_sheet IN (0, 1)", name="ck_content_catalog_lessons_quiz"),
    )
    op.create_table(
        "content_catalog_problems",
        sa.Column("problem_id", sa.Text, primary_key=True),
        sa.Column(
            "book_id", sa.Text, sa.ForeignKey("content_catalog_books.book_id"), nullable=False
        ),
        sa.Column("unit_key", sa.Text, nullable=False),
        sa.Column("lesson_key", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("doc_json", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("needs_review", sa.Integer, nullable=False),
        sa.Column("verify_status", sa.Text, nullable=False),
        sa.Column("duplicate", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_page_first", sa.Integer, nullable=False),
        sa.Column("retired_at", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "needs_review IN (0, 1)", name="ck_content_catalog_problems_needs_review"
        ),
        sa.CheckConstraint("duplicate IN (0, 1)", name="ck_content_catalog_problems_duplicate"),
        sa.CheckConstraint(
            "verify_status IN ('agree', 'disagree', 'unverified')",
            name="ck_content_catalog_problems_verify_status",
        ),
    )
    op.create_index(
        "ix_content_catalog_problems_lesson",
        "content_catalog_problems",
        ["book_id", "unit_key", "lesson_key"],
    )
    op.create_table(
        "content_review_concept_proposals",
        sa.Column("proposal_key", sa.Text, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("problem_count", sa.Integer, nullable=False),
        sa.Column("first_seen", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="proposed"),
        sa.PrimaryKeyConstraint(
            "proposal_key", "grade", name="pk_content_review_concept_proposals"
        ),
    )
    op.create_table(
        "content_review_problem_proposals",
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("proposal_key", sa.Text, nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint(
            "problem_id", "proposal_key", "grade", name="pk_content_review_problem_proposals"
        ),
    )
    op.create_index(
        "ix_content_review_problem_proposals_key",
        "content_review_problem_proposals",
        ["proposal_key", "grade"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_review_problem_proposals_key", table_name="content_review_problem_proposals"
    )
    op.drop_table("content_review_problem_proposals")
    op.drop_table("content_review_concept_proposals")
    op.drop_index("ix_content_catalog_problems_lesson", table_name="content_catalog_problems")
    op.drop_table("content_catalog_problems")
    op.drop_table("content_catalog_lessons")
    op.drop_table("content_catalog_units")
