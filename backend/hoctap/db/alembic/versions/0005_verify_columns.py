"""Verify verdict columns on `build_page_results`.

Revision ID: 0005_verify_columns
Revises: 0004_build_tables
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_verify_columns"
down_revision: str | Sequence[str] | None = "0004_build_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("build_page_results") as batch:
        batch.add_column(
            sa.Column("verify_status", sa.Text, nullable=False, server_default="unverified")
        )
        batch.add_column(sa.Column("verify_reasons_json", sa.Text, nullable=True))
        batch.add_column(sa.Column("needs_review", sa.Integer, nullable=False, server_default="1"))
        batch.create_check_constraint(
            "ck_build_page_results_verify_status",
            "verify_status IN ('agree', 'disagree', 'unverified')",
        )
        batch.create_check_constraint(
            "ck_build_page_results_needs_review", "needs_review IN (0, 1)"
        )


def downgrade() -> None:
    with op.batch_alter_table("build_page_results") as batch:
        batch.drop_constraint("ck_build_page_results_needs_review", type_="check")
        batch.drop_constraint("ck_build_page_results_verify_status", type_="check")
        batch.drop_column("needs_review")
        batch.drop_column("verify_reasons_json")
        batch.drop_column("verify_status")
