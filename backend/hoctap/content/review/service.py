"""Review services, the only writers of `content_review_*` (AD-2).

The caller owns the transaction: pass a connection from `engine.begin()`.

- Concept proposals (Story 1.7) and the curated Concepts built from them (accept, merge,
  rename). A re-publish that changes a Problem's proposals rebuilds its Concept links from
  the accepted or merged proposals.
- Field-level overrides (save, delete), each merge validated before anything is stored.
- Review status (approve, hide, unhide), Error Reports (storage and resolve), the queue.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, delete, func, insert, or_, select, update

from hoctap.api.errors import AppError
from hoctap.content.assets import problem_crop_urls, problem_page_urls
from hoctap.content.catalog.models import (
    content_catalog_books,
    content_catalog_lessons,
    content_catalog_problems,
    content_catalog_units,
)
from hoctap.content.effective import (
    CONFLICT_BASE_CHANGED,
    GUIDE_FIELDS,
    PART_FIELDS,
    TOP_FIELDS,
    EffectiveGuide,
    EffectiveProblem,
    GuideOverride,
    InvalidEffectiveDoc,
    Override,
    ProblemNotFound,
    build_effective,
    effective_concept_guide,
    extracted_value,
    load_concept_links,
    load_guides,
    load_one,
    merge,
    merge_guide,
    validate_doc,
    value_hash,
)
from hoctap.content.review.models import (
    content_review_concept_proposals,
    content_review_concepts,
    content_review_error_reports,
    content_review_guide_overrides,
    content_review_guide_status,
    content_review_overrides,
    content_review_problem_concepts,
    content_review_problem_proposals,
    content_review_status,
)
from hoctap.content.review.schemas import (
    ConceptOut,
    ConceptsOut,
    ConflictOut,
    GuideDetail,
    GuideOverrideOut,
    OverrideOut,
    ProblemDetail,
    ProblemPage,
    ProblemSummary,
    ProposalOut,
    ReportOut,
    ReviewBook,
    ReviewLesson,
    ReviewStatusOut,
    ReviewUnit,
)
from hoctap.content.schema import CONCEPT_ID_PATTERN, PROBLEM_TYPES, ConceptGuideDoc
from hoctap.ids import new_id, to_iso, utc_now

PROPOSED = "proposed"
ACCEPTED = "accepted"
MERGED = "merged"


MSG_PROBLEM_NOT_FOUND = "Không tìm thấy bài."


def clean_text(text: str) -> str:
    """NFC, trimmed, inner whitespace collapsed to one space."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def proposal_key(text: str) -> str:
    """The key that identifies a proposed Concept name: `clean_text()` case-folded (NFC)."""
    return unicodedata.normalize("NFC", clean_text(text).casefold())


@dataclass
class ProposalResult:
    new_keys: list[str] = field(default_factory=list)  # proposals seen for the first time
    links: int = 0  # (problem, proposal) links after this call, for the given Problems
    counts: dict[str, int] = field(default_factory=dict)  # affected key -> problem_count


def record_concept_proposals(
    conn: Connection,
    grade: int,
    proposals: Mapping[str, Iterable[str]],
    now: datetime | None = None,
) -> ProposalResult:
    """Records the Concept proposals of Problems of one Grade.

    `proposals` maps a `problem_id` to its ProblemDoc's `concept_proposals`. The links of
    each given Problem are replaced; the `problem_count` of every affected key is recounted
    from the links. Blank names are skipped. Existing proposals keep their `text`,
    `first_seen` and `status`, so a re-run with the same input changes nothing.
    """
    stamp = to_iso(now or utc_now())
    p, links = content_review_concept_proposals, content_review_problem_proposals
    result = ProposalResult()
    affected: set[str] = set()
    for problem_id, texts in proposals.items():
        wanted: dict[str, str] = {}
        for text in texts:
            key = proposal_key(text)
            if key:
                wanted.setdefault(key, clean_text(text))
        old = {
            r[0]
            for r in conn.execute(
                select(links.c.proposal_key).where(
                    links.c.problem_id == problem_id, links.c.grade == grade
                )
            )
        }
        for key in old - set(wanted):
            conn.execute(
                delete(links).where(
                    links.c.problem_id == problem_id,
                    links.c.grade == grade,
                    links.c.proposal_key == key,
                )
            )
        for key, text in wanted.items():
            exists = conn.execute(
                select(p.c.proposal_key).where(p.c.proposal_key == key, p.c.grade == grade)
            ).first()
            if exists is None:
                conn.execute(
                    insert(p).values(
                        proposal_key=key,
                        grade=grade,
                        text=text,
                        problem_count=0,
                        first_seen=stamp,
                        status=PROPOSED,
                    )
                )
                result.new_keys.append(key)
            if key not in old:
                conn.execute(
                    insert(links).values(problem_id=problem_id, proposal_key=key, grade=grade)
                )
        if old != set(wanted):
            _rebuild_links(conn, problem_id, grade)
        result.links += len(wanted)
        affected |= old | set(wanted)
    for key in sorted(affected):
        count = conn.execute(
            select(func.count())
            .select_from(links)
            .where(links.c.proposal_key == key, links.c.grade == grade)
        ).scalar_one()
        current = conn.execute(
            select(p.c.problem_count).where(p.c.proposal_key == key, p.c.grade == grade)
        ).scalar_one()
        if current != count:
            conn.execute(
                update(p)
                .where(p.c.proposal_key == key, p.c.grade == grade)
                .values(problem_count=count)
            )
        result.counts[key] = count
    return result


