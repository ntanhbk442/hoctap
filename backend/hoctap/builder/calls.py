"""The shared call machinery of the Claude stages (extract, verify): one call per page.

Calls run in a bounded pool (`extraction_concurrency`). A transient failure, or an output
the stage's `check` rejects, is retried once; after that, or on a permanent failure
(refusal, schema failure, budget cap, auth, unknown model), the page's job is `failed`
and the run goes on. Every attempt's cost is recorded in `build_costs`. Each page's result
is written as soon as it arrives, so a crash loses only calls in flight. No new page starts
once the run's spend (unknown-cost calls counted at the per-call cap) reaches the total cap.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine

from hoctap.builder import costs, jobs_store
from hoctap.builder.claude_client import CallResult, ClaudeClient, PageRequest
from hoctap.config import Settings

MAX_ATTEMPTS = costs.MAX_ATTEMPTS

# Why an output is not usable for the stage, or None.
Check = Callable[[dict[str, Any] | None], str | None]


@dataclass(frozen=True)
class CallJob:
    """One page's call: the job key (`ref`, `stage`, `input_hash`) and its request."""

    ref: str
    stage: str
    input_hash: str
    request: PageRequest
    check: Check
    run_kind: str = "pilot"  # pilot | full: stored on the job row when it is first inserted


@dataclass
class _Outcome:
    attempts: list[CallResult]
    error: str | None  # None: done
    crash: Exception | None = None  # the client raised: no job is recorded


def _call(client: ClaudeClient, job: CallJob) -> _Outcome:
    attempts: list[CallResult] = []
    error: str | None = None
    try:
        for _ in range(MAX_ATTEMPTS):
            result = client.extract(job.request)
            attempts.append(result)
            if result.ok:
                error = job.check(result.output)
                if error is None:
                    return _Outcome(attempts, None)
                continue  # an unusable output is retried once
            error = result.error or "call failed (no error message)"
            if not result.transient:
                break
    except Exception as exc:  # noqa: BLE001 - kept with the attempts made so far
        return _Outcome(attempts, error or "crashed", exc)
    return _Outcome(attempts, error)


def _spend(attempts: list[CallResult], settings: Settings) -> float:
    cap = settings.extraction_max_budget_usd
    return sum(a.cost_usd + (cap if a.cost_unknown else 0.0) for a in attempts)


@dataclass
class CallReport:
    calls: int = 0
    done: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0
    unknown_cost_calls: int = 0
    budget_skipped: list[str] = field(default_factory=list)  # not started: total cap reached
    spent_usd: float = 0.0  # the spend counted against the cap (unknown costs at the cap)


def _record(engine: Engine, job: CallJob, outcome: _Outcome) -> None:
    with engine.begin() as conn:
        for number, attempt in enumerate(outcome.attempts, start=1):
            costs.record_call(
                conn,
                page_ref=job.ref,
                stage=job.stage,
                input_hash=job.input_hash,
                attempt=number,
                model=job.request.model,
                result=attempt,
            )
        if outcome.crash is not None:
            return
        if outcome.error is None:
            output = outcome.attempts[-1].output
            jobs_store.record(
                conn,
                job.ref,
                job.stage,
                job.input_hash,
                "done",
                output=output,
                run_kind=job.run_kind,
            )
        else:
            jobs_store.record(
                conn,
                job.ref,
                job.stage,
                job.input_hash,
                "failed",
                error=outcome.error,
                run_kind=job.run_kind,
            )


def run_calls(
    engine: Engine,
    client: ClaudeClient,
    jobs: list[CallJob],
    settings: Settings,
    on_page: Callable[[str, str], None] = lambda ref, status: None,
    max_total_usd: float | None = None,
) -> CallReport:
    """Calls Claude for each job and records the job and its costs.

    A page starts only while the run's spend is below `max_total_usd` (default: the
    config's `extraction_max_total_usd`). If a call raises (a bug, not a failed call) or a
    database write fails, the other pages are still collected and recorded, and the first
    exception is raised at the end; a page whose call raised has no job and is retried on
    the next run. On Ctrl-C, pages not started are cancelled, running CLI children are
    terminated (`client.terminate_all()`), and KeyboardInterrupt propagates.
    """
    report = CallReport()
    cap = settings.extraction_max_total_usd if max_total_usd is None else max_total_usd
    queue = list(jobs)
    first_error: Exception | None = None
    workers = settings.extraction_concurrency
    pool = ThreadPoolExecutor(max_workers=workers)
    running: dict[Future[_Outcome], CallJob] = {}
    try:
        while queue or running:
            while queue and len(running) < workers:
                if report.spent_usd >= cap:
                    report.budget_skipped = [job.ref for job in queue]
                    queue.clear()
                    break
                job = queue.pop(0)
                running[pool.submit(_call, client, job)] = job
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                job = running.pop(future)
                outcome = future.result()
                report.spent_usd += _spend(outcome.attempts, settings)
                report.calls += len(outcome.attempts)
                report.cost_usd += sum(a.cost_usd for a in outcome.attempts)
                report.unknown_cost_calls += sum(a.cost_unknown for a in outcome.attempts)
                try:
                    _record(engine, job, outcome)
                except Exception as exc:  # noqa: BLE001 - keep collecting, raise at the end
                    first_error = first_error or exc
                    report.failed[job.ref] = f"not recorded: {exc}"
                    on_page(job.ref, f"not recorded: {exc}")
                    continue
                if outcome.crash is not None:
                    first_error = first_error or outcome.crash
                    on_page(job.ref, f"crashed: {outcome.crash!r}")
                elif outcome.error is None:
                    report.done.append(job.ref)
                    on_page(job.ref, "done")
                else:
                    report.failed[job.ref] = outcome.error
                    on_page(job.ref, f"failed: {outcome.error}")
    except KeyboardInterrupt:
        for future in running:
            future.cancel()
        terminate = getattr(client, "terminate_all", None)
        if terminate is not None:
            terminate()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if first_error is not None:
        raise first_error
    report.done.sort()
    return report
