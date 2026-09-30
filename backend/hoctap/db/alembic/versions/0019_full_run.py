"""Full-corpus run (Story 6.2): `build_runs` gains the run kind, the group id of a full
run, its overall cap, the stop reason, the unstarted list and the resume options, and the
three `stopped_*` statuses.

Revision ID: 0019_full_run
Revises: 0018_concept_guides
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_full_run"
down_revision: str | Sequence[str] | None = "0018_concept_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "status IN ('running', 'pausing', 'paused', 'done', 'failed', 'cancelled')"
_NEW = (
    "status IN ('running', 'pausing', 'paused', 'done', 'failed', 'cancelled', "
    "'stopped_budget', 'stopped_checkpoint', 'stopped_gate')"
)


def upgrade() -> None:
    with op.batch_alter_table("build_runs", recreate="always") as batch:
        batch.add_column(sa.Column("run_kind", sa.Text, nullable=False, server_default="pilot"))
        batch.add_column(sa.Column("full_id", sa.Text, nullable=True))
        batch.add_column(sa.Column("max_total_usd", sa.Float, nullable=True))
        batch.add_column(sa.Column("stop_reason", sa.Text, nullable=True))
        batch.add_column(sa.Column("unstarted_json", sa.Text, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("options_json", sa.Text, nullable=True))
        batch.drop_constraint("ck_build_runs_status", type_="check")
        batch.create_check_constraint("ck_build_runs_status", _NEW)
        batch.create_check_constraint("ck_build_runs_run_kind", "run_kind IN ('pilot', 'full')")
    op.create_index("ix_build_runs_full_id", "build_runs", ["full_id"])


def downgrade() -> None:
    op.drop_index("ix_build_runs_full_id", table_name="build_runs")
    op.execute("DELETE FROM build_runs WHERE run_kind = 'full'")
    with op.batch_alter_table("build_runs", recreate="always") as batch:
        batch.drop_constraint("ck_build_runs_run_kind", type_="check")
        batch.drop_constraint("ck_build_runs_status", type_="check")
        batch.create_check_constraint("ck_build_runs_status", _OLD)
        batch.drop_column("options_json")
        batch.drop_column("unstarted_json")
        batch.drop_column("stop_reason")
        batch.drop_column("max_total_usd")
        batch.drop_column("full_id")
        batch.drop_column("run_kind")
