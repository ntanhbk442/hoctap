"""`build_*` tables. Only the builder writes them (AD-2).

- `build_jobs`: one row per (`page_ref`, `stage`, `input_hash`); a stage is skipped when a
  `done` row with the same input hash exists.
- `build_costs`: the tokens and USD cost of every Claude call (each attempt).
- `build_page_results`: one row per problem draft of a page: the validated ProblemDoc
  JSON, or the invalid draft with its errors, plus the verify verdict (`verify_status`,
  `verify_reasons_json`, `needs_review`). A row starts `unverified` with `needs_review` 1.
- `build_runs` (Story 1.10): one row per background pilot run started from the Parent
  Area's Extraction screen. `builder.jobs.RunManager` is the only writer.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

build_jobs = Table(
    "build_jobs",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("page_ref", Text, nullable=False),  # {book_id}#p{page:03d}
    Column("stage", Text, nullable=False),  # render | extract | validate | verify
    Column("input_hash", Text, nullable=False),
    Column("status", Text, nullable=False),
    # pilot | full (Story 1.9): the gate's pilot scope is the `pilot` extract jobs.
    Column("run_kind", Text, nullable=False, server_default="pilot"),
    Column("output_json", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("status IN ('done', 'failed')", name="ck_build_jobs_status"),
    CheckConstraint("run_kind IN ('pilot', 'full')", name="ck_build_jobs_run_kind"),
    UniqueConstraint("page_ref", "stage", "input_hash", name="uq_build_jobs_key"),
    Index("ix_build_jobs_stage_status", "stage", "status"),
    Index("ix_build_jobs_run_kind", "run_kind", "page_ref"),
)

build_costs = Table(
    "build_costs",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("page_ref", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("input_hash", Text, nullable=False),  # the job the call was made for
    Column("attempt", Integer, nullable=False),  # 1, then 2 on the retry
    Column("model", Text, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cache_creation_input_tokens", Integer, nullable=False),
    Column("cache_read_input_tokens", Integer, nullable=False),
    Column("cost_usd", Float, nullable=False),  # as reported by the CLI (total_cost_usd)
    # 1 when the CLI reported no cost (a timeout, unparsable output): up to the call cap.
    Column("cost_unknown", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, nullable=False),
    Index("ix_build_costs_page_ref", "page_ref"),
)

build_page_results = Table(
    "build_page_results",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("page_ref", Text, nullable=False),
    Column("book_id", Text, nullable=False),
    Column("page", Integer, nullable=False),
    Column("draft_index", Integer, nullable=False),  # position in the page's `problems`
    Column("input_hash", Text, nullable=False),  # the validate job's input hash
    Column("status", Text, nullable=False),
    Column("problem_id", Text, nullable=True),  # null when no id could be built
    Column("duplicate", Integer, nullable=False, server_default="0"),
    Column("doc_json", Text, nullable=True),  # the validated ProblemDoc
    Column("draft_json", Text, nullable=False),  # the draft as extracted
    Column("errors_json", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    # Story 1.6: agree | disagree | unverified; the reasons; 1 hides the Problem.
    Column("verify_status", Text, nullable=False, server_default="unverified"),
    Column("verify_reasons_json", Text, nullable=True),
    Column("needs_review", Integer, nullable=False, server_default="1"),
    CheckConstraint("status IN ('valid', 'invalid')", name="ck_build_page_results_status"),
    CheckConstraint(
        "verify_status IN ('agree', 'disagree', 'unverified')",
        name="ck_build_page_results_verify_status",
    ),
    CheckConstraint("needs_review IN (0, 1)", name="ck_build_page_results_needs_review"),
    UniqueConstraint("page_ref", "draft_index", name="uq_build_page_results_draft"),
    Index("ix_build_page_results_problem_id", "problem_id"),
)

build_gate = Table(
    "build_gate",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("approved_at", Text, nullable=False),
    Column("metrics_json", Text, nullable=False),
    Column("thresholds_json", Text, nullable=False),
    Column("est_cost", Float, nullable=False),
    # FK to content_review_spot_check_samples.sample_id (declared in migration 0008; the
    # table lives in another module's MetaData).
    Column("sample_id", Text, nullable=False),
    Column("scope_hash", Text, nullable=False),  # sha256 of the sorted pilot page refs
    Column("revoked_at", Text, nullable=True),
)

build_runs = Table(
    "build_runs",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("book_id", Text, nullable=False),
    Column("first_page", Integer, nullable=False),
    Column("last_page", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("stage", Text, nullable=True),  # render | extract | validate | verify | crop | publish
    Column("pages_total", Integer, nullable=False),
    Column("pages_done", Integer, nullable=False, server_default="0"),
    Column("cost_usd", Float, nullable=False, server_default="0"),
    Column("cost_unknown_count", Integer, nullable=False, server_default="0"),
    Column("failed_pages_json", Text, nullable=False, server_default="[]"),
    Column("error", Text, nullable=True),
    # The paused/cancelled run this run resumes (Resume always starts a new row).
    Column("resumed_from", Text, nullable=True),
    Column("started_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("finished_at", Text, nullable=True),
    # Story 6.2: a full-corpus run is one row per Book, grouped by `full_id`. `max_total_usd`
    # is the overall cap of the whole run; `unstarted_json` lists the Books/pages a stopped
    # run did not reach; `options_json` is what a resume needs (grade / books).
    Column("run_kind", Text, nullable=False, server_default="pilot"),
    Column("full_id", Text, nullable=True),
    Column("max_total_usd", Float, nullable=True),
    Column("stop_reason", Text, nullable=True),
    Column("unstarted_json", Text, nullable=False, server_default="[]"),
    Column("options_json", Text, nullable=True),
    CheckConstraint(
        "status IN ('running', 'pausing', 'paused', 'done', 'failed', 'cancelled', "
        "'stopped_budget', 'stopped_checkpoint', 'stopped_gate')",
        name="ck_build_runs_status",
    ),
    CheckConstraint("run_kind IN ('pilot', 'full')", name="ck_build_runs_run_kind"),
    CheckConstraint(
        "stage IS NULL OR stage IN ('render', 'extract', 'validate', 'verify', 'crop', 'publish')",
        name="ck_build_runs_stage",
    ),
    Index("ix_build_runs_status", "status"),
    Index("ix_build_runs_book_id", "book_id"),
    Index("ix_build_runs_full_id", "full_id"),
)
