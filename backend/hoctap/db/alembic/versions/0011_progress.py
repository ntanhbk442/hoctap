"""`progress_sessions`/`progress_events` (Story 2.4): a Session freezes its resolved
Problem list at start (AD-9); `progress_events` is the append-only event log (AD-6). Only
`hoctap.learning` writes these tables.

Revision ID: 0011_progress
Revises: 0010_build_runs
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_progress"
down_revision: str | Sequence[str] | None = "0010_build_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("ref_kind", sa.Text, nullable=False),
        sa.Column("ref_key", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False, server_default="practice"),
        sa.Column("problem_ids_json", sa.Text, nullable=False),
        sa.Column("chunk_size", sa.Integer, nullable=False, server_default="10"),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("completed_at", sa.Text, nullable=True),
        sa.CheckConstraint(
            "mode IN ('practice', 'retry', 'concept', 'quiz', 'replay')",
            name="ck_progress_sessions_mode",
        ),
    )
    op.create_index("ix_progress_sessions_profile_id", "progress_sessions", ["profile_id"])

    op.create_table(
        "progress_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "session_id", sa.Text, sa.ForeignKey("progress_sessions.id"), nullable=False
        ),
        sa.Column("profile_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("problem_id", sa.Text, nullable=True),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.Text, nullable=False),
        sa.Column("received_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "kind IN ('attempt', 'hint_requested', 'solution_shown', 'fallback_revealed', "
            "'self_marked', 'quiz_submitted', 'session_started', 'session_completed')",
            name="ck_progress_events_kind",
        ),
    )
    op.create_index("ix_progress_events_session_id", "progress_events", ["session_id"])
    op.create_index(
        "ix_progress_events_profile_problem", "progress_events", ["profile_id", "problem_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_progress_events_profile_problem", table_name="progress_events")
    op.drop_index("ix_progress_events_session_id", table_name="progress_events")
    op.drop_table("progress_events")
    op.drop_index("ix_progress_sessions_profile_id", table_name="progress_sessions")
    op.drop_table("progress_sessions")