def _rebuild_links(conn: Connection, problem_id: str, grade: int) -> None:
    """Replaces a Problem's Concept links with the targets of its accepted or merged
    proposals."""
    p, links, pc = (
        content_review_concept_proposals,
        content_review_problem_proposals,
        content_review_problem_concepts,
    )
    targets = {
        r[0]
        for r in conn.execute(
            select(p.c.target_concept_id)
            .join(links, (links.c.proposal_key == p.c.proposal_key) & (links.c.grade == p.c.grade))
            .where(
                links.c.problem_id == problem_id,
                links.c.grade == grade,
                p.c.status.in_((ACCEPTED, MERGED)),
                p.c.target_concept_id.is_not(None),
            )
        )
    }
    conn.execute(delete(pc).where(pc.c.problem_id == problem_id))
    for concept_id in sorted(targets):
        conn.execute(insert(pc).values(problem_id=problem_id, concept_id=concept_id))


# --------------------------------------------------------------------------- validation

_FIELD_LABELS = {
    "instruction": "đề bài",
    "display_label": "nhãn bài",
    "prompt": "câu hỏi",
    "answer": "đáp án",
    "hint": "gợi ý",
    "solution": "lời giải",
    "steps": "các bước",
    "final": "kết quả",
    "template": "mẫu",
    "slots": "ô trống",
    "type": "dạng bài",
}

_PART_PREFIX = re.compile(r"^part '[^']*': ")
_COVER = re.compile(r"^answer must cover exactly its (.+?) \((.+)\)$")
_COVER_WHAT = {
    "slots": "ô",
    "rows": "hàng",
    "items": "mục",
    "empty cells": "ô trống",
    "empty nodes": "nút trống",
    "boxes": "hộp",
    "left items": "mục bên trái",
}


def _value_error(message: str) -> str:
    """Our own validator messages; quoted keys and values are kept verbatim."""
    message = _PART_PREFIX.sub("", message)
    if message == "must not be blank":
        return "không được để trống"
    cover = _COVER.fullmatch(message)
    if cover:
        details = []
        for segment in cover.group(2).split("; "):
            kind, _, keys = segment.partition(" ")
            label = {"missing": "thiếu", "unknown": "thừa"}.get(kind)
            details.append(f"{label} {keys}" if label else segment)
        what = _COVER_WHAT.get(cover.group(1), cover.group(1))
        return f"đáp án phải có đúng các {what} ({'; '.join(details)})"
    return f"không hợp lệ: {message}"


def _message(err: Mapping[str, Any]) -> str:
    """A fixed Vietnamese template per pydantic error `type`."""
    kind = err["type"]
    ctx = err.get("ctx") or {}
    if kind == "value_error":
        return _value_error(str(ctx.get("error", err["msg"])))
    templates = {
        "missing": "thiếu trường bắt buộc",
        "extra_forbidden": "trường không được phép",
        "string_type": "phải là chuỗi",
        "int_type": "phải là số nguyên",
        "bool_type": "phải là true hoặc false",
        "list_type": "phải là danh sách",
        "dict_type": "phải là đối tượng",
        "model_type": "phải là đối tượng",
        "model_attributes_type": "phải là đối tượng",
        "union_tag_not_found": "thiếu dạng bài (type)",
        "none_required": "phải để trống (null)",
    }
    if kind in templates:
        return templates[kind]
    if kind == "string_pattern_mismatch":
        return f"sai định dạng (mẫu {ctx.get('pattern')})"
    if kind == "too_short":
        return f"cần ít nhất {ctx.get('min_length')} phần tử"
    if kind == "too_long":
        return f"nhiều nhất {ctx.get('max_length')} phần tử"
    if kind == "union_tag_invalid":
        return f"dạng bài {ctx.get('tag')!r} không hợp lệ"
    if kind == "literal_error":
        return f"phải là một trong {ctx.get('expected')}"
    if kind in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
        bound = next(iter(ctx.values()), "")
        sign = {"greater_than_equal": "≥", "less_than_equal": "≤"}.get(kind, kind)
        return f"phải {sign} {bound}"
    return f"không hợp lệ ({err['msg']})"


def validation_messages(data: Mapping[str, Any], error: ValidationError) -> list[str]:
    """Vietnamese-friendly messages: where (Phần a › đáp án) and what."""
    parts = data.get("parts") if isinstance(data.get("parts"), list) else []
    out: list[str] = []
    for err in error.errors(include_url=False):
        loc = list(err["loc"])
        where: list[str] = []
        if len(loc) >= 2 and loc[0] == "parts" and isinstance(loc[1], int):
            index = loc[1]
            key = parts[index].get("part_key") if index < len(parts) else None  # type: ignore[union-attr]
            where.append(f"Phần {key}" if key else f"Phần {index + 1}")
            loc = loc[2:]
            if loc and loc[0] in PROBLEM_TYPES:
                loc = loc[1:]  # the discriminator tag
        for item in loc:
            if isinstance(item, str):
                where.append(_FIELD_LABELS.get(item, item))
            else:
                where.append(f"#{item + 1}")
        text = _message(err)
        out.append(f"{' › '.join(where)}: {text}" if where else text)
    return list(dict.fromkeys(out))


