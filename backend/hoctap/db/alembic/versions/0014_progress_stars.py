"""`progress_stars` (Story 3.1, AD-6): one row per Problem-per-Session, written inside the
SAME transaction as whichever event resolves the Problem's outcome for that Session.
`stars` is 0/1/3 only (see the CHECK constraint) -- 3 if every Part was first-try-correct,
1 if a Hint/retry was needed but no Part's Solution was shown (or a `fallback` Problem
self-marked "đúng"), 0 if any Part's Solution was shown (or a `fallback` Problem
self-marked "chưa đúng"). A unique (session_id, problem_id) index backs the "written
once" idempotency rule. Only `hoctap.learning` writes it.

Revision ID: 0014_progress_stars
Revises: 0013_auto_play
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_progress_stars"
down_revision: str | Sequence[str] | None = "0013_auto_play"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_stars",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "session_id", sa.Text, sa.ForeignKey("progress_sessions.id"), nullable=False
        ),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("problem_id", sa.Text, nullable=False),
        sa.Column("stars", sa.Integer, nullable=False),
        sa.Column("awarded_at", sa.Text, nullable=False),
        sa.CheckConstraint("stars IN (0, 1, 3)", name="ck_progress_stars_stars"),
    )
    op.create_index(
        "ux_progress_stars_session_problem",
        "progress_stars",
        ["session_id", "problem_id"],
        unique=True,
    )
    op.create_index("ix_progress_stars_profile_id", "progress_stars", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_progress_stars_profile_id", table_name="progress_stars")
    op.drop_index("ux_progress_stars_session_problem", table_name="progress_stars")
    op.drop_table("progress_stars")
