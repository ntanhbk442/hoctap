"""The go/no-go gate before the full run (Story 1.9, FR-5, AD-7).

- Pilot scope: every page reference with a `done` extract job of `run_kind` pilot (the
  full run, Story 6.2, records its jobs as `full`). `pilot_pages` is the count.
- Metrics count published, non-retired Problems whose first page is in scope:
  `fallback_share` (Problems with any `fallback` Part in the effective doc), `key_accuracy`
  (Đúng ÷ (Đúng + Sai) over the latest spot-check sample: an item ever judged Sai counts
  as wrong for good, a Đúng only for the current hash) and `est_cost` = pilot cost per
  page × (catalogue pages − pilot pages). The pilot cost is every recorded call (extract
  and verify, failed pages included) that belongs to a `pilot`-kind job, matched by
  (page_ref, stage, input_hash); a call of unknown cost counts at the per-call cap.
- The sample is drawn with `gate_min_sample + 5` Problems and records the scope it was
  drawn from; a sample from another scope is outdated ("cần rút mẫu mới").
- Approval (`build_gate`) needs both checks to pass, a current sample, the cost accepted
  and the estimate seen to the cent. The latest approval (by UUIDv7 id) is valid while
  it is not revoked, the pilot scope, the latest sample (and its scope) and the thresholds
  are unchanged, both checks still pass and the estimate is unchanged to the cent.
- `require_approval()` is the guard of every full-corpus entry point.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, Engine, func, insert, select, tuple_, update

from hoctap.api.errors import AppError
from hoctap.builder.jobs_store import page_ref
from hoctap.builder.models import build_costs, build_gate, build_jobs
from hoctap.config import Settings
from hoctap.content.catalog.models import content_catalog_books, content_catalog_problems
from hoctap.content.effective import EffectiveProblem, load_effective
from hoctap.content.review import spotcheck
from hoctap.content.review.models import content_review_status
from hoctap.ids import new_id, to_iso, utc_now

PILOT, FULL = "pilot", "full"
DRAW_MARGIN = 5  # the sample has gate_min_sample + 5 Problems
MSG_NOT_ENOUGH_PROBLEMS = "Chưa đủ bài để đánh giá — hãy chạy thử thêm trang."
MSG_SAMPLE_OUTDATED = "Mẫu kiểm tra được rút trước khi có trang chạy thử mới — cần rút mẫu mới."
MSG_NOT_APPROVED = "Chưa được duyệt chạy toàn bộ. Hãy xem báo cáo chạy thử và duyệt trước."


class GateNotApproved(AppError):
    """No valid approval: the full run is refused."""

    def __init__(self, reason: str | None = None) -> None:
        message = MSG_NOT_APPROVED + (f" ({reason})" if reason else "")
        super().__init__(409, "GATE_NOT_APPROVED", message)
        self.reason = reason


# --------------------------------------------------------------------------- report models


class GateThresholds(BaseModel):
    max_fallback_share: float
    min_key_accuracy: float
    min_sample: int


class FallbackCheck(BaseModel):
    passed: bool
    value: float | None = Field(description="null when there are no pilot Problems")
    threshold: float
    problems: int
    with_fallback: int


class AccuracyCheck(BaseModel):
    passed: bool
    value: float | None = Field(description="null before any counted verdict")
    threshold: float
    correct: int
    wrong: int
    stale: int = Field(description="verdicts for an older hash (cần kiểm tra lại)")
    unchecked: int
    sample_id: str | None
    sample_size: int
    min_sample: int
    enough_sample: bool = Field(description="false: chưa đủ mẫu")
    sample_outdated: bool = Field(
        description="the latest sample was drawn from another pilot scope: cần rút mẫu mới"
    )
    eligible_problems: int = Field(description="pilot Problems that can be sampled")
    enough_problems: bool = Field(
        description="false: chưa đủ bài để đánh giá — hãy chạy thử thêm trang"
    )


class GateCost(BaseModel):
    pilot_cost: float = Field(description="USD; unknown-cost calls at the per-call cap")
    reported_cost: float = Field(description="USD reported by the CLI")
    unknown_cost_calls: int
    unknown_cost_cap_usd: float
    per_page: float | None
    pilot_pages: int
    total_pages: int
    remaining_pages: int
    est_cost: float | None = Field(description="USD for the remaining pages, to the cent")


class BookPilotPages(BaseModel):
    book_id: str
    pilot_pages: int


class GateApproval(BaseModel):
    id: str
    approved_at: str
    est_cost: float
    sample_id: str
    valid: bool
    invalid_reasons: list[str] = Field(description="why it no longer holds (Vietnamese)")


class GateReport(BaseModel):
    has_pilot: bool = Field(description="false: chưa chạy thử")
    pilot_pages: int
    pilot_problems: int
    books: list[BookPilotPages]
    thresholds: GateThresholds
    fallback: FallbackCheck
    accuracy: AccuracyCheck
    cost: GateCost
    checks_passed: bool
    approval: GateApproval | None = Field(description="the latest approval, unless revoked")
    approved: bool = Field(description="a valid approval exists: Đã duyệt")


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept_cost: bool = Field(description="must be true (else 422 COST_NOT_ACCEPTED)")
    est_cost_seen: float = Field(
        ge=0, allow_inf_nan=False, description="the estimate shown, USD; compared to the cent"
    )


# --------------------------------------------------------------------------- scope


def pilot_refs(conn: Connection) -> list[str]:
    """The pilot scope: page refs with a `done` pilot extract job, sorted."""
    t = build_jobs
    rows = conn.execute(
        select(t.c.page_ref)
        .where(t.c.stage == "extract", t.c.status == "done", t.c.run_kind == PILOT)
        .distinct()
    ).all()
    return sorted(r[0] for r in rows)


def scope_hash(refs: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(refs)).encode("utf-8")).hexdigest()


def pilot_problem_ids(conn: Connection, refs: list[str] | None = None) -> list[str]:
    """Published, non-retired, non-hidden Problems whose first page is in the pilot scope.

    Hidden is excluded here, not only at spot-check sampling time via `spotcheck.eligible()`:
    a Problem hidden before a sample is ever drawn from it must not keep counting toward
    `fallback_share` (inflating or deflating it relative to true pilot quality) while
    permanently escaping the accuracy check -- the accuracy and fallback checks must agree on
    which Problems "count" (spec-1-9 finding #18). A Problem hidden *after* being sampled is
    unaffected: its verdict (and `first_wrong_at`) is tracked independently of its current
    hidden state."""
    scope = set(pilot_refs(conn) if refs is None else refs)
    t, status = content_catalog_problems, content_review_status
    rows = conn.execute(
        select(t.c.problem_id, t.c.book_id, t.c.source_page_first)
        .select_from(t.outerjoin(status, status.c.problem_id == t.c.problem_id))
        .where(t.c.retired_at.is_(None), func.coalesce(status.c.hidden, 0) == 0)
    ).all()
    return sorted(
        row.problem_id for row in rows if page_ref(row.book_id, row.source_page_first) in scope
    )


def _book_of(ref: str) -> str:
    return ref.rsplit("#p", 1)[0]


# --------------------------------------------------------------------------- metrics


def thresholds(settings: Settings) -> GateThresholds:
    return GateThresholds(
        max_fallback_share=settings.gate_max_fallback_share,
        min_key_accuracy=settings.gate_min_key_accuracy,
        min_sample=settings.gate_min_sample,
    )


def _fallback(states: list[EffectiveProblem], limit: float) -> FallbackCheck:
    with_fallback = sum(1 for s in states if spotcheck.has_fallback(s))
    n = len(states)
    value = with_fallback / n if n else None
    return FallbackCheck(
        passed=value is not None and value <= limit,
        value=value,
        threshold=limit,
        problems=n,
        with_fallback=with_fallback,
    )


def _accuracy(conn: Connection, limits: GateThresholds, scope: str, eligible: int) -> AccuracyCheck:
    out = spotcheck.spot_check_out(conn)
    sample = spotcheck.latest_sample(conn)
    outdated = sample is not None and sample.scope_hash != scope
    counted = out.correct + out.wrong
    value = out.correct / counted if counted else None
    enough = counted >= limits.min_sample
    return AccuracyCheck(
        passed=(enough and not outdated and value is not None and value >= limits.min_key_accuracy),
        value=value,
        threshold=limits.min_key_accuracy,
        correct=out.correct,
        wrong=out.wrong,
        stale=out.stale,
        unchecked=sum(1 for i in out.items if i.verdict is None),
        sample_id=out.sample_id,
        sample_size=out.size,
        min_sample=limits.min_sample,
        enough_sample=enough,
        sample_outdated=outdated,
        eligible_problems=eligible,
        enough_problems=eligible >= limits.min_sample,
    )


def _cost(conn: Connection, refs: list[str], settings: Settings) -> GateCost:
    """Every recorded call (extract and verify, done or failed) that belongs to a
    `pilot`-kind job: its (page_ref, stage, input_hash) matches one. A full-run call on a
    pilot page under a new input hash (a re-extraction after a prompt change) is a `full`
    job and is not counted, so the full run never changes the estimate."""
    t, j = build_costs, build_jobs
    pilot_jobs = select(j.c.page_ref, j.c.stage, j.c.input_hash).where(j.c.run_kind == PILOT)
    reported, unknown = conn.execute(
        select(
            func.coalesce(func.sum(t.c.cost_usd), 0.0),
            func.coalesce(func.sum(t.c.cost_unknown), 0),
        ).where(tuple_(t.c.page_ref, t.c.stage, t.c.input_hash).in_(pilot_jobs))
    ).one()
    reported, unknown = float(reported), int(unknown)
    cap = settings.extraction_max_budget_usd
    pilot_cost = reported + unknown * cap
    b = content_catalog_books
    total_pages = int(conn.execute(select(func.coalesce(func.sum(b.c.page_count), 0))).scalar_one())
    pages = len(refs)
    remaining = max(0, total_pages - pages)
    per_page = pilot_cost / pages if pages else None
    est = round(per_page * remaining, 2) if per_page is not None else None
    return GateCost(
        pilot_cost=round(pilot_cost, 6),
        reported_cost=round(reported, 6),
        unknown_cost_calls=unknown,
        unknown_cost_cap_usd=cap,
        per_page=per_page,
        pilot_pages=pages,
        total_pages=total_pages,
        remaining_pages=remaining,
        est_cost=est,
    )


def _latest_approval(conn: Connection) -> Any | None:
    g = build_gate
    return conn.execute(select(g).order_by(g.c.id.desc()).limit(1)).first()


def _approval(
    row: Any,
    scope: str,
    limits: GateThresholds,
    accuracy: AccuracyCheck,
    checks_passed: bool,
    est: float | None,
) -> GateApproval | None:
    if row is None or row.revoked_at is not None:
        return None
    reasons: list[str] = []
    if row.scope_hash != scope:
        reasons.append("Phạm vi chạy thử đã thay đổi (có trang mới).")
    if row.sample_id != accuracy.sample_id:
        reasons.append("Đã rút mẫu kiểm tra mới.")
    elif accuracy.sample_outdated:
        reasons.append(MSG_SAMPLE_OUTDATED)
    if json.loads(row.thresholds_json) != limits.model_dump():
        reasons.append("Ngưỡng đánh giá đã thay đổi.")
    if not checks_passed:
        reasons.append("Các tiêu chí đánh giá không còn đạt.")
    if est is None or _cents(est) != _cents(row.est_cost):
        now = "—" if est is None else f"${est:.2f}"
        reasons.append(f"Chi phí ước tính đã thay đổi (${row.est_cost:.2f} → {now}).")
    return GateApproval(
        id=row.id,
        approved_at=row.approved_at,
        est_cost=row.est_cost,
        sample_id=row.sample_id,
        valid=not reasons,
        invalid_reasons=reasons,
    )


def report(conn: Connection, settings: Settings) -> GateReport:
    refs = pilot_refs(conn)
    scope = scope_hash(refs)
    problem_ids = pilot_problem_ids(conn, refs)
    states = load_effective(conn, problem_ids, include_retired=False)
    limits = thresholds(settings)
    fallback = _fallback(states, limits.max_fallback_share)
    eligible = sum(1 for s in states if spotcheck.eligible(s))
    accuracy = _accuracy(conn, limits, scope, eligible)
    books = Counter(_book_of(r) for r in refs)
    cost = _cost(conn, refs, settings)
    checks_passed = bool(refs) and fallback.passed and accuracy.passed
    approval = _approval(
        _latest_approval(conn), scope, limits, accuracy, checks_passed, cost.est_cost
    )
    return GateReport(
        has_pilot=bool(refs),
        pilot_pages=len(refs),
        pilot_problems=len(problem_ids),
        books=[BookPilotPages(book_id=b, pilot_pages=n) for b, n in sorted(books.items())],
        thresholds=limits,
        fallback=fallback,
        accuracy=accuracy,
        cost=cost,
        checks_passed=checks_passed,
        approval=approval,
        approved=approval is not None and approval.valid,
    )


# --------------------------------------------------------------------------- actions


def draw_sample(
    conn: Connection, settings: Settings, *, seed: int | None = None, now: datetime | None = None
) -> str:
    """Rút mẫu mới: a new spot-check sample of `gate_min_sample + 5` pilot Problems (all
    eligible ones when fewer), recording the current pilot scope."""
    refs = pilot_refs(conn)
    ids = pilot_problem_ids(conn, refs)
    if not ids:
        raise AppError(409, "NO_PILOT", "Chưa chạy thử: chưa có bài nào để kiểm tra.")
    size = settings.gate_min_sample + DRAW_MARGIN
    return spotcheck.draw_sample(conn, ids, size, scope_hash=scope_hash(refs), seed=seed, now=now)


def _cents(value: float) -> int:
    return round(value * 100)


def approve(
    conn: Connection,
    settings: Settings,
    accept_cost: bool,
    est_cost_seen: float,
    now: datetime | None = None,
) -> GateReport:
    """Duyệt chạy toàn bộ. Refused with 409 NO_PILOT, SAMPLE_OUTDATED (the sample predates
    the current pilot scope), GATE_CHECKS_FAILED or ESTIMATE_CHANGED (the estimate differs
    to the cent from the one shown); 422 COST_NOT_ACCEPTED when the cost is not accepted."""
    current = report(conn, settings)
    if not current.has_pilot:
        raise AppError(409, "NO_PILOT", "Chưa chạy thử.")
    if not accept_cost:
        raise AppError(422, "COST_NOT_ACCEPTED", "Cần chấp nhận chi phí ước tính.")
    if current.accuracy.sample_outdated:
        raise AppError(409, "SAMPLE_OUTDATED", MSG_SAMPLE_OUTDATED)
    est = current.cost.est_cost
    sample_id = current.accuracy.sample_id
    if not current.checks_passed or est is None or sample_id is None:
        raise AppError(409, "GATE_CHECKS_FAILED", "Chưa đạt đủ các tiêu chí đánh giá.")
    if _cents(est_cost_seen) != _cents(est):
        raise AppError(
            409,
            "ESTIMATE_CHANGED",
            f"Chi phí ước tính đã thay đổi thành ${est:.2f}. Hãy xem lại rồi duyệt.",
        )
    refs = pilot_refs(conn)
    metrics = {
        "fallback_share": current.fallback.value,
        "key_accuracy": current.accuracy.value,
        "est_cost": est,
        "pilot_cost": current.cost.pilot_cost,
        "unknown_cost_calls": current.cost.unknown_cost_calls,
        "pilot_pages": current.pilot_pages,
        "pilot_problems": current.pilot_problems,
        "sample_correct": current.accuracy.correct,
        "sample_wrong": current.accuracy.wrong,
        "pilot_refs": refs,
    }
    conn.execute(
        insert(build_gate).values(
            id=new_id(),
            approved_at=to_iso(now or utc_now()),
            metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            thresholds_json=json.dumps(current.thresholds.model_dump(), sort_keys=True),
            est_cost=est,
            sample_id=sample_id,
            scope_hash=scope_hash(refs),
            revoked_at=None,
        )
    )
    return report(conn, settings)


def revoke(conn: Connection, settings: Settings, now: datetime | None = None) -> GateReport:
    """Thu hồi: withdraws the latest approval (nothing happens when there is none)."""
    row = _latest_approval(conn)
    if row is not None and row.revoked_at is None:
        conn.execute(
            update(build_gate)
            .where(build_gate.c.id == row.id)
            .values(revoked_at=to_iso(now or utc_now()))
        )
    return report(conn, settings)


def require_approval(engine: Engine, settings: Settings) -> GateReport:
    """The guard of every full-corpus entry point: raises GateNotApproved unless the latest
    approval is valid; returns the report."""
    with engine.connect() as conn:
        current = report(conn, settings)
    if not current.approved:
        reasons = current.approval.invalid_reasons if current.approval else []
        raise GateNotApproved(" ".join(reasons) or None)
    return current


def new_pages_would_invalidate(engine: Engine, settings: Settings, refs: list[str]) -> bool:
    """Whether extracting these page refs would invalidate a currently valid approval: an
    approval is valid and some ref is outside the current pilot scope (the pilot's
    warning)."""
    with engine.connect() as conn:
        scope = set(pilot_refs(conn))
        if not any(r not in scope for r in refs):
            return False
        return report(conn, settings).approved
