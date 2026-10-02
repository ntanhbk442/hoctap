"""`progress_assignments` grows an exam-scope ref alongside its existing Lesson ref (Story
8.1): a parent can now assign either a Lesson (the existing `book_id`/`unit_key`/
`lesson_key` triple) or an exam (`exam_scope_json`, same scope/count/time_limit_s shape
`learning.problem_sets.ExamRef` resolves at Session-start time -- an Assignment is a
recipe, not a frozen Problem list, so starting it re-resolves a FRESH random draw every
time, same AD-9 freeze-at-session-start rule as every other ref kind).

The three Lesson columns become nullable and a CHECK constraint enforces exactly one ref
kind per row: either all three Lesson columns are set and `exam_scope_json` is null, or
all three are null and `exam_scope_json` is set. An Assignment row is never both at once.

Revision ID: 0023_exam_assignments
Revises: 0022_exam_sessions
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_exam_assignments"
down_revision: str | Sequence[str] | None = "0022_exam_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REF_XOR = (
    "(book_id IS NOT NULL AND unit_key IS NOT NULL AND lesson_key IS NOT NULL "
    "AND exam_scope_json IS NULL) OR "
    "(book_id IS NULL AND unit_key IS NULL AND lesson_key IS NULL "
    "AND exam_scope_json IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("progress_assignments") as batch:
        batch.add_column(sa.Column("exam_scope_json", sa.Text, nullable=True))
        batch.alter_column("book_id", existing_type=sa.Text, nullable=True)
        batch.alter_column("unit_key", existing_type=sa.Text, nullable=True)
        batch.alter_column("lesson_key", existing_type=sa.Text, nullable=True)
        batch.create_check_constraint("ck_progress_assignments_ref_xor", _REF_XOR)


def downgrade() -> None:
    with op.batch_alter_table("progress_assignments") as batch:
        batch.drop_constraint("ck_progress_assignments_ref_xor", type_="check")
        batch.alter_column("book_id", existing_type=sa.Text, nullable=False)
        batch.alter_column("unit_key", existing_type=sa.Text, nullable=False)
        batch.alter_column("lesson_key", existing_type=sa.Text, nullable=False)
        batch.drop_column("exam_scope_json")
