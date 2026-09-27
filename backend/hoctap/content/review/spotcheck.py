"""Kiểm tra ngẫu nhiên: the spot-check of Answer Keys (Story 1.9), `content_review_spot_*`.

The caller owns the transaction: pass a connection from `engine.begin()`.

- A sample is drawn once from the given candidate Problems (the builder passes the pilot
  Problems and the pilot scope hash, stored on the sample): stratified across Problem
  Types in proportion to their counts, at least one per type present, `size` Problems (or
  every candidate when there are fewer). The seed is stored. Only Problems that are not
  retired, not hidden and have no `fallback` Part are sampled; Problems still awaiting
  review can be. Drawing again creates a new sample and keeps the old one; only the latest
  sample (by its UUIDv7 id) counts.
- The spot-check measures extraction accuracy. Once an item has been judged wrong it
  counts as wrong for good (`first_wrong_at`), even after the Problem is fixed. A correct
  verdict counts only while the Problem's effective hash equals the hash it was given
  for; otherwise it is stale ("cần kiểm tra lại"). A wrong verdict also opens a
  `parent`-kind note on the Problem, which puts it in Cần duyệt. Verdicts never change
  content or approvals.

A Problem's type for the strata is the type of its first Part.
"""

from __future__ import annotations

import random
import secrets
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, insert, select, update

from hoctap.api.errors import AppError
from hoctap.content.effective import EffectiveProblem, load_effective
from hoctap.content.review.models import (
    content_review_spot_check_samples,
    content_review_spot_checks,
)
from hoctap.content.review.schemas import SpotCheckItem, SpotCheckOut
from hoctap.content.review.service import add_error_report
from hoctap.ids import new_id, to_iso, utc_now

CORRECT = "correct"
WRONG = "wrong"
VERDICTS = (CORRECT, WRONG)
NOTE_PREFIX = "Kiểm tra ngẫu nhiên: đáp án sai."


def problem_type(state: EffectiveProblem) -> str:
    """The type of the Problem's first Part (from the effective doc when it is valid)."""
    source = state.doc.model_dump(mode="json") if state.doc is not None else state.extracted
    parts = source.get("parts") or []
    return str(parts[0].get("type", "?")) if parts else "?"


def allocate(counts: Mapping[str, int], size: int) -> dict[str, int]:
    """How many to draw per type: one per type present, then the rest in proportion to
    the counts (largest remainder). Every type present gets at least one, so the result
    exceeds `size` only when there are more types than `size`."""
    present = {t: n for t, n in counts.items() if n > 0}
    total = sum(present.values())
    if total <= size:
        return dict(present)
    alloc = dict.fromkeys(present, 1)
    rest = size - len(present)
    spare = total - len(present)
    if rest <= 0 or spare <= 0:
        return alloc
    quotas = {t: (n - 1) * rest / spare for t, n in present.items()}
    for t, q in quotas.items():
        alloc[t] += int(q)
    left = size - sum(alloc.values())
    by_remainder = sorted(present, key=lambda t: (-(quotas[t] - int(quotas[t])), t))
    for t in by_remainder:
        if left <= 0:
            break
        if alloc[t] < present[t]:
            alloc[t] += 1
            left -= 1
    return alloc


def has_fallback(state: EffectiveProblem) -> bool:
    """Whether the Problem has any `fallback` Part (effective doc when it is valid)."""
    source = state.doc.model_dump(mode="json") if state.doc is not None else state.extracted
    return any(p.get("type") == "fallback" for p in source.get("parts") or [])


def eligible(state: EffectiveProblem) -> bool:
    """Can be sampled: not retired, not hidden, no `fallback` Part."""
    return not state.retired and not state.hidden and not has_fallback(state)


def draw_sample(
    conn: Connection,
    candidate_ids: Iterable[str],
    size: int,
    *,
    scope_hash: str,
    seed: int | None = None,
    now: datetime | None = None,
) -> str:
    """Draws and stores a new sample; returns its `sample_id`. Raises AppError 409
    NOTHING_TO_SAMPLE when no candidate can be sampled."""
    states = [s for s in load_effective(conn, sorted(set(candidate_ids))) if eligible(s)]
    if not states:
        raise AppError(409, "NOTHING_TO_SAMPLE", "Chưa có bài nào để kiểm tra.")
    seed = secrets.randbits(31) if seed is None else seed
    rng = random.Random(seed)
    by_type: dict[str, list[str]] = {}
    for s in sorted(states, key=lambda s: s.problem_id):
        by_type.setdefault(problem_type(s), []).append(s.problem_id)
    alloc = allocate({t: len(ids) for t, ids in by_type.items()}, size)
    chosen: list[str] = []
    for t in sorted(by_type):
        chosen += rng.sample(by_type[t], alloc.get(t, 0))
    rng.shuffle(chosen)
    sample_id = new_id()
    stamp = to_iso(now or utc_now())
    conn.execute(
        insert(content_review_spot_check_samples).values(
            sample_id=sample_id,
            seed=seed,
            size=len(chosen),
            scope_hash=scope_hash,
            created_at=stamp,
        )
    )
    for position, problem_id in enumerate(chosen, start=1):
        conn.execute(
            insert(content_review_spot_checks).values(
                sample_id=sample_id,
                problem_id=problem_id,
                position=position,
                verdict=None,
                verdict_hash=None,
                first_wrong_at=None,
                note="",
                checked_at=None,
            )
        )
    return sample_id


