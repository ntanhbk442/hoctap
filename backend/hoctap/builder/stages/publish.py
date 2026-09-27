"""`publish`: the current valid `build_page_results` of a page range -> published content.

1. Which rows are current (Story 1.5's current-hash rule): the page's extract hash is
   computed from the images on disk, and only a `done` extraction with exactly that hash
   counts. A row is current when its `input_hash` equals the validate hash those
   extractions give its page and the page's `validate` job for that hash is `done`.
   Rows of any other page are stale: not published, and reported. A page whose images
   are missing (so its hash cannot be computed) falls back to its latest `done`
   extraction, so the missing image fails only the crops that need it.
2. `crop` cuts the images of every current valid row. A Problem whose crops fail is not
   published and is reported.
3. In one transaction, `content.catalog.publish_problems()` upserts the units, lessons and
   Problems (and retires vanished Problems of the touched Lessons), and
   `content.review.record_concept_proposals()` records the Concept proposals per Grade.
   The builder never writes `content_*` tables itself (AD-2).

Every valid row is published, `needs_review` and duplicate rows too (flagged: hiding is
the visibility gate's job). Invalid drafts are never published; they are counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, select

from hoctap.builder import jobs_store
from hoctap.builder.models import build_page_results
from hoctap.builder.stages import crop, validate
from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    PublishResult,
    UnitRow,
    publish_problems,
)
from hoctap.content.review.service import ProposalResult, record_concept_proposals
from hoctap.content.schema import ProblemDoc

STAGE = "publish"


@dataclass
class PublishReport:
    pages: list[int] = field(default_factory=list)  # requested pages that are current
    stale_pages: list[int] = field(default_factory=list)  # not current: nothing published
    invalid: int = 0  # invalid drafts on the current pages (never published)
    invalid_docs: dict[str, str] = field(default_factory=dict)  # stored doc fails validation
    crop: crop.CropReport = field(default_factory=crop.CropReport)
    result: PublishResult = field(default_factory=PublishResult)
    proposals: ProposalResult = field(default_factory=ProposalResult)
    needs_review: list[str] = field(default_factory=list)  # published, flagged
    duplicates: list[str] = field(default_factory=list)  # published, flagged
    missing_structure: list[str] = field(default_factory=list)  # unit / unit.lesson keys

    @property
    def published(self) -> int:
        r = self.result
        return len(r.inserted) + len(r.updated) + len(r.unchanged) + len(r.restored)

    @property
    def failed(self) -> dict[str, str]:
        """Problems that could not be published: crop failures and invalid stored docs."""
        return self.crop.failed | self.invalid_docs


@dataclass(frozen=True)
class _Row:
    page: int
    draft_index: int
    problem_id: str
    doc_json: str
    duplicate: int
    needs_review: int
    verify_status: str


def _effective_extractions(
    conn: Any, book_id: str, current: dict[int, str]
) -> dict[int, validate.PageInput]:
    """The extraction each page's validate hash is built from (see the module doc).

    Only the pages the latest book-level validate run used are considered, so the hashes
    are computed over the same page set as `run_validate()`."""
    book_ref = validate.book_job_ref(book_id)
    book_job = jobs_store.latest_done(conn, validate.STAGE, book_ref).get(book_ref)
    used = book_job.output.get("pages") if book_job and isinstance(book_job.output, dict) else None
    if not isinstance(used, list):
        return {}
    prefix = f"{book_id}#p"
    latest = {
        int(ref[len(prefix) :]): job
        for ref, job in jobs_store.latest_done(conn, "extract", prefix).items()
    }
    inputs: dict[int, validate.PageInput] = {}
    for page in sorted(p for p in used if isinstance(p, int)):
        ref = jobs_store.page_ref(book_id, page)
        if page in current:
            job = jobs_store.find_done(conn, ref, "extract", current[page])
        else:
            job = latest.get(page)  # images missing: assume the latest extraction
        if job is not None and isinstance(job.output, dict):
            inputs[page] = validate.PageInput(page, job.input_hash, job.output)
    return inputs


def run_publish(
    engine: Engine,
    data_dir: Path,
    book: BookRow,
    pages: list[int],
    current: dict[int, str],
) -> PublishReport:
    """Crops and publishes the current valid Problems of `pages` (see the module doc).

    `current` is the current extract hash of every page whose images are on disk.
    """
    report = PublishReport()
    book_id = book.book_id
    t = build_page_results
    wanted = set(pages)
    with engine.connect() as conn:
        inputs = _effective_extractions(conn, book_id, current)
        hashes = {p: i.extract_hash for p, i in inputs.items()}
        # The validate hash of every page whose rows are current (validated at that hash).
        book_expected: dict[int, str] = {}
        for page in sorted(inputs):
            h = validate.page_input_hash(book_id, book.page_count, page, hashes)
            ref = jobs_store.page_ref(book_id, page)
            if jobs_store.find_done(conn, ref, validate.STAGE, h) is not None:
                book_expected[page] = h
        expected = {p: h for p, h in book_expected.items() if p in wanted}
        all_rows = conn.execute(
            select(
                t.c.page,
                t.c.draft_index,
                t.c.status,
                t.c.problem_id,
                t.c.doc_json,
                t.c.input_hash,
                t.c.duplicate,
                t.c.needs_review,
                t.c.verify_status,
            )
            .where(t.c.book_id == book_id)
            .order_by(t.c.page, t.c.draft_index)
        ).all()

    stale: set[int] = set(wanted) - set(expected)
    rows: list[_Row] = []
    for r in all_rows:
        if r.page not in wanted:
            continue
        if r.page not in expected or r.input_hash != expected[r.page]:
            stale.add(r.page)
            continue
        if r.status != "valid" or r.problem_id is None or r.doc_json is None:
            report.invalid += 1
            continue
        rows.append(
            _Row(
                r.page,
                r.draft_index,
                r.problem_id,
                r.doc_json,
                r.duplicate,
                r.needs_review,
                r.verify_status,
            )
        )
    # A page with no rows at all is only stale when it is not current.
    report.stale_pages = sorted(stale)
    current_pages = sorted(wanted - stale)
    report.pages = current_pages
    rows = [r for r in rows if r.page in current_pages]

    docs: dict[str, ProblemDoc] = {}
    for row in rows:
        try:
            docs[row.problem_id] = ProblemDoc.model_validate_json(row.doc_json)
        except ValidationError as exc:
            report.invalid_docs[row.problem_id] = (
                f"stored doc no longer validates: {exc.error_count()} error(s): "
                f"{exc.errors(include_url=False)[0]['msg']}"
            )
    first_page = {row.problem_id: row.page for row in rows}  # the lowest source page
    report.crop = crop.run_crop(engine, data_dir, book_id, list(docs.values()))
    cropped = set(report.crop.ok)

    structure = validate.book_structure(list(inputs.values()))
    problems: list[ProblemInput] = []
    for row in rows:
        if row.problem_id not in cropped:
            continue
        doc = docs[row.problem_id].model_dump(mode="json")
        problems.append(
            ProblemInput(
                doc=doc,
                position=validate.position(row.page, row.draft_index),
                needs_review=bool(row.needs_review),
                verify_status=row.verify_status,
                duplicate=bool(row.duplicate),
            )
        )
        if row.needs_review:
            report.needs_review.append(row.problem_id)
        if row.duplicate:
            report.duplicates.append(row.problem_id)

    unit_keys = sorted({p.lesson[0] for p in problems})
    lesson_keys = sorted({p.lesson for p in problems})
    # A unit/lesson missing from the extracted structure is inserted blank when new, but
    # never overwrites an existing row (`insert_only`); it is reported.
    units = []
    for key in unit_keys:
        info = structure.units.get(key)
        if info is None:
            report.missing_structure.append(key)
            units.append(UnitRow(book_id, key, "", "", 0, insert_only=True))
        else:
            units.append(UnitRow(book_id, key, info.label, info.title, info.position))
    lessons = []
    for unit_key, lesson_key in lesson_keys:
        info = structure.lessons.get((unit_key, lesson_key))
        if info is None:
            report.missing_structure.append(f"{unit_key}.{lesson_key}")
            lessons.append(LessonRow(book_id, unit_key, lesson_key, "", "", 0, insert_only=True))
        else:
            lessons.append(
                LessonRow(book_id, unit_key, lesson_key, info.label, info.title, info.position)
            )

    # Still extracted but not published now (another page, a failed crop, a stale page, a
    # draft that is invalid this time): never retired on that account.
    present = {r.problem_id for r in all_rows if r.problem_id}
    touched = {(d.unit_key, d.lesson_key) for pid, d in docs.items() if pid not in report.failed}
    with engine.begin() as conn:
        report.result = publish_problems(
            conn,
            book_id,
            units=units,
            lessons=lessons,
            problems=problems,
            touched_lessons=touched,
            touch_pages=current_pages,
            current_pages=set(book_expected),
            present=present,
        )
        proposals: dict[str, list[str]] = dict.fromkeys(report.result.retired, [])
        proposals |= {p.problem_id: p.doc["concept_proposals"] for p in problems}
        report.proposals = record_concept_proposals(conn, book.grade, proposals)
        for page in current_pages:
            jobs_store.record(
                conn,
                jobs_store.page_ref(book_id, page),
                STAGE,
                expected[page],
                "done",
                output={
                    "published": sorted(
                        p.problem_id for p in problems if first_page[p.problem_id] == page
                    ),
                    "failed": sorted(pid for pid in report.failed if first_page.get(pid) == page),
                },
            )
    return report


def describe(report: PublishReport) -> list[str]:
    """The report lines printed by the CLI."""
    r = report.result
    lines = [
        f"crop: {report.crop.cut} cut, {report.crop.skipped} unchanged, "
        f"{len(report.crop.failed)} problem(s) failed",
        f"publish: {report.published} published ({len(r.inserted)} new, {len(r.updated)} "
        f"updated, {len(r.restored)} restored, {len(r.unchanged)} unchanged), "
        f"{len(r.retired)} retired, {report.invalid} invalid draft(s) not published; "
        f"{len(report.needs_review)} need review, {len(report.duplicates)} duplicate(s)",
        f"concept proposals: {len(report.proposals.new_keys)} new, "
        f"{report.proposals.links} link(s)",
    ]
    if r.retired:
        lines.append(f"retired (vanished from their lesson): {', '.join(r.retired)}")
    if r.restored:
        lines.append(f"restored: {', '.join(r.restored)}")
    if report.missing_structure:
        lines.append(
            "units/lessons with no extracted heading (label and position left blank): "
            + ", ".join(report.missing_structure)
        )
    if report.stale_pages:
        pages = ", ".join(str(p) for p in report.stale_pages)
        lines.append(
            f"stale pages (not published; run `hoctap build pilot` for them first): {pages}"
        )
    return lines


def nothing_current(report: PublishReport) -> bool:
    """Every requested page is stale: nothing could be published."""
    return not report.pages and bool(report.stale_pages)


def describe_failures(report: PublishReport) -> list[str]:
    if not report.failed:
        return []
    lines = [
        f"Cảnh báo / Warning: {len(report.failed)} bài không xuất bản được / problem(s) "
        "not published:"
    ]
    lines += [f"  - {pid}: {why}" for pid, why in sorted(report.failed.items())]
    return lines
