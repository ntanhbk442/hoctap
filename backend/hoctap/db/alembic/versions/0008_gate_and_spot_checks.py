"""The go/no-go gate (`build_gate`) and the spot-check samples and verdicts.

Revision ID: 0008_gate_and_spot_checks
Revises: 0007_review_tables
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_gate_and_spot_checks"
down_revision: str | Sequence[str] | None = "0007_review_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_review_spot_check_samples",
        sa.Column("sample_id", sa.Text, primary_key=True),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("scope_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_table(
        "content_review_spot_checks",
        sa.Column(
            "sample_id",
            sa.Text,
            sa.ForeignKey("content_review_spot_check_samples.sample_id"),
            nullable=False,
        ),
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("verdict", sa.Text, nullable=True),
        sa.Column("verdict_hash", sa.Text, nullable=True),
        sa.Column("first_wrong_at", sa.Text, nullable=True),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("checked_at", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("sample_id", "problem_id", name="pk_content_review_spot_checks"),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('correct', 'wrong')",
            name="ck_content_review_spot_checks_verdict",
        ),
    )
    op.create_table(
        "build_gate",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("approved_at", sa.Text, nullable=False),
        sa.Column("metrics_json", sa.Text, nullable=False),
        sa.Column("thresholds_json", sa.Text, nullable=False),
        sa.Column("est_cost", sa.Float, nullable=False),
        sa.Column(
            "sample_id",
            sa.Text,
            sa.ForeignKey("content_review_spot_check_samples.sample_id"),
            nullable=False,
        ),
        sa.Column("scope_hash", sa.Text, nullable=False),
        sa.Column("revoked_at", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("build_gate")
    op.drop_table("content_review_spot_checks")
    op.drop_table("content_review_spot_check_samples")