def latest_sample(conn: Connection) -> Any | None:
    t = content_review_spot_check_samples
    return conn.execute(select(t).order_by(t.c.sample_id.desc()).limit(1)).first()


def _items(conn: Connection, sample_id: str) -> list[SpotCheckItem]:
    t = content_review_spot_checks
    rows = conn.execute(select(t).where(t.c.sample_id == sample_id).order_by(t.c.position)).all()
    states = {s.problem_id: s for s in load_effective(conn, [r.problem_id for r in rows])}
    items: list[SpotCheckItem] = []
    for r in rows:
        state = states.get(r.problem_id)
        current = state.content_hash if state is not None else None
        retired = state is None or state.retired
        stale = (
            r.first_wrong_at is None
            and r.verdict == CORRECT
            and (retired or current is None or r.verdict_hash != current)
        )
        if r.first_wrong_at is not None:
            counted: str | None = WRONG
        elif r.verdict == CORRECT and not stale:
            counted = CORRECT
        else:
            counted = None
        source: Mapping[str, Any] = {}
        if state is not None:
            source = state.doc.model_dump(mode="json") if state.doc else state.extracted
        items.append(
            SpotCheckItem(
                problem_id=r.problem_id,
                position=r.position,
                problem_type=problem_type(state) if state is not None else "?",
                display_label=str(source.get("display_label", "")),
                verdict=r.verdict,
                note=r.note,
                checked_at=r.checked_at,
                verdict_hash=r.verdict_hash,
                first_wrong_at=r.first_wrong_at,
                counted=counted,
                content_hash=current,
                stale=stale,
                retired=retired,
            )
        )
    return items


def spot_check_out(conn: Connection) -> SpotCheckOut:
    sample = latest_sample(conn)
    if sample is None:
        return SpotCheckOut(
            sample_id=None,
            seed=None,
            created_at=None,
            size=0,
            correct=0,
            wrong=0,
            stale=0,
            checked=0,
            items=[],
        )
    items = _items(conn, sample.sample_id)
    correct = sum(1 for i in items if i.counted == CORRECT)
    wrong = sum(1 for i in items if i.counted == WRONG)
    return SpotCheckOut(
        sample_id=sample.sample_id,
        seed=sample.seed,
        created_at=sample.created_at,
        size=len(items),
        correct=correct,
        wrong=wrong,
        stale=sum(1 for i in items if i.stale),
        checked=correct + wrong,
        items=items,
    )


def set_verdict(
    conn: Connection,
    sample_id: str,
    problem_id: str,
    verdict: str,
    content_hash: str,
    note: str = "",
    now: datetime | None = None,
) -> None:
    """Đúng / Sai for one sampled Problem. `content_hash` is the effective hash on screen:
    a different current hash is refused with 409 STALE. Only the latest sample accepts
    verdicts. The first wrong verdict sets `first_wrong_at` (never cleared). A wrong
    verdict opens a `parent` note on the Problem (Cần duyệt), unless the previous verdict
    was already wrong for the same content."""
    if verdict not in VERDICTS:
        raise AppError(422, "INVALID_VERDICT", "Kết quả phải là Đúng hoặc Sai.")
    latest = latest_sample(conn)
    if latest is None or latest.sample_id != sample_id:
        raise AppError(409, "SAMPLE_OUTDATED", "Mẫu này không còn là mẫu hiện tại.")
    t = content_review_spot_checks
    row = conn.execute(
        select(t).where(t.c.sample_id == sample_id, t.c.problem_id == problem_id)
    ).first()
    if row is None:
        raise AppError(404, "NOT_IN_SAMPLE", "Bài này không có trong mẫu kiểm tra.")
    states = load_effective(conn, [problem_id])
    state = states[0] if states else None
    if state is None or state.retired:
        raise AppError(409, "PROBLEM_RETIRED", "Bài này đã bị loại khỏi sách.")
    if state.content_hash is None:
        raise AppError(
            409, "INVALID_EFFECTIVE", "Nội dung sau khi sửa không hợp lệ; hãy sửa trước."
        )
    if content_hash != state.content_hash:
        raise AppError(409, "STALE", "Nội dung đã thay đổi từ khi mở. Hãy xem lại.")
    note = unicodedata.normalize("NFC", note).strip()
    already_wrong = row.verdict == WRONG and row.verdict_hash == state.content_hash
    stamp = to_iso(now or utc_now())
    values: dict[str, Any] = {
        "verdict": verdict,
        "verdict_hash": state.content_hash,
        "note": note,
        "checked_at": stamp,
    }
    if verdict == WRONG and row.first_wrong_at is None:
        values["first_wrong_at"] = stamp
    conn.execute(
        update(t).where(t.c.sample_id == sample_id, t.c.problem_id == problem_id).values(**values)
    )
    if verdict == WRONG and not already_wrong:
        text = f"{NOTE_PREFIX} {note}".strip()
        add_error_report(conn, problem_id, "parent", text, now)
