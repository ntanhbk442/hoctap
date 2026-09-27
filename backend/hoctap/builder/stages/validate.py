"""`validate`: page extractions -> ProblemDocs, with deterministic structural keys.

Within a book, in page order:

- The unit and lesson headings are carried forward. `unit_key`/`lesson_key` are slugs of
  the heading labels ("TUẦN 3" -> "tuan03", "Tiết 2" -> "tiet2", "Phiếu tự luyện cuối
  tuần" -> "phieu"); pages before the first heading use "u00"/"l00". A new unit heading
  resets the lesson to "l00". A heading applies from its `y` down: a problem whose bbox
  top is above the heading keeps the previous unit/lesson. A heading whose label gives
  no key is ignored (the previous keys stay) and reported as a page warning.
- `problem_id` follows the ProblemDoc rule `{book_id}.{unit_key}.{lesson_key}.{label}`.
  A valid draft whose id is taken gets the first free "-2", "-3"... suffix (the label is
  shortened so it stays a key) and is flagged `duplicate`. Invalid drafts take no id.
- A draft with `continues_on_next_page` gains the next page as a source page, and its
  `on_next_page` images are placed on the next page.
- Each draft is validated on its own: an invalid draft is stored with its errors and the
  other drafts and pages are unaffected.

`run_validate()` rebuilds every `build_page_results` row of the book in one transaction,
from the `done` extractions whose extract hash is the page's current one; pages with rows
or extractions but no current extraction lose their rows and are reported as stale.
Rebuilt rows are `unverified` with `needs_review` = 1 until `verify` runs again.
`input_hash` of page p = sha256 of the validator and ProblemDoc versions and the extract
hashes of every current page of the book up to p + 1; the book-level job
(`{book_id}#book`) hashes all of them and is the skip check (latest wins, so A -> B -> A
rebuilds).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, delete, insert, select

from hoctap.builder import jobs_store
from hoctap.builder.extraction.models import ProblemDraft
from hoctap.builder.models import build_page_results
from hoctap.content.schema import KEY_PATTERN, SCHEMA_VERSION, ProblemDoc
from hoctap.ids import new_id, to_iso, utc_now

STAGE = "validate"
VALIDATE_VERSION = "v2"
UNIT_DEFAULT = "u00"
LESSON_DEFAULT = "l00"

_KEY_RE = re.compile(KEY_PATTERN)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50}
_CANONICAL_ROMAN = re.compile(r"^(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _roman(word: str) -> int | None:
    if not word or not _CANONICAL_ROMAN.fullmatch(word):
        return None
    total = 0
    for i, c in enumerate(word):
        value = _ROMAN[c]
        total += -value if i + 1 < len(word) and _ROMAN[word[i + 1]] > value else value
    return total


def heading_key(label: str) -> str | None:
    """The structural key for a heading label, or None when the label has no letters."""
    text = _ascii(label)
    words = re.findall(r"[a-z]+", text)
    digits = re.search(r"\d+", text)
    if not words:
        return None
    if words[:2] == ["chu", "de"]:
        base, rest = "chude", words[2:]
    elif words[:2] == ["on", "tap"]:
        base, rest = "ontap", words[2:]
    else:
        base, rest = words[0], words[1:]
    number = int(digits.group()) if digits else (_roman(rest[0]) if rest else None)
    if base == "phieu":
        key = "phieu" if number is None else f"phieu{number}"
    elif base == "tuan" and number is not None:
        key = f"tuan{number:02d}"
    else:
        key = f"{base}{'' if number is None else number}"
    key = key[:16]
    return key if _KEY_RE.fullmatch(key) else None


def _heading_label(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("label"), str):
        label = value["label"].strip()
        return label or None
    return None


def _heading_y(value: dict[str, Any]) -> float:
    y = value.get("y")
    if isinstance(y, int | float) and not isinstance(y, bool) and 0 <= y <= 1:
        return float(y)
    return 0.0  # no usable position: the heading applies to the whole page


def _draft_top(raw: Any) -> float:
    """The top of a draft's bbox, or 1.0 (below every heading) when it has none."""
    bbox = raw.get("bbox") if isinstance(raw, dict) else None
    if isinstance(bbox, list) and len(bbox) == 4:
        top = bbox[1]
        if isinstance(top, int | float) and not isinstance(top, bool):
            return float(top)
    return 1.0