def _invalid(data: Mapping[str, Any], exc: InvalidEffectiveDoc) -> AppError:
    details = validation_messages(data, exc.error)
    return AppError(
        422, "INVALID_OVERRIDE", "Bản sửa không hợp lệ: " + "; ".join(details[:3]), details
    )


# --------------------------------------------------------------------------- overrides


@dataclass(frozen=True)
class Edit:
    """One field-level edit. `part_key` None (or '') is the top level."""

    field: str
    value: Any
    part_key: str | None = None


def _nfc_value(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc_value(v) for v in value]
    if isinstance(value, dict):
        return {unicodedata.normalize("NFC", k): _nfc_value(v) for k, v in value.items()}
    return value


def _state(conn: Connection, problem_id: str) -> EffectiveProblem:
    try:
        return load_one(conn, problem_id)
    except ProblemNotFound:
        raise AppError(404, "PROBLEM_NOT_FOUND", MSG_PROBLEM_NOT_FOUND) from None


def _check_edit(extracted: Mapping[str, Any], edit: Edit) -> tuple[str, Any]:
    part_key = edit.part_key or ""
    allowed = PART_FIELDS if part_key else TOP_FIELDS
    if edit.field not in allowed:
        where = f"phần {part_key}" if part_key else "cấp bài"
        raise AppError(422, "INVALID_FIELD", f"Không sửa được trường {edit.field!r} ở {where}.")
    found, base = extracted_value(extracted, part_key, edit.field)
    if not found:
        raise AppError(422, "PART_NOT_FOUND", f"Bài không có phần {part_key!r}.")
    if edit.field == "part":
        if not isinstance(edit.value, dict) or edit.value.get("part_key") != part_key:
            raise AppError(
                422,
                "INVALID_OVERRIDE",
                f"Phần thay thế phải là một đối tượng JSON có part_key = {part_key!r}.",
            )
    return part_key, base


def _merged_or_raise(
    conn: Connection, state: EffectiveProblem, overrides: Iterable[Override]
) -> None:
    links = load_concept_links(conn, [state.problem_id]).get(state.problem_id, [])
    merged, _ = merge(state.extracted, overrides, links)
    try:
        validate_doc(state.problem_id, merged)
    except InvalidEffectiveDoc as exc:
        raise _invalid(merged, exc) from None


def save_overrides(
    conn: Connection, problem_id: str, edits: Sequence[Edit], now: datetime | None = None
) -> None:
    """Stores field-level overrides after validating the full merged doc.

    An edit whose value equals the extracted value deletes its override. Saving again
    re-bases an override on the current extracted value. Raises AppError (422 with the
    validation messages) and stores nothing when the merge is invalid.
    """
    stamp = to_iso(now or utc_now())
    state = _state(conn, problem_id)
    current = {(o.part_key, o.field): o for o in state.overrides}
    wanted = dict(current)
    removed: set[tuple[str, str]] = set()
    changed: set[tuple[str, str]] = set()
    for edit in edits:
        part_key, base = _check_edit(state.extracted, edit)
        value = _nfc_value(edit.value)
        key = (part_key, edit.field)
        if value_hash(value) == value_hash(base):
            wanted.pop(key, None)
            removed.add(key)
            changed.discard(key)
            continue
        old = current.get(key)
        wanted[key] = Override(
            old.id if old else new_id(), problem_id, part_key, edit.field, value, value_hash(base)
        )
        changed.add(key)
        removed.discard(key)
    _merged_or_raise(conn, state, wanted.values())
    t = content_review_overrides
    for key in removed:
        if key in current:
            conn.execute(delete(t).where(t.c.id == current[key].id))
    for key in changed:
        o = wanted[key]
        values = {
            "value_json": json.dumps(o.value, ensure_ascii=False, sort_keys=True),
            "base_hash": o.base_hash,
            "updated_at": stamp,
        }
        if key in current:
            conn.execute(update(t).where(t.c.id == o.id).values(**values))
        else:
            conn.execute(
                insert(t).values(
                    id=o.id,
                    problem_id=problem_id,
                    part_key=o.part_key,
                    field=o.field,
                    created_at=stamp,
                    **values,
                )
            )
    if removed or changed:
        _auto_resolve_reports_on_content_change(conn, problem_id, state.content_hash, now)


def _auto_resolve_reports_on_content_change(
    conn: Connection, problem_id: str, old_hash: str | None, now: datetime | None
) -> None:
    """Orchestrator's Independent Audit (spec-4-4 #1, 2026-10-01): a parent who opens the
    editor from an Error Report, fixes the content and saves, but forgets to separately
    click "Đã xử lý" ("resolve_report"), would otherwise leave the Problem hidden
    (`effective.py` keeps hiding on any open `parent` report) and stuck in "Cần duyệt"
    forever even though it is now correct.

    Chosen fix (option (a) of the audit's two suggestions): auto-resolve every OPEN report
    on this Problem whenever `save_overrides()` actually changes the effective
    `content_hash` -- the same hash `approve()`'s own STALE check already treats as "the
    content Anh is looking at". Rejected alternative (b), a reminder banner in the editor:
    it still requires the parent to remember a SECOND action, which is exactly the trap
    this finding is about; auto-resolving on an actual content change removes the trap
    entirely with no further parent action needed, and a report whose Problem content was
    NOT actually touched (e.g. an edit that reverts to the extracted value, hitting the
    `value_hash(value) == value_hash(base)` early-continue above, so `removed`/`changed`
    stay empty) correctly leaves the report open rather than resolving on a no-op save.
    """
    new_hash = _state(conn, problem_id).content_hash
    if new_hash is None or new_hash == old_hash:
        return
    t = content_review_error_reports
    open_ids = [
        r.id
        for r in conn.execute(
            select(t.c.id).where(t.c.problem_id == problem_id, t.c.status == "open")
        )
    ]
    for report_id in open_ids:
        resolve_report(conn, report_id, now)


