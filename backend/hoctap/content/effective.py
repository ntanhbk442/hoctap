"""The effective Problem: extracted content with the review overlay (AD-4, AD-5).

`effective_problem()` is the only place that merges `content_catalog_problems.doc_json`
with `content_review_overrides` and the curated Concept links. `visible_to_child()` is the
only selector of what the child may see; it returns `child_view()` of the effective doc.

Merge order: `part` overrides (a whole Part replaced) first, then the field overrides
(`instruction`, `display_label` at the top level; `prompt`, `answer`, `hint`, `solution`
per Part), then `concept_ids` replaced by the curated links (sorted).

A conflict is an override whose `base_hash` no longer equals the hash of the current
extracted value, or whose `part_key` no longer exists. The first still wins; the second is
skipped. Both are listed.

The effective `content_hash` is the sha256 of the canonical JSON of the effective doc
without `concept_ids`, so curating Concepts never withdraws an approval.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, select

from hoctap.content.catalog.models import content_catalog_concept_guides, content_catalog_problems
from hoctap.content.catalog.service import canonical_doc_json
from hoctap.content.review.models import (
    content_review_error_reports,
    content_review_guide_overrides,
    content_review_guide_status,
    content_review_overrides,
    content_review_problem_concepts,
    content_review_status,
)
from hoctap.content.schema import ConceptGuideDoc, ProblemDoc
from hoctap.content.views import ChildProblemView, child_view

TOP_FIELDS: frozenset[str] = frozenset({"instruction", "display_label"})
PART_FIELDS: frozenset[str] = frozenset({"prompt", "answer", "hint", "solution", "part"})

CONFLICT_BASE_CHANGED = "base_changed"
CONFLICT_PART_MISSING = "part_missing"


class InvalidEffectiveDoc(ValueError):
    """The merged doc fails ProblemDoc validation."""

    def __init__(self, problem_id: str, error: ValidationError) -> None:
        self.problem_id = problem_id
        self.error = error
        super().__init__(
            f"{problem_id}: the effective doc is invalid: {error.error_count()} error(s): "
            f"{error.errors(include_url=False)[0]['msg']}"
        )


class ProblemNotFound(LookupError):
    pass


def value_hash(value: Any) -> str:
    """sha256 of the canonical JSON (NFC, sorted keys) of any JSON value."""
    return hashlib.sha256(canonical_doc_json(value).encode("utf-8")).hexdigest()


def effective_hash(doc: Mapping[str, Any]) -> str:
    """The effective `content_hash`: the doc without `concept_ids`."""
    return value_hash({k: v for k, v in doc.items() if k != "concept_ids"})


@dataclass(frozen=True)
class Override:
    id: str
    problem_id: str
    part_key: str  # '' for the top level
    field: str
    value: Any
    base_hash: str


@dataclass(frozen=True)
class Conflict:
    override_id: str
    part_key: str
    field: str
    reason: str  # base_changed | part_missing


def extracted_value(doc: Mapping[str, Any], part_key: str, field_name: str) -> tuple[bool, Any]:
    """(found, value) of a field of the extracted doc; found is False for a missing Part."""
    if not part_key:
        return True, doc.get(field_name)
    for part in doc.get("parts", []):
        if part.get("part_key") == part_key:
            return True, part if field_name == "part" else part.get(field_name)
    return False, None


def merge(
    extracted: Mapping[str, Any],
    overrides: Iterable[Override],
    concept_ids: Sequence[str] | None,
) -> tuple[dict[str, Any], list[Conflict]]:
    """The merged doc (as JSON data, not validated) and the conflicts."""
    doc = copy.deepcopy(dict(extracted))
    conflicts: list[Conflict] = []
    ordered = sorted(overrides, key=lambda o: (o.field != "part", o.part_key, o.field))
    for o in ordered:
        found, base = extracted_value(extracted, o.part_key, o.field)
        if not found:
            conflicts.append(Conflict(o.id, o.part_key, o.field, CONFLICT_PART_MISSING))
            continue
        if value_hash(base) != o.base_hash:
            conflicts.append(Conflict(o.id, o.part_key, o.field, CONFLICT_BASE_CHANGED))
        value = copy.deepcopy(o.value)
        if not o.part_key:
            doc[o.field] = value
            continue
        parts = doc["parts"]
        index = next(i for i, p in enumerate(parts) if p.get("part_key") == o.part_key)
        if o.field == "part":
            parts[index] = value
        else:
            parts[index] = {**parts[index], o.field: value}
    if concept_ids is not None:
        doc["concept_ids"] = sorted(concept_ids)
    return doc, conflicts


def validate_doc(problem_id: str, data: Mapping[str, Any]) -> ProblemDoc:
    try:
        return ProblemDoc.model_validate(data)
    except ValidationError as exc:
        raise InvalidEffectiveDoc(problem_id, exc) from exc


@dataclass
class EffectiveProblem:
    problem_id: str
    book_id: str
    unit_key: str
    lesson_key: str
    position: int
    needs_review: bool
    verify_status: str
    duplicate: bool
    retired: bool
    extracted: dict[str, Any]
    overrides: list[Override]
    conflicts: list[Conflict]
    doc: ProblemDoc | None  # None when the merged doc is invalid (see `error`)
    content_hash: str | None
    error: InvalidEffectiveDoc | None = None
    approved_hash: str | None = None
    hidden: bool = False
    open_reports: dict[str, int] = field(default_factory=dict)  # kind -> open count

    @property
    def approved(self) -> bool:
        return self.content_hash is not None and self.approved_hash == self.content_hash

    @property
    def awaiting_approval(self) -> bool:
        """`needs_review` and not approved for the current effective hash."""
        return self.needs_review and not self.approved

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts) or self.error is not None

    @property
    def has_open_report(self) -> bool:
        return sum(self.open_reports.values()) > 0

    @property
    def in_queue(self) -> bool:
        """A duplicate stops queueing once approved for the current hash, or hidden."""
        duplicate = self.duplicate and not (self.approved or self.hidden)
        return not self.retired and (
            self.awaiting_approval or self.has_conflict or self.has_open_report or duplicate
        )

    @property
    def visible(self) -> bool:
        return (
            not self.retired
            and self.doc is not None
            and not self.hidden
            and not self.open_reports.get("parent")
            and not self.has_conflict
            and not self.awaiting_approval
        )


def _parse_override(row: Any) -> Override:
    return Override(
        row.id, row.problem_id, row.part_key, row.field, json.loads(row.value_json), row.base_hash
    )


def load_overrides(conn: Connection, problem_ids: Sequence[str]) -> dict[str, list[Override]]:
    t = content_review_overrides
    out: dict[str, list[Override]] = {}
    for row in conn.execute(select(t).where(t.c.problem_id.in_(problem_ids))):
        out.setdefault(row.problem_id, []).append(_parse_override(row))
    return out


def load_concept_links(conn: Connection, problem_ids: Sequence[str]) -> dict[str, list[str]]:
    t = content_review_problem_concepts
    out: dict[str, list[str]] = {}
    rows = conn.execute(
        select(t.c.problem_id, t.c.concept_id).where(t.c.problem_id.in_(problem_ids))
    )
    for problem_id, concept_id in rows:
        out.setdefault(problem_id, []).append(concept_id)
    return out


def _chunks(ids: Sequence[str], size: int = 500) -> Iterable[Sequence[str]]:
    for i in range(0, len(ids), size):
        yield ids[i : i + size]


def _build(conn: Connection, rows: Sequence[Any]) -> list[EffectiveProblem]:
    ids = [r.problem_id for r in rows]
    overrides: dict[str, list[Override]] = {}
    links: dict[str, list[str]] = {}
    status: dict[str, Any] = {}
    reports: dict[str, dict[str, int]] = {}
    s, er = content_review_status, content_review_error_reports
    for chunk in _chunks(ids):
        overrides |= load_overrides(conn, chunk)
        links |= load_concept_links(conn, chunk)
        for row in conn.execute(select(s).where(s.c.problem_id.in_(chunk))):
            status[row.problem_id] = row
        for row in conn.execute(
            select(er.c.problem_id, er.c.kind).where(
                er.c.problem_id.in_(chunk), er.c.status == "open"
            )
        ):
            kinds = reports.setdefault(row.problem_id, {})
            kinds[row.kind] = kinds.get(row.kind, 0) + 1
    out: list[EffectiveProblem] = []
    for row in rows:
        extracted = json.loads(row.doc_json)
        own = overrides.get(row.problem_id, [])
        merged, conflicts = merge(extracted, own, links.get(row.problem_id, []))
        doc: ProblemDoc | None = None
        error: InvalidEffectiveDoc | None = None
        try:
            doc = validate_doc(row.problem_id, merged)
        except InvalidEffectiveDoc as exc:
            error = exc
        st = status.get(row.problem_id)
        out.append(
            EffectiveProblem(
                problem_id=row.problem_id,
                book_id=row.book_id,
                unit_key=row.unit_key,
                lesson_key=row.lesson_key,
                position=row.position,
                needs_review=bool(row.needs_review),
                verify_status=row.verify_status,
                duplicate=bool(row.duplicate),
                retired=row.retired_at is not None,
                extracted=extracted,
                overrides=own,
                conflicts=conflicts,
                doc=doc,
                content_hash=None if doc is None else effective_hash(doc.model_dump(mode="json")),
                error=error,
                approved_hash=None if st is None else st.approved_hash,
                hidden=bool(st is not None and st.hidden),
                open_reports=reports.get(row.problem_id, {}),
            )
        )
    return out


def _problem_rows(
    conn: Connection,
    problem_ids: Iterable[str] | None = None,
    *,
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
    include_retired: bool = True,
) -> list[Any]:
    t = content_catalog_problems
    query = select(t).order_by(t.c.book_id, t.c.position, t.c.problem_id)
    if book_id is not None:
        query = query.where(t.c.book_id == book_id)
    if unit_key is not None:
        query = query.where(t.c.unit_key == unit_key)
    if lesson_key is not None:
        query = query.where(t.c.lesson_key == lesson_key)
    if not include_retired:
        query = query.where(t.c.retired_at.is_(None))
    if problem_ids is None:
        return list(conn.execute(query).all())
    ids = list(dict.fromkeys(problem_ids))
    rows: list[Any] = []
    for chunk in _chunks(ids):
        rows += conn.execute(query.where(t.c.problem_id.in_(chunk))).all()
    return sorted(rows, key=lambda r: (r.book_id, r.position, r.problem_id))


def load_effective(
    conn: Connection,
    problem_ids: Iterable[str] | None = None,
    *,
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
    include_retired: bool = True,
) -> list[EffectiveProblem]:
    """The effective state of many Problems (invalid merges are reported, not raised),
    sorted by book, then position."""
    rows = _problem_rows(
        conn,
        problem_ids,
        book_id=book_id,
        unit_key=unit_key,
        lesson_key=lesson_key,
        include_retired=include_retired,
    )
    return _build(conn, rows)


def build_effective(conn: Connection, rows: Sequence[Any]) -> list[EffectiveProblem]:
    """The effective state of the given `content_catalog_problems` rows, in their order."""
    return _build(conn, rows)


def load_one(conn: Connection, problem_id: str) -> EffectiveProblem:
    """The effective state of one Problem; raises ProblemNotFound."""
    found = load_effective(conn, [problem_id])
    if not found:
        raise ProblemNotFound(problem_id)
    return found[0]


@dataclass(frozen=True)
class Effective:
    doc: ProblemDoc
    content_hash: str
    conflicts: list[Conflict]


def effective_problem(conn: Connection, problem_id: str) -> Effective:
    """The effective ProblemDoc of a Problem, its effective `content_hash` and conflicts.

    Raises ProblemNotFound, or InvalidEffectiveDoc when the merge fails validation.
    """
    state = load_one(conn, problem_id)
    if state.error is not None:
        raise state.error
    assert state.doc is not None and state.content_hash is not None
    return Effective(state.doc, state.content_hash, state.conflicts)


def visible_to_child(
    conn: Connection,
    problem_ids: Iterable[str] | None = None,
    *,
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
) -> list[ChildProblemView]:
    """The single child-facing selector: `child_view()` of the effective doc of every
    visible Problem, by the given ids or query, sorted by book, then position.

    Visible: not retired, not hidden, no open parent Error Report, no conflict, and not
    `needs_review` unless approved for the current effective hash.
    """
    states = load_effective(
        conn,
        problem_ids,
        book_id=book_id,
        unit_key=unit_key,
        lesson_key=lesson_key,
        include_retired=False,
    )
    return [child_view(s.doc) for s in states if s.visible and s.doc is not None]


# --------------------------------------------------------------------------- concept guides

GUIDE_FIELDS: frozenset[str] = frozenset({"explanation", "example"})


@dataclass(frozen=True)
class GuideOverride:
    id: str
    concept_id: str
    field: str
    value: Any
    base_hash: str


@dataclass
class EffectiveGuide:
    """A Concept's Guide: the generated body with Anh's field overrides (AD-4).

    `approved` is true only when `approved_hash` equals the hash of the current effective
    body: generating, regenerating to different text and every edit make it false. Story
    5.2 must show a child only Guides with `approved`."""

    concept_id: str
    source: str
    model: str
    generated_at: str
    generated: dict[str, Any]
    overrides: list[GuideOverride]
    conflicts: list[GuideOverride]  # overrides whose generated field changed since saving
    body: dict[str, Any]  # the merged body (JSON data)
    doc: ConceptGuideDoc | None  # None when the merged body is invalid
    content_hash: str
    approved_hash: str | None = None

    @property
    def approved(self) -> bool:
        return self.doc is not None and self.approved_hash == self.content_hash

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)


def merge_guide(
    generated: Mapping[str, Any], overrides: Iterable[GuideOverride]
) -> tuple[dict[str, Any], list[GuideOverride]]:
    """The merged Guide body and the overrides whose base changed (they still win)."""
    body = copy.deepcopy(dict(generated))
    conflicts: list[GuideOverride] = []
    for o in sorted(overrides, key=lambda o: o.field):
        if value_hash(generated.get(o.field)) != o.base_hash:
            conflicts.append(o)
        body[o.field] = copy.deepcopy(o.value)
    return body, conflicts


def load_guides(
    conn: Connection, concept_ids: Sequence[str] | None = None
) -> dict[str, EffectiveGuide]:
    """The effective Guide of every Concept that has one (or of the given Concepts)."""
    g, o, s = (
        content_catalog_concept_guides,
        content_review_guide_overrides,
        content_review_guide_status,
    )
    query = select(g)
    if concept_ids is not None:
        query = query.where(g.c.concept_id.in_(list(concept_ids)))
    rows = conn.execute(query.order_by(g.c.concept_id)).all()
    ids = [r.concept_id for r in rows]
    overrides: dict[str, list[GuideOverride]] = {}
    approved: dict[str, str | None] = {}
    for chunk in _chunks(ids):
        for row in conn.execute(select(o).where(o.c.concept_id.in_(chunk))):
            overrides.setdefault(row.concept_id, []).append(
                GuideOverride(
                    row.id, row.concept_id, row.field, json.loads(row.value_json), row.base_hash
                )
            )
        for row in conn.execute(select(s).where(s.c.concept_id.in_(chunk))):
            approved[row.concept_id] = row.approved_hash
    out: dict[str, EffectiveGuide] = {}
    for row in rows:
        generated = json.loads(row.body_json)
        own = overrides.get(row.concept_id, [])
        body, conflicts = merge_guide(generated, own)
        try:
            doc: ConceptGuideDoc | None = ConceptGuideDoc.model_validate(body)
        except ValidationError:
            doc = None
        out[row.concept_id] = EffectiveGuide(
            concept_id=row.concept_id,
            source=row.source,
            model=row.model,
            generated_at=row.generated_at,
            generated=generated,
            overrides=own,
            conflicts=conflicts,
            body=body,
            doc=doc,
            content_hash=value_hash(body),
            approved_hash=approved.get(row.concept_id),
        )
    return out


def effective_concept_guide(conn: Connection, concept_id: str) -> EffectiveGuide | None:
    """The effective Guide of a Concept (generated text plus overrides, `approved` flag),
    or None when the Concept has no generated Guide. The only place that merges them."""
    return load_guides(conn, [concept_id]).get(concept_id)