def _errors(exc: ValidationError) -> list[dict[str, Any]]:
    return json.loads(exc.json(include_url=False))


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PageInput:
    page: int
    extract_hash: str
    data: dict[str, Any]


@dataclass
class DraftOutcome:
    draft_index: int
    status: str  # valid | invalid
    problem_id: str | None
    duplicate: bool
    doc: dict[str, Any] | None
    draft: Any
    errors: list[dict[str, Any]] | None


@dataclass
class PageOutcome:
    page: int
    input_hash: str
    unit_key: str  # the keys in force at the bottom of the page
    lesson_key: str
    drafts: list[DraftOutcome] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Event:
    y: float
    kind: str  # unit | lesson
    key: str
    label: str = ""  # the heading as printed (NFC), for the book structure
    title: str = ""


def _page_events(data: dict[str, Any], warnings: list[str]) -> list[_Event]:
    events = []
    for kind in ("unit", "lesson"):
        value = data.get(f"{kind}_heading")
        if value is None:
            continue
        label = _heading_label(value)
        key = heading_key(label) if label is not None else None
        if key is None:
            warnings.append(f"{kind} heading {label!r} gives no key; the previous one is kept")
            continue
        events.append(_Event(_heading_y(value), kind, key, *_heading_text(value)))
    return sorted(events, key=lambda e: (e.y, e.kind != "unit"))


def _apply(unit: str, lesson: str, events: list[_Event], top: float) -> tuple[str, str]:
    for event in events:
        if event.y > top:
            break
        if event.kind == "unit":
            unit, lesson = event.key, LESSON_DEFAULT
        else:
            lesson = event.key
    return unit, lesson


def page_input_hash(
    book_id: str, page_count: int, page: int, extract_hashes: dict[int, str]
) -> str:
    """The validate `input_hash` of `page`, given the extract hash of every current page."""
    chain = [(p, h) for p, h in sorted(extract_hashes.items()) if p <= page + 1]
    return _sha([VALIDATE_VERSION, SCHEMA_VERSION, book_id, page_count, chain])


def validate_book(book_id: str, pages: list[PageInput], page_count: int) -> list[PageOutcome]:
    """Pure: validates the extracted pages of one book, in page order."""
    pages = sorted(pages, key=lambda p: p.page)
    unit, lesson = UNIT_DEFAULT, LESSON_DEFAULT
    used: set[str] = set()
    outcomes: list[PageOutcome] = []
    hashes = {p.page: p.extract_hash for p in pages}
    for page in pages:
        input_hash = page_input_hash(book_id, page_count, page.page, hashes)
        warnings: list[str] = []
        events = _page_events(page.data, warnings)
        problems = page.data.get("problems")
        drafts = []
        for index, raw in enumerate(problems if isinstance(problems, list) else []):
            keys = _apply(unit, lesson, events, _draft_top(raw))
            drafts.append(_validate_draft(book_id, page.page, page_count, *keys, index, raw, used))
        unit, lesson = _apply(unit, lesson, events, 1.0)
        outcomes.append(PageOutcome(page.page, input_hash, unit, lesson, drafts, warnings))
    return outcomes


@dataclass(frozen=True)
class HeadingInfo:
    """A unit or lesson as the book prints it: its heading (empty for the defaults and
    for keys whose heading was not seen) and where it first appears."""

    label: str
    title: str
    position: int  # `position(first page, order of appearance on that page)`


@dataclass
class BookStructure:
    units: dict[str, HeadingInfo] = field(default_factory=dict)
    lessons: dict[tuple[str, str], HeadingInfo] = field(default_factory=dict)


def _heading_text(value: Any) -> tuple[str, str]:
    label = _heading_label(value) or ""
    title = value.get("title") if isinstance(value, dict) else None
    clean = unicodedata.normalize("NFC", title.strip()) if isinstance(title, str) else ""
    return unicodedata.normalize("NFC", label), clean


POSITION_SCALE = 10_000  # positions of units, lessons and Problems: page * scale + order


def position(page: int, order: int) -> int:
    """The shared ordering key: page first, then the order on the page."""
    if not 0 <= order < POSITION_SCALE:
        raise ValueError(f"order {order} on page {page} is outside 0-{POSITION_SCALE - 1}")
    return page * POSITION_SCALE + order