def delete_override(conn: Connection, problem_id: str, override_id: str) -> None:
    """Reverts one override ("Bỏ sửa"). Refused only when it would turn a valid effective
    doc invalid; an already invalid doc can always be reverted step by step."""
    state = _state(conn, problem_id)
    remaining = [o for o in state.overrides if o.id != override_id]
    if len(remaining) == len(state.overrides):
        raise AppError(404, "OVERRIDE_NOT_FOUND", "Không tìm thấy bản sửa.")
    if state.error is None:
        _merged_or_raise(conn, state, remaining)
    t = content_review_overrides
    conn.execute(delete(t).where(t.c.id == override_id, t.c.problem_id == problem_id))


def delete_all_overrides(conn: Connection, problem_id: str) -> None:
    """ "Bỏ tất cả sửa đổi": back to the extracted doc, which is always valid."""
    _state(conn, problem_id)
    t = content_review_overrides
    conn.execute(delete(t).where(t.c.problem_id == problem_id))


# --------------------------------------------------------------------------- status


def _upsert_status(conn: Connection, problem_id: str, stamp: str, **values: Any) -> None:
    t = content_review_status
    exists = conn.execute(select(t.c.problem_id).where(t.c.problem_id == problem_id)).first()
    if exists is None:
        values.setdefault("hidden", 0)
        conn.execute(insert(t).values(problem_id=problem_id, updated_at=stamp, **values))
    else:
        conn.execute(
            update(t).where(t.c.problem_id == problem_id).values(updated_at=stamp, **values)
        )


MSG_RETIRED = "Bài này đã bị loại khỏi sách sau lần trích xuất mới."
MSG_STALE = "Nội dung đã thay đổi từ khi mở. Hãy xem lại rồi duyệt."


def _active_state(conn: Connection, problem_id: str) -> EffectiveProblem:
    state = _state(conn, problem_id)
    if state.retired:
        raise AppError(409, "PROBLEM_RETIRED", MSG_RETIRED)
    return state


def approve(
    conn: Connection,
    problem_id: str,
    expected_hash: str | None = None,
    now: datetime | None = None,
) -> str:
    """Duyệt: `approved_hash` = the current effective hash, which is returned.

    `expected_hash` is the effective hash the parent looked at: a different current hash
    is refused with 409 STALE.

    Approving also accepts the overrides whose extracted base changed (their `base_hash`
    is moved to the current extracted value): Anh has checked the effective content. An
    override whose Part is gone stays a conflict until it is reverted.
    """
    stamp = to_iso(now or utc_now())
    state = _active_state(conn, problem_id)
    if state.content_hash is None:
        raise AppError(
            409, "INVALID_EFFECTIVE", "Nội dung sau khi sửa không hợp lệ; hãy sửa hoặc bỏ sửa."
        )
    if expected_hash is not None and expected_hash != state.content_hash:
        raise AppError(409, "STALE", MSG_STALE)
    t = content_review_overrides
    for c in state.conflicts:
        if c.reason == CONFLICT_BASE_CHANGED:
            _, base = extracted_value(state.extracted, c.part_key, c.field)
            conn.execute(
                update(t)
                .where(t.c.id == c.override_id)
                .values(base_hash=value_hash(base), updated_at=stamp)
            )
    _upsert_status(conn, problem_id, stamp, approved_hash=state.content_hash)
    return state.content_hash


def set_hidden(
    conn: Connection, problem_id: str, hidden: bool, now: datetime | None = None
) -> None:
    """Ẩn (hidden) / Hiện (shown again). A retired Problem cannot be hidden."""
    stamp = to_iso(now or utc_now())
    if hidden:
        _active_state(conn, problem_id)
    else:
        _state(conn, problem_id)
    _upsert_status(conn, problem_id, stamp, hidden=int(hidden))


# --------------------------------------------------------------------------- reports

REPORT_KINDS = ("parent", "child")
REPORT_NOTE_MAX = 500


def add_error_report(
    conn: Connection, problem_id: str, kind: str, note: str = "", now: datetime | None = None
) -> str:
    """Stores an open Error Report (Story 4.4). One open report per kind per Problem: a
    repeat returns the existing report's id. The note is trimmed and capped."""
    if kind not in REPORT_KINDS:
        raise ValueError(f"unknown report kind {kind!r}")
    _state(conn, problem_id)
    t = content_review_error_reports
    existing = conn.execute(
        select(t.c.id)
        .where(t.c.problem_id == problem_id, t.c.kind == kind, t.c.status == "open")
        .order_by(t.c.created_at, t.c.id)
    ).first()
    if existing is not None:
        return str(existing.id)
    note = unicodedata.normalize("NFC", note).strip()
    if len(note) > REPORT_NOTE_MAX:
        raise AppError(422, "NOTE_TOO_LONG", f"Ghi chú tối đa {REPORT_NOTE_MAX} ký tự.")
    report_id = new_id()
    conn.execute(
        insert(content_review_error_reports).values(
            id=report_id,
            problem_id=problem_id,
            kind=kind,
            note=note,
            status="open",
            created_at=to_iso(now or utc_now()),
            resolved_at=None,
        )
    )
    return report_id


