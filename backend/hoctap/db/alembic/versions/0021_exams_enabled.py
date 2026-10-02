"""`parent_profiles.exams_enabled` (Story 8.1): gates every exam entry point (parent-
assigned and child-on-demand alike) for a Child Profile. Default off -- exam mode is an
explicit, per-Profile opt-in (a deliberate departure from this app's own "no timers" child
design philosophy; see spec-8-1's Intent).

Revision ID: 0021_exams_enabled
Revises: 0020_db_epoch
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_exams_enabled"
down_revision: str | Sequence[str] | None = "0020_db_epoch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parent_profiles",
        sa.Column("exams_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("parent_profiles", "exams_enabled")