def book_structure(pages: list[PageInput]) -> BookStructure:
    """Pure: the units and lessons of the extracted pages, with the same carry-forward rule
    as `validate_book()`. The first appearance of a key gives its label, title and position."""
    structure = BookStructure()
    unit, lesson = UNIT_DEFAULT, LESSON_DEFAULT
    for page in sorted(pages, key=lambda p: p.page):
        order = 0
        problems = page.data.get("problems")
        tops = [_draft_top(raw) for raw in (problems if isinstance(problems, list) else [])]
        marks: list[tuple[float, int, _Event | None]] = [
            (e.y, 0 if e.kind == "unit" else 1, e) for e in _page_events(page.data, [])
        ]
        marks += [(top, 2, None) for top in tops]
        for _, _, event in sorted(marks, key=lambda m: (m[0], m[1])):
            unit_text = lesson_text = ("", "")
            if event is not None and event.kind == "unit":
                unit, lesson = event.key, LESSON_DEFAULT
                unit_text = (event.label, event.title)
            elif event is not None:
                lesson = event.key
                lesson_text = (event.label, event.title)
            if unit not in structure.units:
                order += 1
                structure.units[unit] = HeadingInfo(*unit_text, position(page.page, order))
            if (unit, lesson) not in structure.lessons:
                order += 1
                info = HeadingInfo(*lesson_text, position(page.page, order))
                structure.lessons[(unit, lesson)] = info
    return structure


def _suffixed(label: str, n: int) -> str:
    suffix = f"-{n}"
    return label[: 16 - len(suffix)] + suffix


def _validate_draft(
    book_id: str,
    page: int,
    page_count: int,
    unit: str,
    lesson: str,
    index: int,
    raw: Any,
    used: set[str],
) -> DraftOutcome:
    label = raw.get("problem_label") if isinstance(raw, dict) else None
    problem_id: str | None = None
    if isinstance(label, str) and _KEY_RE.fullmatch(label):
        problem_id = f"{book_id}.{unit}.{lesson}.{label}"
    try:
        draft = ProblemDraft.model_validate(raw)
    except ValidationError as exc:
        return DraftOutcome(index, "invalid", problem_id, False, None, raw, _errors(exc))
    label = draft.problem_label

    source_pages = [{"page": page, "bbox": draft.bbox}]
    if draft.continues_on_next_page:
        if page + 1 > page_count:
            error = {
                "type": "continuation",
                "loc": ["continues_on_next_page"],
                "msg": f"page {page} is the last page of the book ({page_count})",
            }
            return DraftOutcome(index, "invalid", problem_id, False, None, raw, [error])
        source_pages.append({"page": page + 1, "bbox": draft.next_page_bbox})
    doc = {
        "schema_version": SCHEMA_VERSION,
        "problem_id": f"{book_id}.{unit}.{lesson}.{label}",
        "book_id": book_id,
        "unit_key": unit,
        "lesson_key": lesson,
        "problem_label": label,
        "display_label": draft.display_label,
        "instruction": draft.instruction,
        "layout": draft.layout,
        "source_pages": source_pages,
        "images": [
            {
                "image_key": image.image_key,
                "page": page + 1 if image.on_next_page else page,
                "bbox": image.bbox,
            }
            for image in draft.images
        ],
        "concept_ids": [],  # curated ids are tagged in Story 1.7; names go to proposals
        "concept_proposals": draft.concept_proposals,
        "parts": [part.model_dump(mode="json") for part in draft.parts],
    }
    try:
        valid = ProblemDoc.model_validate(doc)
    except ValidationError as exc:
        return DraftOutcome(index, "invalid", problem_id, False, None, raw, _errors(exc))
    duplicate = valid.problem_id in used
    n = 1
    while valid.problem_id in used:
        n += 1
        new_label = _suffixed(label, n)
        doc |= {"problem_label": new_label, "problem_id": f"{book_id}.{unit}.{lesson}.{new_label}"}
        valid = ProblemDoc.model_validate(doc)
    used.add(valid.problem_id)
    return DraftOutcome(
        index, "valid", valid.problem_id, duplicate, valid.model_dump(mode="json"), raw, None
    )


@dataclass
class ValidateReport:
    unchanged: bool = False
    pages: int = 0  # pages with a current extraction
    stale_pages: list[int] = field(default_factory=list)  # rows removed: no current extraction
    valid: int = 0
    invalid: int = 0
    duplicates: list[str] = field(default_factory=list)
    warnings: dict[int, list[str]] = field(default_factory=dict)