def resolve_report(conn: Connection, report_id: str, now: datetime | None = None) -> None:
    t = content_review_error_reports
    row = conn.execute(select(t.c.status).where(t.c.id == report_id)).first()
    if row is None:
        raise AppError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo lỗi.")
    if row.status == "open":
        conn.execute(
            update(t)
            .where(t.c.id == report_id)
            .values(status="resolved", resolved_at=to_iso(now or utc_now()))
        )


def list_reports(conn: Connection, problem_id: str) -> list[Any]:
    t = content_review_error_reports
    return list(
        conn.execute(
            select(t).where(t.c.problem_id == problem_id).order_by(t.c.created_at, t.c.id)
        ).all()
    )


# --------------------------------------------------------------------------- queue


def review_queue(conn: Connection) -> list[EffectiveProblem]:
    """Cần duyệt: active Problems awaiting approval, in conflict, with an open Error
    Report, or flagged duplicate; sorted by book, then position.

    Prefiltered in SQL by the stored flags (needs_review, duplicate, has overrides, open
    reports): only those Problems are merged and validated.
    """
    t, o, r = content_catalog_problems, content_review_overrides, content_review_error_reports
    rows = conn.execute(
        select(t)
        .where(
            t.c.retired_at.is_(None),
            or_(
                t.c.needs_review == 1,
                t.c.duplicate == 1,
                t.c.problem_id.in_(select(o.c.problem_id)),
                t.c.problem_id.in_(select(r.c.problem_id).where(r.c.status == "open")),
            ),
        )
        .order_by(t.c.book_id, t.c.position, t.c.problem_id)
    ).all()
    return [s for s in build_effective(conn, rows) if s.in_queue]


# --------------------------------------------------------------------------- concepts

_SLUG_MAX = 48  # the slug part of CONCEPT_ID_PATTERN


def slugify(text: str) -> str:
    """ASCII slug of a Vietnamese name: "So sánh số" -> "so-sanh-so"."""
    text = unicodedata.normalize("NFC", text).replace("đ", "d").replace("Đ", "D")
    ascii_text = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = slug[:_SLUG_MAX].strip("-")
    return slug or "khai-niem"


def _unique_concept_id(conn: Connection, grade: int, text: str) -> str:
    """`g{grade}.{slug}`, with `-2`, `-3`... on collision; the slug is trimmed so the
    suffix always fits the 48-character limit."""
    c = content_review_concepts
    slug = slugify(text)
    candidate, n = f"g{grade}.{slug}", 1
    while conn.execute(select(c.c.concept_id).where(c.c.concept_id == candidate)).first():
        n += 1
        suffix = f"-{n}"
        candidate = f"g{grade}.{slug[: _SLUG_MAX - len(suffix)].rstrip('-')}{suffix}"
    if not re.fullmatch(CONCEPT_ID_PATTERN, candidate):
        raise AppError(422, "INVALID_CONCEPT_ID", f"Không tạo được mã khái niệm {candidate!r}.")
    return candidate


def _proposal(conn: Connection, grade: int, key: str) -> Any:
    p = content_review_concept_proposals
    row = conn.execute(select(p).where(p.c.grade == grade, p.c.proposal_key == key)).first()
    if row is None:
        raise AppError(404, "PROPOSAL_NOT_FOUND", "Không tìm thấy đề xuất khái niệm.")
    if row.status != PROPOSED:
        raise AppError(409, "PROPOSAL_DONE", "Đề xuất này đã được xử lý.")
    return row


def _link_proposal(conn: Connection, grade: int, key: str, concept_id: str, status: str) -> int:
    p, links, pc = (
        content_review_concept_proposals,
        content_review_problem_proposals,
        content_review_problem_concepts,
    )
    conn.execute(
        update(p)
        .where(p.c.grade == grade, p.c.proposal_key == key)
        .values(status=status, target_concept_id=concept_id)
    )
    problem_ids = [
        r[0]
        for r in conn.execute(
            select(links.c.problem_id).where(links.c.grade == grade, links.c.proposal_key == key)
        )
    ]
    for problem_id in problem_ids:
        exists = conn.execute(
            select(pc.c.problem_id).where(
                pc.c.problem_id == problem_id, pc.c.concept_id == concept_id
            )
        ).first()
        if exists is None:
            conn.execute(insert(pc).values(problem_id=problem_id, concept_id=concept_id))
    return len(problem_ids)


def accept_proposal(
    conn: Connection, grade: int, proposal_key: str, now: datetime | None = None
) -> str:
    """Nhận: creates a Concept from the proposal's text and links its Problems."""
    row = _proposal(conn, grade, proposal_key)
    name = clean_text(row.text)
    if not name:
        raise AppError(422, "INVALID_NAME", "Tên khái niệm không được để trống.")
    concept_id = _unique_concept_id(conn, grade, name)
    conn.execute(
        insert(content_review_concepts).values(
            concept_id=concept_id,
            grade=grade,
            name_vi=name,
            created_at=to_iso(now or utc_now()),
        )
    )
    _link_proposal(conn, grade, proposal_key, concept_id, ACCEPTED)
    return concept_id


