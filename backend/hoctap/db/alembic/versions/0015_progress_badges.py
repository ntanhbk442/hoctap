"""`progress_badges` (Story 3.2, AD-6): one row per Profile-per-earned-badge, written
inside the SAME transaction as whichever event first makes that badge's condition true.
`badge_key` is one of a fixed enum (`week1`, `streak7`, `stars100` -- see the CHECK
constraint). A unique (profile_id, badge_key) index backs the "earned once, ever, per
Profile" idempotency rule. Only `hoctap.learning` writes it.

Revision ID: 0015_progress_badges
Revises: 0014_progress_stars
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_progress_badges"
down_revision: str | Sequence[str] | None = "0014_progress_stars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_badges",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("badge_key", sa.Text, nullable=False),
        sa.Column("earned_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "badge_key IN ('week1', 'streak7', 'stars100')",
            name="ck_progress_badges_badge_key",
        ),
    )
    op.create_index(
        "ux_progress_badges_profile_badge",
        "progress_badges",
        ["profile_id", "badge_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_progress_badges_profile_badge", table_name="progress_badges")
    op.drop_table("progress_badges")
