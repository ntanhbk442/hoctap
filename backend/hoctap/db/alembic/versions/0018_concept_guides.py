"""Concept Guides: generated, edited and approved (Story 5.1).

Revision ID: 0018_concept_guides
Revises: 0017_assignments
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_concept_guides"
down_revision: str | Sequence[str] | None = "0017_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_catalog_concept_guides",
        sa.Column("concept_id", sa.Text, primary_key=True),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("generated_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "source IN ('book', 'problems')", name="ck_content_catalog_concept_guides_source"
        ),
    )
    op.create_table(
        "content_review_guide_overrides",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("concept_id", sa.Text, nullable=False),
        sa.Column("field", sa.Text, nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("base_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("concept_id", "field", name="uq_content_review_guide_overrides"),
    )
    op.create_table(
        "content_review_guide_status",
        sa.Column("concept_id", sa.Text, primary_key=True),
        sa.Column("approved_hash", sa.Text, nullable=True),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("content_review_guide_status")
    op.drop_table("content_review_guide_overrides")
    op.drop_table("content_catalog_concept_guides")
