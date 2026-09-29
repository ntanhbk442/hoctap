"""`progress_*` tables (Story 2.4, AD-6/AD-9). Only `hoctap.learning` writes them.

- `progress_sessions`: one row per started Session (AD-9). `problem_ids_json` is the
  frozen, resolved, full list of the Session's Problems (every chunk, not just chunk 1) --
  `learning.problem_sets.resolve()`'s output at start time, never recomputed afterwards.
  `mode` is stored now (`retry`/`concept`/`quiz`/`replay` are Story 2.5+/AD-6 territory) so
  the schema doesn't need another migration later; this story only ever writes `"practice"`.
  `completed_at` stays nullable and unset here -- a `session_completed` event existing for a
  Session is what a later story uses to fill it in.
- `progress_events`: append-only (AD-6). `id` is the CLIENT-supplied UUIDv7 and the primary
  key -- this is what makes a resend a no-op (insert, catch the IntegrityError on a
  duplicate id, re-fetch). `occurred_at` is the client's own timestamp, stored verbatim
  (never overwritten by server time -- it decides the calendar day per AD-6); `received_at`
  is server time via the app's testable clock.
- `progress_retry_items` (Story 2.5): the Retry Queue. One row per Profile+Problem
  currently needing a retry -- added on a Part's first wrong `attempt`, resolved
  (`resolved_at` set) once every Part of that Problem has since been answered correctly.
  Profile-wide (not Session-scoped), matching staged help's own scope (AD-6). Not
  append-only: `resolved_at` is the one field ever updated after insert.
- `progress_stars` (Story 3.1, AD-6): one row per Problem-per-Session, written ONCE
  inside the SAME transaction as whichever event resolves the Problem's outcome for that
  Session (see `learning.scoring.maybe_award_stars()`), never a second commit boundary.
  `stars` is 0/1/3 only -- a `CHECK` constraint, not an arbitrary int (see
  `learning.scoring`'s own docstring for what each value means). A unique
  (`session_id`, `problem_id`) index makes a resolving event's resend idempotent (checked
  before insert, same "already stored, no-op" posture as every other Story 2.5+
  mutation). Only `hoctap.learning` writes it.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table, Text

metadata = MetaData()

progress_sessions = Table(
    "progress_sessions",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("profile_id", Text, nullable=False),
    Column("ref_kind", Text, nullable=False),
    Column("ref_key", Text, nullable=False),
    Column("mode", Text, nullable=False, server_default="practice"),
    Column("problem_ids_json", Text, nullable=False),  # the frozen, resolved, full list
    Column("chunk_size", Integer, nullable=False, server_default="10"),
    Column("started_at", Text, nullable=False),
    Column("completed_at", Text, nullable=True),
    CheckConstraint(
        "mode IN ('practice', 'retry', 'concept', 'quiz', 'replay')",
        name="ck_progress_sessions_mode",
    ),
)

progress_events = Table(
    "progress_events",
    metadata,
    Column("id", Text, primary_key=True),  # client-supplied UUIDv7 -- makes a resend a no-op
    Column("session_id", Text, ForeignKey("progress_sessions.id"), nullable=False),
    Column("profile_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("problem_id", Text, nullable=True),  # NULL for session_started/session_completed
    Column("payload_json", Text, nullable=False, server_default="{}"),
    Column("occurred_at", Text, nullable=False),  # client time, stored verbatim (AD-6)
    Column("received_at", Text, nullable=False),  # server time (testable clock)
    CheckConstraint(
        "kind IN ('attempt', 'hint_requested', 'solution_shown', 'fallback_revealed', "
        "'self_marked', 'quiz_submitted', 'session_started', 'session_completed')",
        name="ck_progress_events_kind",
    ),
)

progress_retry_items = Table(
    "progress_retry_items",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("profile_id", Text, nullable=False),
    Column("problem_id", Text, nullable=False),
    Column("added_at", Text, nullable=False),
    Column("resolved_at", Text, nullable=True),
)

progress_stars = Table(
    "progress_stars",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("session_id", Text, ForeignKey("progress_sessions.id"), nullable=False),
    Column("profile_id", Text, nullable=False),
    Column("problem_id", Text, nullable=False),
    Column("stars", Integer, nullable=False),
    Column("awarded_at", Text, nullable=False),
    CheckConstraint("stars IN (0, 1, 3)", name="ck_progress_stars_stars"),
)

Index("ix_progress_sessions_profile_id", progress_sessions.c.profile_id)
Index("ix_progress_events_session_id", progress_events.c.session_id)
Index(
    "ix_progress_events_profile_problem",
    progress_events.c.profile_id,
    progress_events.c.problem_id,
)
Index(
    "ix_progress_retry_items_profile_problem",
    progress_retry_items.c.profile_id,
    progress_retry_items.c.problem_id,
)
Index(
    "ux_progress_stars_session_problem",
    progress_stars.c.session_id,
    progress_stars.c.problem_id,
    unique=True,
)
Index("ix_progress_stars_profile_id", progress_stars.c.profile_id)
