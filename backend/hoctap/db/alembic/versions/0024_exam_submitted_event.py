"""`progress_events.kind` CHECK gains `'exam_submitted'` (Story 8.1): mirrors
`quiz_submitted` -- one event that grades a whole exam Session's Problems at once.

Revision ID: 0024_exam_submitted_event
Revises: 0023_exam_assignments
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_exam_submitted_event"
down_revision: str | Sequence[str] | None = "0023_exam_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = (
    "kind IN ('attempt', 'hint_requested', 'solution_shown', 'fallback_revealed', "
    "'self_marked', 'quiz_submitted', 'session_started', 'session_completed')"
)
_NEW_KINDS = (
    "kind IN ('attempt', 'hint_requested', 'solution_shown', 'fallback_revealed', "
    "'self_marked', 'quiz_submitted', 'exam_submitted', 'session_started', "
    "'session_completed')"
)


def upgrade() -> None:
    with op.batch_alter_table("progress_events") as batch:
        batch.drop_constraint("ck_progress_events_kind", type_="check")
        batch.create_check_constraint("ck_progress_events_kind", _NEW_KINDS)


def downgrade() -> None:
    with op.batch_alter_table("progress_events") as batch:
        batch.drop_constraint("ck_progress_events_kind", type_="check")
        batch.create_check_constraint("ck_progress_events_kind", _OLD_KINDS)
