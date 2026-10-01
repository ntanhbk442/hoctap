"""Story 1.5 finding #22 (2026-10-01, Orchestrator's Independent Audit): `_record()` in
`builder/calls.py` used to write the `build_costs` row and the `build_jobs` done/failed
row in the SAME transaction, so a paid call's cost row could be rolled back along with a
later, unrelated job-row write failure, leaving no trace the call was ever billed. These
tests exercise `_record()` directly (no real Claude call; `CallResult`/`_Outcome` are
built by hand) to pin the fixed behaviour: the cost row is committed on its own, before
the job-status write, and survives even when the job-status write then fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from hoctap.builder import jobs_store
from hoctap.builder.calls import CallJob, _Outcome, _record
from hoctap.builder.claude_client import CallResult, PageRequest, Usage
from hoctap.builder.models import build_costs, build_jobs
from hoctap.db.engine import create_db_engine, run_migrations

PAGE_REF = "toan1-2020-q1#p005"


@pytest.fixture
def engine(tmp_path: Path):
    engine = create_db_engine(tmp_path / "hoctap.db")
    run_migrations(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _job() -> CallJob:
    request = PageRequest(
        page_ref=PAGE_REF,
        prompt="p",
        system_prompt="s",
        schema={},
        model="claude-opus-5",
        add_dir=Path("/tmp"),
        max_budget_usd=0.5,
        timeout_seconds=60,
    )
    return CallJob(
        ref=PAGE_REF,
        stage="extract",
        input_hash="h1",
        request=request,
        check=lambda output: None,
    )


def _paid_attempt() -> CallResult:
    return CallResult(ok=True, output={"problems": []}, cost_usd=0.1234, usage=Usage(1, 2, 0, 0))


def test_cost_row_committed_before_job_row(engine) -> None:
    """The happy path: cost row(s) then the job row, both visible after `_record()`."""
    job = _job()
    outcome = _Outcome(attempts=[_paid_attempt()], error=None)
    _record(engine, job, outcome)
    with engine.connect() as conn:
        costs = list(conn.execute(select(build_costs.c.cost_usd)))
        assert [c[0] for c in costs] == [0.1234]
        done = jobs_store.find_done(conn, PAGE_REF, "extract", "h1")
        assert done is not None


def test_paid_cost_row_survives_a_failing_job_write(
    engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paid call's cost row must not be rolled back just because the SEPARATE job-status
    write that follows it then fails (disk full, transient lock, constraint violation)."""

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated job-row write failure")

    monkeypatch.setattr(jobs_store, "record", boom)
    job = _job()
    outcome = _Outcome(attempts=[_paid_attempt()], error=None)
    with pytest.raises(RuntimeError, match="simulated job-row write failure"):
        _record(engine, job, outcome)
    with engine.connect() as conn:
        # The cost row committed in its own transaction before the job write ran, so it
        # survives even though the job-status write raised.
        costs = list(conn.execute(select(build_costs.c.cost_usd)))
        assert [c[0] for c in costs] == [0.1234]
        # No job row exists: the next run correctly sees this page as not-yet-done and
        # retries it (and records that retry's cost too) rather than silently losing it.
        assert jobs_store.get_job(conn, PAGE_REF, "extract", "h1") is None


def test_crash_records_cost_but_no_job_row(engine) -> None:
    """A client crash (a bug, not a failed call): the cost of attempts already made is
    still recorded, but no job row is written (unchanged behaviour)."""
    job = _job()
    outcome = _Outcome(attempts=[_paid_attempt()], error="crashed", crash=RuntimeError("boom"))
    _record(engine, job, outcome)
    with engine.connect() as conn:
        costs = list(conn.execute(select(build_costs.c.cost_usd)))
        assert [c[0] for c in costs] == [0.1234]
        assert conn.execute(select(build_jobs.c.id)).first() is None