def _concept(conn: Connection, concept_id: str) -> Any:
    c = content_review_concepts
    row = conn.execute(select(c).where(c.c.concept_id == concept_id)).first()
    if row is None:
        raise AppError(404, "CONCEPT_NOT_FOUND", "Không tìm thấy khái niệm.")
    return row


def merge_proposal(conn: Connection, grade: int, proposal_key: str, concept_id: str) -> None:
    """Gộp vào…: links the proposal's Problems to an existing Concept of the same Grade."""
    _proposal(conn, grade, proposal_key)
    concept = _concept(conn, concept_id)
    if concept.grade != grade:
        raise AppError(422, "GRADE_MISMATCH", "Khái niệm thuộc lớp khác.")
    _link_proposal(conn, grade, proposal_key, concept_id, MERGED)


def rename_concept(conn: Connection, concept_id: str, name_vi: str) -> None:
    """Đổi tên: changes `name_vi` only; the `concept_id` never changes."""
    _concept(conn, concept_id)
    name = clean_text(name_vi)
    if not name:
        raise AppError(422, "INVALID_NAME", "Tên khái niệm không được để trống.")
    c = content_review_concepts
    conn.execute(update(c).where(c.c.concept_id == concept_id).values(name_vi=name))


@dataclass(frozen=True)
class ConceptRow:
    concept_id: str
    grade: int
    name_vi: str
    problem_count: int


def list_concepts(conn: Connection) -> tuple[list[Any], list[ConceptRow]]:
    """(proposals by Grade and text, curated Concepts with their link counts)."""
    p, c, pc = (
        content_review_concept_proposals,
        content_review_concepts,
        content_review_problem_concepts,
    )
    proposals = list(conn.execute(select(p).order_by(p.c.grade, p.c.text, p.c.proposal_key)))
    counts = dict(
        conn.execute(select(pc.c.concept_id, func.count()).group_by(pc.c.concept_id)).all()
    )
    concepts = [
        ConceptRow(r.concept_id, r.grade, r.name_vi, counts.get(r.concept_id, 0))
        for r in conn.execute(select(c).order_by(c.c.grade, c.c.name_vi, c.c.concept_id))
    ]
    return proposals, concepts


# --------------------------------------------------------------------------- views


def summary(state: EffectiveProblem) -> ProblemSummary:
    source = state.doc.model_dump(mode="json") if state.doc is not None else state.extracted
    return ProblemSummary(
        problem_id=state.problem_id,
        book_id=state.book_id,
        unit_key=state.unit_key,
        lesson_key=state.lesson_key,
        position=state.position,
        display_label=str(source.get("display_label", "")),
        instruction=str(source.get("instruction", "")),
        awaiting_approval=state.awaiting_approval,
        conflict=state.has_conflict,
        report=state.has_open_report,
        hidden=state.hidden,
        duplicate=state.duplicate,
        approved=state.approved,
        visible=state.visible,
        retired=state.retired,
    )


PAGE_SIZE = 50


def list_problems(
    conn: Connection,
    *,
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
    page: int = 1,
) -> ProblemPage:
    """Tất cả: active Problems by book and position, 50 per page. Filtered and paginated
    in SQL; only the Problems of the page are merged."""
    t = content_catalog_problems
    where = [t.c.retired_at.is_(None)]
    if book_id is not None:
        where.append(t.c.book_id == book_id)
    if unit_key is not None:
        where.append(t.c.unit_key == unit_key)
    if lesson_key is not None:
        where.append(t.c.lesson_key == lesson_key)
    total = conn.execute(select(func.count()).select_from(t).where(*where)).scalar_one()
    rows = conn.execute(
        select(t)
        .where(*where)
        .order_by(t.c.book_id, t.c.position, t.c.problem_id)
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    ).all()
    return ProblemPage(
        items=[summary(s) for s in build_effective(conn, rows)],
        total=total,
        page=page,
        page_size=PAGE_SIZE,
    )


def list_review_books(conn: Connection) -> list[ReviewBook]:
    """Books that have active Problems, with their Units and Lessons, for the filters."""
    b, t = content_catalog_books, content_catalog_problems
    u, les = content_catalog_units, content_catalog_lessons
    counts = conn.execute(
        select(t.c.book_id, t.c.unit_key, t.c.lesson_key, func.count())
        .where(t.c.retired_at.is_(None))
        .group_by(t.c.book_id, t.c.unit_key, t.c.lesson_key)
    ).all()
    active: dict[str, dict[str, set[str]]] = {}
    per_book: dict[str, int] = {}
    for book, unit, lesson, n in counts:
        active.setdefault(book, {}).setdefault(unit, set()).add(lesson)
        per_book[book] = per_book.get(book, 0) + n
    units = {
        (r.book_id, r.unit_key): r
        for r in conn.execute(select(u).where(u.c.book_id.in_(list(active))))
    }
    lessons = {
        (r.book_id, r.unit_key, r.lesson_key): r
        for r in conn.execute(select(les).where(les.c.book_id.in_(list(active))))
    }
    out: list[ReviewBook] = []
    rows = conn.execute(
        select(b.c.book_id, b.c.title_vi)
        .where(b.c.book_id.in_(list(active)))
        .order_by(b.c.edition, b.c.grade, b.c.volume)
    )
    for book_id, title in rows:

        def unit_pos(key: str, book_id: str = book_id) -> tuple[int, str]:
            row = units.get((book_id, key))
            return (row.position if row else 0, key)

        book_units = []
        for unit_key in sorted(active[book_id], key=unit_pos):
            unit_row = units.get((book_id, unit_key))

            def lesson_pos(key: str, book_id: str = book_id, unit_key: str = unit_key):
                row = lessons.get((book_id, unit_key, key))
                return (row.position if row else 0, key)

            book_units.append(
                ReviewUnit(
                    unit_key=unit_key,
                    label=_label(unit_row, unit_key),
                    lessons=[
                        ReviewLesson(
                            lesson_key=k, label=_label(lessons.get((book_id, unit_key, k)), k)
                        )
                        for k in sorted(active[book_id][unit_key], key=lesson_pos)
                    ],
                )
            )
        out.append(
            ReviewBook(
                book_id=book_id, title_vi=title, problem_count=per_book[book_id], units=book_units
            )
        )
    return out


