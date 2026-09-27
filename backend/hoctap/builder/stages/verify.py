"""`verify`: an independent second answer for every valid Problem of a page.

One Claude call per page that has valid `build_page_results` rows. The call gets the page
image, the images of every other source page of its Problems (a Problem continuing onto
the next page), and the child view of each Problem, so no extracted Answer Key, Hint or
Solution reaches it (AD-5). Its output is a `VerifyPage`; `builder.verify.compare` turns
it, the code arithmetic and the Hint check into one verdict per Problem, stored on the
Problem's row (`verify_status`, `verify_reasons_json`, `needs_review`). A stored doc that
no longer validates is not sent: its row is `unverified` with reason `invalid_doc`.

The calls, retries, cost records and the total budget cap are `builder.calls.run_calls`.
`input_hash` = sha256 of `verify_model`, the verify prompt version, system prompt, output
schema, the source page image hashes and the child-view JSON. The verdicts are recomputed
from the stored output on every run, so a re-run with nothing changed makes no call, and a
changed extracted answer (same child view) is compared again without a new call.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, select, update

from hoctap.builder import jobs_store
from hoctap.builder.calls import CallJob, CallReport, run_calls
from hoctap.builder.claude_client import ClaudeClient, PageRequest
from hoctap.builder.models import build_page_results
from hoctap.builder.stages import render
from hoctap.builder.verify.compare import (
    INVALID_DOC,
    NOT_RUN,
    UNVERIFIED,
    Reason,
    Verdict,
    verdict_for,
)
from hoctap.builder.verify.models import VerifyEnvelope, verify_schema
from hoctap.builder.verify.prompt import (
    VERIFY_PROMPT_VERSION,
    VERIFY_SYSTEM_PROMPT,
    verify_prompt,
)
from hoctap.config import Settings
from hoctap.content.schema import ProblemDoc
from hoctap.content.views import child_view

STAGE = "verify"


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ProblemRow:
    row_id: str
    problem_id: str
    doc: ProblemDoc


@dataclass(frozen=True)
class InvalidRow:
    """A stored doc that no longer validates: not sent, marked `invalid_doc`."""

    row_id: str
    problem_id: str
    error: str


@dataclass(frozen=True)
class PageImage:
    page: int
    path: Path
    sha: str | None  # None: not rendered


@dataclass(frozen=True)
class VerifyTask:
    book_id: str
    page: int
    image: PageImage
    other_images: tuple[PageImage, ...]  # the other source pages of the page's Problems
    problems: tuple[ProblemRow, ...]
    invalid: tuple[InvalidRow, ...] = ()

    @property
    def ref(self) -> str:
        return jobs_store.page_ref(self.book_id, self.page)

    @property
    def rendered(self) -> bool:
        return all(i.sha is not None for i in (self.image, *self.other_images))

    def child_views(self) -> list[dict[str, Any]]:
        return [child_view(p.doc).model_dump(mode="json") for p in self.problems]


def _image(settings: Settings, book_id: str, page: int) -> PageImage:
    path = settings.data_dir / render.image_rel_path(book_id, page)
    return PageImage(page, path, render.image_sha256(path))


def load_tasks(
    engine: Engine, settings: Settings, book_id: str, pages: list[int] | None = None
) -> list[VerifyTask]:
    """One task per page (of `pages`, or every page of the book) with valid rows."""
    t = build_page_results
    query = select(t.c.id, t.c.page, t.c.problem_id, t.c.doc_json).where(
        t.c.book_id == book_id,
        t.c.status == "valid",
        t.c.problem_id.is_not(None),
        t.c.doc_json.is_not(None),
    )
    if pages is not None:
        query = query.where(t.c.page.in_(pages))
    with engine.connect() as conn:
        rows = conn.execute(query.order_by(t.c.page, t.c.draft_index)).all()
    valid: dict[int, list[ProblemRow]] = {}
    invalid: dict[int, list[InvalidRow]] = {}
    for row in rows:
        try:
            doc = ProblemDoc.model_validate_json(row.doc_json)
        except ValidationError as exc:
            error = f"{exc.error_count()} error(s): {exc.errors(include_url=False)[0]['msg']}"
            invalid.setdefault(row.page, []).append(InvalidRow(row.id, row.problem_id, error))
            continue
        valid.setdefault(row.page, []).append(ProblemRow(row.id, row.problem_id, doc))
    tasks = []
    for page in sorted(set(valid) | set(invalid)):
        problems = valid.get(page, [])
        others = sorted({s.page for p in problems for s in p.doc.source_pages} - {page})
        tasks.append(
            VerifyTask(
                book_id=book_id,
                page=page,
                image=_image(settings, book_id, page),
                other_images=tuple(_image(settings, book_id, other) for other in others),
                problems=tuple(problems),
                invalid=tuple(invalid.get(page, [])),
            )
        )
    return tasks


def verify_input_hash(task: VerifyTask, settings: Settings) -> str:
    return _sha(
        {
            "model": settings.verify_model,
            "prompt_version": VERIFY_PROMPT_VERSION,
            "system": _sha(VERIFY_SYSTEM_PROMPT),
            "schema": _sha(verify_schema()),
            "page": task.image.sha,
            "other_pages": [[i.page, i.sha] for i in task.other_images],
            "problems": task.child_views(),
        }
    )


def build_request(task: VerifyTask, settings: Settings) -> PageRequest:
    return PageRequest(
        page_ref=task.ref,
        prompt=verify_prompt(
            task.page,
            task.image.path.resolve(),
            [(i.page, i.path.resolve()) for i in task.other_images],
            task.child_views(),
        ),
        system_prompt=VERIFY_SYSTEM_PROMPT,
        schema=verify_schema(),
        model=settings.verify_model or settings.extraction_model,
        add_dir=task.image.path.parent.resolve(),
        max_budget_usd=settings.extraction_max_budget_usd,
        timeout_seconds=settings.extraction_timeout_seconds,
        stage=STAGE,
    )


def _check_output(output: dict[str, Any] | None) -> str | None:
    """Why the output is not a usable verify page, or None. Problems are checked later."""
    try:
        VerifyEnvelope.model_validate(output)
    except ValidationError as exc:
        return f"output is not a verify page: {exc}"
    return None


def pending(
    engine: Engine, tasks: list[VerifyTask], settings: Settings
) -> list[tuple[VerifyTask, str]]:
    """The rendered tasks with Problems to send and no `done` verify job for their current
    input hash."""
    todo = []
    with engine.connect() as conn:
        for task in tasks:
            if not task.problems or not task.rendered:
                continue
            input_hash = verify_input_hash(task, settings)
            if jobs_store.find_done(conn, task.ref, STAGE, input_hash) is None:
                todo.append((task, input_hash))
    return todo


def run_verify(
    engine: Engine,
    client: ClaudeClient,
    todo: list[tuple[VerifyTask, str]],
    settings: Settings,
    on_page: Callable[[str, str], None] = lambda ref, status: None,
    max_total_usd: float | None = None,
) -> CallReport:
    """Calls Claude for each pending page (see `builder.calls.run_calls`)."""
    jobs = [
        CallJob(task.ref, STAGE, input_hash, build_request(task, settings), _check_output)
        for task, input_hash in todo
    ]
    return run_calls(engine, client, jobs, settings, on_page, max_total_usd)


@dataclass
class VerdictReport:
    counts: Counter[str] = field(default_factory=Counter)  # agree | disagree | unverified
    needs_review: dict[str, list[Reason]] = field(default_factory=dict)  # problem_id -> why
    unrendered_pages: list[int] = field(default_factory=list)
    invalid_docs: list[str] = field(default_factory=list)  # problem ids
    not_run_pages: list[int] = field(default_factory=list)  # no result for the current input


def second_answers(output: Any, known: set[str]) -> tuple[dict[str, Any], dict[str, str]]:
    """(problem_id -> its output entry, problem_id -> why the output is inconsistent for it).

    A problem_id given twice is inconsistent for that Problem; an entry whose problem_id is
    unknown (or missing) makes the output inconsistent for every Problem of the page."""
    problems = output.get("problems") if isinstance(output, dict) else None
    entries = problems if isinstance(problems, list) else []
    ids = [e.get("problem_id") if isinstance(e, dict) else None for e in entries]
    counts = Counter(ids)
    found: dict[str, Any] = {}
    for pid, entry in zip(ids, entries, strict=True):
        if isinstance(pid, str):
            found.setdefault(pid, entry)
    invalid: dict[str, str] = {}
    unknown = sorted(str(pid) for pid in counts if pid not in known)
    if unknown:
        invalid = {pid: f"unknown problem_ids in the output: {unknown}" for pid in known}
    for pid, n in counts.items():
        if pid in known and n > 1:
            invalid[pid] = f"problem_id given {n} times"
    return found, invalid


def apply_verdicts(engine: Engine, tasks: list[VerifyTask], settings: Settings) -> VerdictReport:
    """Computes every Problem's verdict from the page's verify job for its current input
    and stores it on the Problem's row, in one transaction. No call is made."""
    report = VerdictReport()
    t = build_page_results

    def store(conn: Any, row_id: str, problem_id: str, verdict: Verdict) -> None:
        report.counts[verdict.status] += 1
        if verdict.needs_review:
            report.needs_review[problem_id] = verdict.reasons
        conn.execute(
            update(t)
            .where(t.c.id == row_id)
            .values(
                verify_status=verdict.status,
                verify_reasons_json=json.dumps(verdict.reasons_json(), ensure_ascii=False),
                needs_review=int(verdict.needs_review),
            )
        )

    with engine.begin() as conn:
        for task in tasks:
            for bad in task.invalid:
                report.invalid_docs.append(bad.problem_id)
                reason = Reason(None, INVALID_DOC, second=bad.error)
                store(conn, bad.row_id, bad.problem_id, Verdict(UNVERIFIED, [reason]))
            if not task.problems:
                continue
            job = None
            if task.rendered:
                input_hash = verify_input_hash(task, settings)
                job = jobs_store.get_job(conn, task.ref, STAGE, input_hash)
            else:
                report.unrendered_pages.append(task.page)
            if job is None and task.rendered:
                report.not_run_pages.append(task.page)
            done = job is not None and job.status == "done"
            known = {p.problem_id for p in task.problems}
            seconds, inconsistent = second_answers(job.output, known) if done else ({}, {})
            for problem in task.problems:
                if job is None:
                    verdict = Verdict(UNVERIFIED, [Reason(None, NOT_RUN)])
                elif not done:
                    verdict = verdict_for(problem.doc, None, failure=job.error or "failed")
                else:
                    verdict = verdict_for(
                        problem.doc,
                        seconds.get(problem.problem_id),
                        invalid=inconsistent.get(problem.problem_id),
                    )
                store(conn, problem.row_id, problem.problem_id, verdict)
    return report