def book_job_ref(book_id: str) -> str:
    return f"{book_id}#book"


def _result_pages(conn: Connection, book_id: str) -> set[int]:
    t = build_page_results
    return {r[0] for r in conn.execute(select(t.c.page).where(t.c.book_id == book_id).distinct())}


def run_validate(
    engine: Engine, book_id: str, page_count: int, current: dict[int, str]
) -> ValidateReport:
    """Rebuilds all of the book's `build_page_results` from its current extractions.

    `current` maps every page whose current extract hash is known (its images are
    rendered) to that hash. Only a `done` extraction with exactly that hash is used.
    """
    prefix = f"{book_id}#p"
    report = ValidateReport()
    with engine.begin() as conn:
        extracted = {
            int(ref[len(prefix) :]) for ref in jobs_store.latest_done(conn, "extract", prefix)
        }
        inputs: list[PageInput] = []
        stale: list[int] = []
        with_rows = _result_pages(conn, book_id)
        for page in sorted(extracted | set(current) | with_rows):
            extract_hash = current.get(page)
            ref = jobs_store.page_ref(book_id, page)
            job = jobs_store.find_done(conn, ref, "extract", extract_hash) if extract_hash else None
            if job is not None and isinstance(job.output, dict):
                inputs.append(PageInput(page, extract_hash, job.output))
            elif page in extracted or page in with_rows:
                stale.append(page)
        outcomes = validate_book(book_id, inputs, page_count)
        report.pages = len(outcomes)
        report.stale_pages = stale
        for outcome in outcomes:
            report.valid += sum(d.status == "valid" for d in outcome.drafts)
            report.invalid += sum(d.status == "invalid" for d in outcome.drafts)
            report.duplicates += [
                d.problem_id for d in outcome.drafts if d.duplicate and d.problem_id
            ]
            if outcome.warnings:
                report.warnings[outcome.page] = outcome.warnings

        book_hash = _sha(
            [VALIDATE_VERSION, SCHEMA_VERSION, [(o.page, o.input_hash) for o in outcomes], stale]
        )
        latest = jobs_store.latest_done(conn, STAGE, book_job_ref(book_id)).get(
            book_job_ref(book_id)
        )
        if latest is not None and latest.input_hash == book_hash:
            report.unchanged = True
            return report
        conn.execute(delete(build_page_results).where(build_page_results.c.book_id == book_id))
        for outcome in outcomes:
            _write_page(conn, book_id, outcome)
        jobs_store.record(
            conn,
            book_job_ref(book_id),
            STAGE,
            book_hash,
            "done",
            output={"pages": [o.page for o in outcomes], "stale_pages": stale},
        )
    return report


def _write_page(conn: Connection, book_id: str, outcome: PageOutcome) -> None:
    t = build_page_results
    ref = jobs_store.page_ref(book_id, outcome.page)
    stamp = to_iso(utc_now())
    for d in outcome.drafts:
        conn.execute(
            insert(t).values(
                id=new_id(),
                page_ref=ref,
                book_id=book_id,
                page=outcome.page,
                draft_index=d.draft_index,
                input_hash=outcome.input_hash,
                status=d.status,
                problem_id=d.problem_id,
                duplicate=int(d.duplicate),
                doc_json=None if d.doc is None else json.dumps(d.doc, ensure_ascii=False),
                draft_json=json.dumps(d.draft, ensure_ascii=False),
                errors_json=None if d.errors is None else json.dumps(d.errors, ensure_ascii=False),
                created_at=stamp,
                # A rebuilt row is unverified (and hidden) until the verify stage runs again.
                verify_status="unverified",
                verify_reasons_json=None,
                needs_review=1,
            )
        )
    jobs_store.record(
        conn,
        ref,
        STAGE,
        outcome.input_hash,
        "done",
        output={
            "unit_key": outcome.unit_key,
            "lesson_key": outcome.lesson_key,
            "valid": sum(d.status == "valid" for d in outcome.drafts),
            "invalid": sum(d.status == "invalid" for d in outcome.drafts),
            "duplicates": [d.problem_id for d in outcome.drafts if d.duplicate],
            "warnings": outcome.warnings,
        },
    )