def _label(row: Any, key: str) -> str:
    """ "TUẦN 5 – title" as printed, or the key when the heading is unknown."""
    if row is None:
        return key
    text = " – ".join(x for x in (row.label, row.title) if x)
    return text or key


def problem_detail(conn: Connection, problem_id: str) -> ProblemDetail:
    state = _state(conn, problem_id)
    reasons = {c.override_id: c.reason for c in state.conflicts}
    error: list[str] = []
    if state.error is not None:
        links = load_concept_links(conn, [problem_id]).get(problem_id, [])
        merged, _ = merge(state.extracted, state.overrides, links)
        error = validation_messages(merged, state.error.error)
    try:
        assets_doc = state.doc or validate_doc(problem_id, state.extracted)
    except InvalidEffectiveDoc:
        assets_doc = None
    return ProblemDetail(
        summary=summary(state),
        extracted=state.extracted,
        effective=state.doc,
        effective_error=error,
        content_hash=state.content_hash,
        overrides=[
            OverrideOut(
                id=o.id,
                part_key=o.part_key or None,
                field=o.field,  # type: ignore[arg-type]
                value=o.value,
                base_hash=o.base_hash,
                conflict=reasons.get(o.id),  # type: ignore[arg-type]
            )
            for o in sorted(state.overrides, key=lambda o: (o.part_key, o.field))
        ],
        conflicts=[
            ConflictOut(
                override_id=c.override_id,
                part_key=c.part_key or None,
                field=c.field,  # type: ignore[arg-type]
                reason=c.reason,  # type: ignore[arg-type]
            )
            for c in state.conflicts
        ],
        status=ReviewStatusOut(
            needs_review=state.needs_review,
            verify_status=state.verify_status,
            approved_hash=state.approved_hash,
            approved=state.approved,
            hidden=state.hidden,
            duplicate=state.duplicate,
            retired=state.retired,
            visible=state.visible,
        ),
        reports=[
            ReportOut(
                id=r.id,
                problem_id=r.problem_id,
                kind=r.kind,
                note=r.note,
                status=r.status,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in list_reports(conn, problem_id)
        ],
        crop_urls=problem_crop_urls(assets_doc) if assets_doc else [],
        page_urls=problem_page_urls(assets_doc) if assets_doc else [],
    )


def report_out(conn: Connection, report_id: str) -> ReportOut:
    t = content_review_error_reports
    r = conn.execute(select(t).where(t.c.id == report_id)).first()
    if r is None:
        raise AppError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo lỗi.")
    return ReportOut(
        id=r.id,
        problem_id=r.problem_id,
        kind=r.kind,
        note=r.note,
        status=r.status,
        created_at=r.created_at,
        resolved_at=r.resolved_at,
    )


def _guide_rank(concept: ConceptRow, guides: Mapping[str, EffectiveGuide]) -> tuple[int, int]:
    """Concepts whose unapproved Guide was drafted from sample Problems (no book material)
    come first in each Grade; the rest keep the list order (Grade, name)."""
    guide = guides.get(concept.concept_id)
    first = guide is not None and guide.source == "problems" and not guide.approved
    return (concept.grade, 0 if first else 1)


def concepts_out(conn: Connection) -> ConceptsOut:
    proposals, concepts = list_concepts(conn)
    guides = load_guides(conn)
    return ConceptsOut(
        proposals=[
            ProposalOut(
                proposal_key=p.proposal_key,
                grade=p.grade,
                text=p.text,
                problem_count=p.problem_count,
                status=p.status,
                target_concept_id=p.target_concept_id,
            )
            for p in proposals
        ],
        concepts=[
            ConceptOut(
                concept_id=c.concept_id,
                grade=c.grade,
                name_vi=c.name_vi,
                problem_count=c.problem_count,
                has_guide=c.concept_id in guides,
                guide_source=guides[c.concept_id].source if c.concept_id in guides else None,  # type: ignore[arg-type]
                guide_conflict=c.concept_id in guides and guides[c.concept_id].has_conflict,
                guide_approved=c.concept_id in guides and guides[c.concept_id].approved,
            )
            for c in sorted(concepts, key=lambda c: _guide_rank(c, guides))
        ],
    )


# --------------------------------------------------------------------------- concept guides

MSG_GUIDE_NOT_FOUND = "Khái niệm này chưa có hướng dẫn."


def _guide(conn: Connection, concept_id: str) -> EffectiveGuide:
    _concept(conn, concept_id)  # 404 CONCEPT_NOT_FOUND
    guide = effective_concept_guide(conn, concept_id)
    if guide is None:
        raise AppError(404, "GUIDE_NOT_FOUND", MSG_GUIDE_NOT_FOUND)
    return guide


def _validate_guide(body: Mapping[str, Any]) -> None:
    try:
        ConceptGuideDoc.model_validate(body)
    except ValidationError as exc:
        details = validation_messages(body, exc)
        raise AppError(
            422, "INVALID_OVERRIDE", "Bản sửa không hợp lệ: " + "; ".join(details[:3]), details
        ) from None


def save_guide_overrides(
    conn: Connection, concept_id: str, edits: Sequence[Edit], now: datetime | None = None
) -> None:
    """Stores field overrides (`explanation`, `example`) of a Concept's Guide after
    validating the merged Guide. An edit equal to the generated value removes its override;
    saving re-bases an override on the current generated value. Nothing is stored when the
    merge is invalid (422); unknown Concept: 404 CONCEPT_NOT_FOUND."""
    stamp = to_iso(now or utc_now())
    guide = _guide(conn, concept_id)
    current = {o.field: o for o in guide.overrides}
    wanted = dict(current)
    for edit in edits:
        if edit.field not in GUIDE_FIELDS:
            raise AppError(422, "INVALID_FIELD", f"Không sửa được trường {edit.field!r}.")
        value = _nfc_value(edit.value)
        base = guide.generated.get(edit.field)
        if value_hash(value) == value_hash(base):
            wanted.pop(edit.field, None)
            continue
        old = current.get(edit.field)
        wanted[edit.field] = GuideOverride(
            old.id if old else new_id(), concept_id, edit.field, value, value_hash(base)
        )
    body, _ = merge_guide(guide.generated, wanted.values())
    _validate_guide(body)
    t = content_review_guide_overrides
    for name, old in current.items():
        if name not in wanted:
            conn.execute(delete(t).where(t.c.id == old.id))
    for name, o in wanted.items():
        if name in current and current[name] == o:
            continue
        values = {
            "value_json": json.dumps(o.value, ensure_ascii=False, sort_keys=True),
            "base_hash": o.base_hash,
            "updated_at": stamp,
        }
        if name in current:
            conn.execute(update(t).where(t.c.id == o.id).values(**values))
        else:
            conn.execute(
                insert(t).values(
                    id=o.id, concept_id=concept_id, field=name, created_at=stamp, **values
                )
            )


def delete_guide_override(conn: Connection, concept_id: str, field_name: str | None = None) -> None:
    """Reset: removes the override of one field, or of every field, so the effective Guide
    returns to the generated text."""
    _guide(conn, concept_id)
    t = content_review_guide_overrides
    query = delete(t).where(t.c.concept_id == concept_id)
    if field_name is not None:
        query = query.where(t.c.field == field_name)
    conn.execute(query)


def approve_guide(
    conn: Connection,
    concept_id: str,
    expected_hash: str | None = None,
    now: datetime | None = None,
) -> str:
    """Duyệt: `approved_hash` = the hash of the current effective Guide, which is returned.
    A different `expected_hash` is refused (409 STALE). Approving also re-bases the
    overrides whose generated field changed (Anh has checked the effective text)."""
    stamp = to_iso(now or utc_now())
    guide = _guide(conn, concept_id)
    if guide.doc is None:
        raise AppError(
            409, "INVALID_EFFECTIVE", "Nội dung sau khi sửa không hợp lệ; hãy sửa hoặc bỏ sửa."
        )
    if expected_hash is not None and expected_hash != guide.content_hash:
        raise AppError(409, "STALE", MSG_STALE)
    o = content_review_guide_overrides
    for c in guide.conflicts:
        conn.execute(
            update(o)
            .where(o.c.id == c.id)
            .values(base_hash=value_hash(guide.generated.get(c.field)), updated_at=stamp)
        )
    t = content_review_guide_status
    if conn.execute(select(t.c.concept_id).where(t.c.concept_id == concept_id)).first() is None:
        conn.execute(
            insert(t).values(
                concept_id=concept_id, approved_hash=guide.content_hash, updated_at=stamp
            )
        )
    else:
        conn.execute(
            update(t)
            .where(t.c.concept_id == concept_id)
            .values(approved_hash=guide.content_hash, updated_at=stamp)
        )
    return guide.content_hash


def guide_detail(conn: Connection, concept_id: str) -> GuideDetail:
    guide = _guide(conn, concept_id)
    conflicted = {c.field for c in guide.conflicts}
    return GuideDetail(
        concept_id=concept_id,
        source=guide.source,  # type: ignore[arg-type]
        model=guide.model,
        generated_at=guide.generated_at,
        generated=ConceptGuideDoc.model_validate(guide.generated),
        effective=guide.doc,
        content_hash=guide.content_hash,
        approved=guide.approved,
        conflict=guide.has_conflict,
        overrides=[
            GuideOverrideOut(
                field=o.field,  # type: ignore[arg-type]
                value=o.value,
                base_hash=o.base_hash,
                conflict=o.field in conflicted,
            )
            for o in sorted(guide.overrides, key=lambda o: o.field)
        ],
    )
