"""`build_jobs.run_kind`: pilot | full. The go/no-go gate's pilot scope is the extract
jobs of kind `pilot`; existing rows are pilot rows.

Revision ID: 0009_build_jobs_run_kind
Revises: 0008_gate_and_spot_checks
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_build_jobs_run_kind"
down_revision: str | Sequence[str] | None = "0008_gate_and_spot_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("build_jobs") as batch:
        batch.add_column(sa.Column("run_kind", sa.Text, nullable=False, server_default="pilot"))
        batch.create_check_constraint("ck_build_jobs_run_kind", "run_kind IN ('pilot', 'full')")
    op.create_index("ix_build_jobs_run_kind", "build_jobs", ["run_kind", "page_ref"])


def downgrade() -> None:
    op.drop_index("ix_build_jobs_run_kind", table_name="build_jobs")
    with op.batch_alter_table("build_jobs") as batch:
        batch.drop_constraint("ck_build_jobs_run_kind", type_="check")
        batch.drop_column("run_kind")
