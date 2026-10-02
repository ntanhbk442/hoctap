"""`progress_sessions.time_limit_s` (Story 8.1): the exam time limit in seconds, stored
alongside `started_at` so the backend -- not the client -- is the timer's source of truth
(a closed-and-reopened tablet mid-exam must show the real remaining time, not a reset
countdown). Nullable; only ever set for `mode='exam'`. `mode`'s CHECK constraint gains
`'exam'`.

Orchestrator's Independent Audit (2026-10-02): `progress_events.session_id` has a real
FOREIGN KEY onto `progress_sessions.id`. Adding a column alone (every PRIOR migration that
touched `progress_sessions`, e.g. 0017's `assignment_id`) is a direct `ALTER TABLE ... ADD
COLUMN`, which SQLite supports natively with no table recreation. But also dropping and
recreating a CHECK constraint forces `batch_alter_table`'s SQLite fallback to fully
recreate the table (create new, copy rows, DROP the old, rename) -- and with
`PRAGMA foreign_keys=ON` (this app's own `db.engine._set_sqlite_pragmas`, which fires on
every new connection including the one running this migration), that DROP TABLE fails with
`FOREIGN KEY constraint failed` the moment the database has even one real `progress_events`
row -- which every fresh-per-test database in this project's test suite never has, but any
actually-lived-in deployment always does. First caught when this exact migration crashed
`hoctap serve` outright against this project's own real development database.

Revision ID: 0022_exam_sessions
Revises: 0021_exams_enabled
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_exam_sessions"
down_revision: str | Sequence[str] | None = "0021_exams_enabled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_MODES = "mode IN ('practice', 'retry', 'concept', 'quiz', 'replay')"
_NEW_MODES = "mode IN ('practice', 'retry', 'concept', 'quiz', 'replay', 'exam')"


def upgrade() -> None:
    # The batch recreate below DROPs and re-creates `progress_sessions`; `progress_events`
    # has a real FOREIGN KEY onto it (see this module's own docstring). FK enforcement for
    # the duration is handled one layer up, by `db.engine.run_migrations()` -- SQLite only
    # allows toggling `PRAGMA foreign_keys` with no transaction open, which is never true
    # from inside an individual migration's `upgrade()`/`downgrade()`.
    with op.batch_alter_table("progress_sessions") as batch:
        batch.add_column(sa.Column("time_limit_s", sa.Integer, nullable=True))
        batch.drop_constraint("ck_progress_sessions_mode", type_="check")
        batch.create_check_constraint("ck_progress_sessions_mode", _NEW_MODES)


def downgrade() -> None:
    with op.batch_alter_table("progress_sessions") as batch:
        batch.drop_constraint("ck_progress_sessions_mode", type_="check")
        batch.create_check_constraint("ck_progress_sessions_mode", _OLD_MODES)
        batch.drop_column("time_limit_s")
