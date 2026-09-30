"""`hoctap build full`: the whole corpus, Book by Book (Story 6.2, FR-5).

`plan_full()` writes nothing and calls nothing: it orders the Books by (grade, edition,
volume), checks each one's source file, and says which pages would call Claude (the
estimate the spending guard prints). `run_full()` then processes the Books in order with the
existing resumable stages (`pilot.run_pilot`, `run_kind='full'`): the go/no-go approval is
re-checked before every Book, the overall cap is shared by all Books (each Book gets the
remaining budget), and the run stops at the checkpoints below. Failed pages never abort the
run; they are listed and retried by the next invocation (the same idempotent path: a page
with a `done` job for the current input hash is never called again).

Checkpoints (decided by Anh, 2026-09-30):
- grades 1 and 2 (already piloted): the run stops after each grade it worked on; running
  `build full` again is the human "Tiếp tục";
- grades 3-5 (never piloted): the first Book of the grade runs its first `pilot_max_pages`
  pages as `pilot` jobs, then the run stops. Those pages change the gate's pilot scope, so
  the approval is void until the gate is reviewed and approved again; the next invocation
  refuses (`GATE_NOT_APPROVED`) until then, and only then does the rest of the grade run.

One `build_runs` row per Book (`run_kind='full'`, grouped by `full_id`, with the overall cap)
holds the progress; a stop is recorded on the last row. The run never marks itself accepted
and never runs speech, guides or the gate approval.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, insert, select, update

from hoctap.builder import costs, gate
from hoctap.builder.models import build_page_results, build_runs
from hoctap.builder.pilot import (
    PilotError,
    PilotPlan,
    pending_pages,
    pending_verify_pages,
    plan_book,
    run_pilot,
)
from hoctap.config import Settings
from hoctap.content.catalog.service import BookRow, list_books
from hoctap.content.effective import load_effective
from hoctap.content.review import spotcheck
from hoctap.ids import new_id, to_iso, utc_now

log = logging.getLogger(__name__)

Out = Callable[[str], None]

PILOT, FULL = "pilot", "full"
PAUSE_GRADES = (1, 2)  # already piloted: pause after each grade
PROBE_FROM_GRADE = 3  # never piloted: the first Book of the grade is a small pilot first
TARGET_INTERACTIVE = 0.95

STOP_BUDGET, STOP_CHECKPOINT, STOP_GATE = "budget", "checkpoint", "gate"
STOP_STATUS = {
    STOP_BUDGET: "stopped_budget",
    STOP_CHECKPOINT: "stopped_checkpoint",
    STOP_GATE: "stopped_gate",
}
ACTIVE = ("running", "pausing")


# --------------------------------------------------------------------------- plan


@dataclass
class BookPlan:
    book: BookRow
    pdf_path: Path | None
    scope: list[int]  # the pages this run works on (the probe range, or the whole Book)
    pending: list[int]  # scope pages whose extraction would call Claude
    verify_pending: list[int]  # scope pages that would call Claude for the verify pass
    kind: str = FULL  # the run_kind of the jobs it creates: `pilot` for a grade 3-5 probe
    probe: bool = False
    skipped: str | None = None  # why this Book cannot run now

    @property
    def needs_work(self) -> bool:
        return bool(self.pending or self.verify_pending)


@dataclass
class FullPlan:
    books: list[BookPlan]
    extract: costs.Estimate
    verify: costs.Estimate
    grade: int | None = None
    book_ids: tuple[str, ...] = ()

    @property
    def runnable(self) -> list[BookPlan]:
        return [b for b in self.books if b.skipped is None]

    @property
    def calls_pages(self) -> int:
        return sum(len(b.pending) for b in self.runnable)

    @property
    def estimate_usd(self) -> float:
        return round(self.extract.usd + self.verify.usd, 2)

    @property
    def worst_case_usd(self) -> float:
        return round(self.extract.worst_case_usd + self.verify.worst_case_usd, 2)

    def options(self) -> dict[str, Any]:
        return {"grade": self.grade, "books": list(self.book_ids)}


def plan_full(
    engine: Engine,
    settings: Settings,
    *,
    grade: int | None = None,
    books: tuple[str, ...] = (),
) -> FullPlan:
    """The ordered plan; `grade` / `books` narrow it. Raises `PilotError` for an empty
    catalogue or an unknown selection. Nothing is written and nothing is called."""
    with engine.connect() as conn:
        catalogue = list_books(conn)
    if not catalogue:
        raise PilotError(
            "Danh mục sách trống; chạy `hoctap build catalogue` trước / "
            "The book catalogue is empty; run `hoctap build catalogue` first."
        )
    ordered = sorted(catalogue, key=lambda b: (b.grade, b.edition, b.volume))
    first_of_grade: dict[int, str] = {}
    for b in ordered:
        first_of_grade.setdefault(b.grade, b.book_id)
    known = {b.book_id for b in ordered}
    unknown = [x for x in books if x not in known]
    if unknown:
        raise PilotError(f"Không có sách / Unknown book(s): {', '.join(unknown)}")
    selected = [b for b in ordered if not books or b.book_id in set(books)]
    if grade is not None:
        selected = [b for b in selected if b.grade == grade]
    if not selected:
        raise PilotError("Không có sách nào khớp / No book matches --grade / --books.")

    cache: dict[str, tuple[PilotPlan | None, str | None, list[int]]] = {}

    def whole(book: BookRow) -> tuple[PilotPlan | None, str | None, list[int]]:
        if book.book_id not in cache:
            try:
                pp = plan_book(engine, settings, book.book_id, 1, book.page_count)
            except PilotError as exc:
                cache[book.book_id] = (None, str(exc), [])
            else:
                cache[book.book_id] = (pp, None, pending_pages(engine, settings, pp))
        return cache[book.book_id]

    def probe_pages(book: BookRow) -> int:
        return min(settings.pilot_max_pages, book.page_count)

    def probe_done(g: int) -> bool:
        first = next(b for b in ordered if b.book_id == first_of_grade[g])
        pp, _err, pend = whole(first)
        return pp is not None and not any(p <= probe_pages(first) for p in pend)

    plans: list[BookPlan] = []
    for b in selected:
        pp, err, pend = whole(b)
        if pp is None:
            plans.append(BookPlan(b, None, [], [], [], skipped=err))
            continue
        scope, pending, kind, probe = list(pp.pages), pend, FULL, False
        if b.grade >= PROBE_FROM_GRADE and not probe_done(b.grade):
            if b.book_id != first_of_grade[b.grade]:
                plans.append(
                    BookPlan(
                        b,
                        pp.pdf_path,
                        [],
                        [],
                        [],
                        skipped=(
                            f"chờ chạy thử đầu lớp {b.grade} (sách đầu tiên của lớp chưa chạy "
                            f"thử) / grade {b.grade} probe not done yet"
                        ),
                    )
                )
                continue
            n = probe_pages(b)
            scope, pending, kind, probe = scope[:n], [p for p in pend if p <= n], PILOT, True
        scope_plan = PilotPlan(b, pp.pdf_path, scope)
        verify = sorted(set(pending) | set(pending_verify_pages(engine, settings, scope_plan)))
        plans.append(BookPlan(b, pp.pdf_path, scope, pending, verify, kind, probe))

    runnable = [p for p in plans if p.skipped is None]
    return FullPlan(
        plans,
        costs.estimate(sum(len(p.pending) for p in runnable), settings),
        costs.estimate(sum(len(p.verify_pending) for p in runnable), settings),
        grade,
        tuple(books),
    )


def describe_plan(plan: FullPlan, settings: Settings) -> list[str]:
    """The per-Book plan and the pre-flight estimate, for the spending guard."""
    lines = [f"Kế hoạch / Plan: {len(plan.books)} sách / book(s), theo thứ tự / in order:"]
    for p in plan.books:
        b = p.book
        if p.skipped:
            lines.append(f"  - {b.book_id} (lớp {b.grade}): BỎ QUA / SKIPPED: {p.skipped}")
            continue
        tag = " [chạy thử đầu lớp / grade probe, jobs `pilot`]" if p.probe else ""
        lines.append(
            f"  - {b.book_id} (lớp {b.grade}): {len(p.pending)} trang gọi Claude / page(s) to "
            f"call of {len(p.scope)} in scope, {len(p.verify_pending)} to verify{tag}"
        )
    lines.append(plan.extract.describe(settings.extraction_model))
    verify_model = settings.verify_model or settings.extraction_model
    lines.append("verify: " + plan.verify.describe(verify_model))
    lines.append(
        f"Tổng ước tính / Total estimate: ~${plan.estimate_usd:.2f}, worst case "
        f"${plan.worst_case_usd:.2f}"
    )
    return lines


# --------------------------------------------------------------------------- report


@dataclass
class Quality:
    problems: int = 0
    fallback: int = 0
    disagree: int = 0

    @property
    def interactive_share(self) -> float | None:
        return None if not self.problems else 1 - self.fallback / self.problems


@dataclass
class BookReport:
    book_id: str
    grade: int
    kind: str
    status: str  # a build_runs status
    pages_total: int
    pages_done: int
    cost_usd: float
    failed: list[dict[str, Any]] = field(default_factory=list)
    quality: Quality = field(default_factory=Quality)
    run_id: str | None = None


@dataclass
class FullReport:
    full_id: str
    status: str = "done"  # done | paused | cancelled | stopped_* | dry_run
    message: str | None = None
    max_total_usd: float | None = None
    books: list[BookReport] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)  # {book_id, reason}
    unstarted: list[dict[str, Any]] = field(default_factory=list)  # {book_id, pages, reason}
    failed_pages: list[dict[str, Any]] = field(default_factory=list)
    spent_usd: float = 0.0  # counted against the cap (unknown-cost calls at the per-call cap)
    cost_usd: float = 0.0
    estimate_usd: float = 0.0
    requests_written: int = 0
    quality: Quality = field(default_factory=Quality)


def book_quality(engine: Engine, book_id: str) -> Quality:
    """Published, non-retired Problems of the Book, those with a `fallback` Part, and the
    valid extraction rows the second Claude pass disagreed with."""
    with engine.connect() as conn:
        states = load_effective(conn, book_id=book_id, include_retired=False)
        disagree = conn.execute(
            select(func.count()).where(
                build_page_results.c.book_id == book_id,
                build_page_results.c.status == "valid",
                build_page_results.c.verify_status == "disagree",
            )
        ).scalar_one()
    return Quality(len(states), sum(1 for s in states if spotcheck.has_fallback(s)), int(disagree))


def _page_of(ref: str) -> int:
    return int(ref.rsplit("#p", 1)[1])


def _failures(book_id: str, rep: Any) -> tuple[list[dict[str, Any]], int]:
    """A chunk's failed pages (page, stage, reason) and its unknown-cost call count."""
    out: list[dict[str, Any]] = []
    for ref, reason in rep.extract.failed.items():
        page = _page_of(ref)
        out.append({"book_id": book_id, "page": page, "stage": "extract", "reason": reason})
    unknown = rep.extract.unknown_cost_calls
    if rep.verify is not None:
        unknown += rep.verify.calls.unknown_cost_calls
        for ref, reason in rep.verify.calls.failed.items():
            out.append(
                {"book_id": book_id, "page": _page_of(ref), "stage": "verify", "reason": reason}
            )
    if rep.publish_report is not None:
        for problem_id, reason in rep.publish_report.failed.items():
            why = f"{problem_id}: {reason}"
            out.append({"book_id": book_id, "page": 0, "stage": "crop", "reason": why})
    return out, unknown


def describe(report: FullReport) -> list[str]:
    """The run report: per Book, then in total, the failures, and what to do next."""
    lines = []
    for b in report.books:
        q = b.quality
        share = "—" if q.interactive_share is None else f"{q.interactive_share:.1%}"
        lines.append(
            f"{b.book_id}: {b.status}, {b.pages_done}/{b.pages_total} page(s), "
            f"{len(b.failed)} failed, ${b.cost_usd:.4f}; {q.problems} Problem(s), "
            f"interactive {share}, {q.fallback} fallback, {q.disagree} verify disagreement(s)"
        )
    q = report.quality
    share = "—" if q.interactive_share is None else f"{q.interactive_share:.1%}"
    cap = "—" if report.max_total_usd is None else f"${report.max_total_usd:.2f}"
    lines.append(
        f"Tổng / Total: {sum(b.pages_done for b in report.books)}/"
        f"{sum(b.pages_total for b in report.books)} page(s), "
        f"${report.cost_usd:.4f} reported (${report.spent_usd:.4f} counted against the cap {cap}) "
        f"of ~${report.estimate_usd:.2f} estimated; {len(report.failed_pages)} failed page(s)"
    )
    lines.append(
        f"Bài tương tác / Interactive share: {share} of {q.problems} Problem(s) "
        f"(target at least {TARGET_INTERACTIVE:.0%}); {q.disagree} verify disagreement(s)"
    )
    for s in report.skipped:
        lines.append(f"Bỏ qua / Skipped {s['book_id']}: {s['reason']}")
    for u in report.unstarted:
        lines.append(
            f"Chưa chạy / Not started {u['book_id']}: {u['pages']} page(s) ({u['reason']})"
        )
    if report.message:
        lines.append(report.message)
    lines.append(
        'Tiếp theo / Next: mở Khu phụ huynh → Xem lại → "Kiểm tra ngẫu nhiên" (/parent/review'
        "?tab=spot-check) để kiểm tra 100 bài (mục tiêu ≥98% đáp án đúng). Lượt chạy không tự "
        'đánh dấu "đã chấp nhận" / open Parent Area → Review → "Kiểm tra ngẫu nhiên" to '
        "check 100 Problems (target 98% Answer Keys correct). The run never marks itself accepted."
    )
    return lines


def describe_failures(report: FullReport) -> list[str]:
    return [
        f"  - {f['book_id']} p{f['page']} [{f['stage']}]: {f['reason']}"
        for f in report.failed_pages
    ]


# --------------------------------------------------------------------------- rows


def _insert_row(
    engine: Engine,
    *,
    run_id: str,
    full_id: str,
    bp: BookPlan,
    cap: float,
    options: dict[str, Any],
    resumed_from: str | None,
    status: str = "running",
) -> None:
    now = to_iso(utc_now())
    scope = bp.scope or [1]
    with engine.begin() as conn:
        conn.execute(
            insert(build_runs).values(
                id=run_id,
                book_id=bp.book.book_id,
                first_page=scope[0],
                last_page=scope[-1],
                status=status,
                stage=None,
                pages_total=len(bp.scope),
                pages_done=0,
                cost_usd=0.0,
                cost_unknown_count=0,
                failed_pages_json="[]",
                error=None,
                resumed_from=resumed_from,
                started_at=now,
                updated_at=now,
                finished_at=None if status in ACTIVE else now,
                run_kind=FULL,
                full_id=full_id,
                max_total_usd=cap,
                stop_reason=None,
                unstarted_json="[]",
                options_json=json.dumps(options, ensure_ascii=False),
            )
        )


def _set_row(engine: Engine, run_id: str, **values: Any) -> None:
    values["updated_at"] = to_iso(utc_now())
    with engine.begin() as conn:
        conn.execute(update(build_runs).where(build_runs.c.id == run_id).values(**values))


def _finish_row(
    engine: Engine,
    run_id: str,
    status: str,
    *,
    stop_reason: str | None = None,
    unstarted: list[dict[str, Any]] | None = None,
    error: str | None = None,
    **values: Any,
) -> None:
    now = to_iso(utc_now())
    values.update(
        status=status,
        stage=None,
        stop_reason=stop_reason,
        error=error,
        finished_at=now,
        unstarted_json=json.dumps(unstarted or [], ensure_ascii=False),
    )
    _set_row(engine, run_id, **values)


def spent_of(engine: Engine, settings: Settings, full_id: str) -> float:
    """What the rows of a full run have spent against its cap so far (unknown-cost calls at
    the per-call cap): a resumed run continues from it."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(build_runs.c.cost_usd, build_runs.c.cost_unknown_count).where(
                build_runs.c.full_id == full_id
            )
        ).all()
    return sum(r.cost_usd + r.cost_unknown_count * settings.extraction_max_budget_usd for r in rows)


def close_stale_rows(engine: Engine, now_iso: str, stale_before_iso: str) -> None:
    """Rows left `running`/`pausing` by a killed process (untouched for a while) are closed
    as `cancelled`, so they do not block the run lock."""
    with engine.begin() as conn:
        conn.execute(
            update(build_runs)
            .where(build_runs.c.status.in_(ACTIVE), build_runs.c.updated_at < stale_before_iso)
            .values(status="cancelled", stage=None, finished_at=now_iso, updated_at=now_iso)
        )


def active_run(engine: Engine) -> Any | None:
    with engine.connect() as conn:
        return conn.execute(
            select(build_runs).where(build_runs.c.status.in_(ACTIVE)).limit(1)
        ).first()


# --------------------------------------------------------------------------- run


def _stage_setter(engine: Engine, run_id: str) -> Callable[[str], None]:
    def set_stage(stage: str) -> None:
        _set_row(engine, run_id, stage=stage)

    return set_stage


def _chunks(pages: list[int], size: int) -> list[list[int]]:
    return [pages[i : i + size] for i in range(0, len(pages), size)]


def _unstarted(
    engine: Engine, settings: Settings, rest: list[BookPlan], current: BookPlan | None
) -> list[dict[str, Any]]:
    out = []
    if current is not None:
        left = pending_pages(engine, settings, PilotPlan(current.book, Path(), current.scope))
        if left:
            out.append({"book_id": current.book.book_id, "pages": len(left), "reason": "chưa xong"})
    for bp in rest:
        out.append({"book_id": bp.book.book_id, "pages": len(bp.pending), "reason": "chưa bắt đầu"})
    return out


def run_full(
    engine: Engine,
    settings: Settings,
    plan: FullPlan,
    client: Any | None,
    *,
    max_total_usd: float,
    dry_run: bool = False,
    out: Out = print,
    full_id: str | None = None,
    resumed_from: str | None = None,
    already_spent: float = 0.0,
    chunk: int | None = None,
    should_stop: Callable[[], str | None] = lambda: None,
    on_row: Callable[[str], None] = lambda run_id: None,
) -> FullReport:
    """Runs the plan Book by Book (see the module docstring). `chunk` is the number of pages
    per `run_pilot` call (default `pilot_max_pages`; the Parent Area uses 1 so that pause and
    cancel act between pages); `should_stop()` returns `"paused"` / `"cancelled"` to stop
    between chunks; `on_row(run_id)` is told of each Book's row."""
    full_id = full_id or new_id()
    report = FullReport(
        full_id,
        max_total_usd=max_total_usd,
        estimate_usd=plan.estimate_usd,
        skipped=[{"book_id": p.book.book_id, "reason": p.skipped} for p in plan.books if p.skipped],
    )
    runnable = plan.runnable
    if dry_run:
        report.status = "dry_run"
        for bp in runnable:
            rep = run_pilot(
                engine,
                settings,
                PilotPlan(bp.book, bp.pdf_path or Path(), bp.scope),
                None,
                dry_run=True,
                out=out,
                run_kind=bp.kind,
            )
            report.requests_written += len(rep.requests_written)
            if rep.verify is not None:
                report.requests_written += len(rep.verify.requests_written)
        return report

    remaining = max_total_usd - already_spent
    size = chunk or settings.pilot_max_pages
    options = plan.options()
    worked_grades: set[int] = set()
    last_row: str | None = None

    def stop_between(idx: int, reason: str, message: str) -> None:
        """Stops before Book `idx` (or after the last one): recorded on the last row, or on a
        new empty row for the next Book when this invocation has none yet."""
        rest = runnable[idx:]
        report.status = STOP_STATUS.get(reason, reason)
        report.message = message
        report.unstarted = _unstarted(engine, settings, rest, None)
        if last_row is not None:
            _finish_row(
                engine, last_row, report.status, stop_reason=reason, unstarted=report.unstarted
            )
        elif rest:
            run_id = new_id()
            _insert_row(
                engine,
                run_id=run_id,
                full_id=full_id,
                bp=rest[0],
                cap=max_total_usd,
                options=options,
                resumed_from=resumed_from,
                status=report.status,
            )
            _set_row(
                engine,
                run_id,
                stop_reason=reason,
                unstarted_json=json.dumps(report.unstarted, ensure_ascii=False),
            )
            on_row(run_id)

    for idx, bp in enumerate(runnable):
        stop = should_stop()
        if stop:
            report.status, report.message = stop, "Đã dừng theo yêu cầu / Stopped on request."
            report.unstarted = _unstarted(engine, settings, runnable[idx:], None)
            break
        try:
            gate.require_approval(engine, settings)
        except gate.GateNotApproved as exc:
            stop_between(idx, STOP_GATE, f"{exc.code}: {exc.message}")
            break
        run_id = new_id()
        _insert_row(
            engine,
            run_id=run_id,
            full_id=full_id,
            bp=bp,
            cap=max_total_usd,
            options=options,
            resumed_from=resumed_from,
        )
        last_row = run_id
        on_row(run_id)
        prefix = f"{bp.book.book_id}#p"
        with engine.connect() as conn:
            baseline = costs.total_cost(conn, prefix)
        failed: list[dict[str, Any]] = []
        unknown = pages_done = 0
        book_stop: str | None = None
        out(
            f"{bp.book.book_id}: {len(bp.scope)} page(s), {len(bp.pending)} to call"
            + (" (grade probe, pilot jobs)" if bp.probe else "")
        )

        def cost_now(prefix: str = prefix, baseline: float = baseline) -> float:
            with engine.connect() as conn:
                return costs.total_cost(conn, prefix) - baseline

        try:
            for pages in _chunks(bp.scope, size):
                book_stop = should_stop()
                if book_stop:
                    break
                if remaining <= 0 and set(pages) & set(bp.pending):
                    book_stop = STOP_BUDGET
                    break
                chunk_plan = PilotPlan(bp.book, bp.pdf_path or Path(), pages)
                rep = run_pilot(
                    engine,
                    settings,
                    chunk_plan,
                    client,
                    dry_run=False,
                    out=lambda _line: None,
                    max_total_usd=max(remaining, 0.0),
                    run_kind=bp.kind,
                    on_stage=_stage_setter(engine, run_id),
                )
                spent = rep.extract.spent_usd + (
                    rep.verify.calls.spent_usd if rep.verify is not None else 0.0
                )
                remaining -= spent
                report.spent_usd += spent
                found, unk = _failures(bp.book.book_id, rep)
                for f in found:
                    if f["page"] == 0:
                        f["page"] = pages[0]
                failed.extend(found)
                unknown += unk
                pages_done += len(pages) - len(pending_pages(engine, settings, chunk_plan))
                _set_row(
                    engine,
                    run_id,
                    stage=None,
                    pages_done=pages_done,
                    cost_usd=cost_now(),
                    cost_unknown_count=unknown,
                    failed_pages_json=json.dumps(failed, ensure_ascii=False),
                )
                out(
                    f"  {bp.book.book_id} p{pages[0]}-{pages[-1]}: "
                    f"{pages_done}/{len(bp.scope)} done, {len(found)} failure(s), "
                    f"${cost_now():.4f} so far"
                )
                if rep.extract.budget_skipped or (
                    rep.verify is not None and rep.verify.calls.budget_skipped
                ):
                    book_stop = STOP_BUDGET
                    break
        except BaseException as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            _finish_row(
                engine,
                run_id,
                "cancelled" if interrupted else "failed",
                error="interrupted" if interrupted else str(exc),
                pages_done=pages_done,
                failed_pages_json=json.dumps(failed, ensure_ascii=False),
                cost_usd=cost_now(),
                cost_unknown_count=unknown,
            )
            if not interrupted:
                log.exception("full run failed", extra={"full_id": full_id})
            raise

        report.failed_pages.extend(failed)
        report.books.append(
            BookReport(
                bp.book.book_id,
                bp.book.grade,
                bp.kind,
                "done",
                len(bp.scope),
                pages_done,
                cost_now(),
                failed,
                run_id=run_id,
            )
        )
        common: dict[str, Any] = {
            "pages_done": pages_done,
            "failed_pages_json": json.dumps(failed, ensure_ascii=False),
            "cost_usd": cost_now(),
            "cost_unknown_count": unknown,
        }
        if book_stop in ("paused", "cancelled"):
            report.status = book_stop
            report.message = "Đã dừng theo yêu cầu / Stopped on request."
            report.books[-1].status = book_stop
            report.unstarted = _unstarted(engine, settings, runnable[idx + 1 :], bp)
            _finish_row(engine, run_id, book_stop, unstarted=report.unstarted, **common)
            break
        if book_stop == STOP_BUDGET:
            report.status = STOP_STATUS[STOP_BUDGET]
            report.books[-1].status = report.status
            report.unstarted = _unstarted(engine, settings, runnable[idx + 1 :], bp)
            report.message = (
                f"Hết ngân sách ${max_total_usd:.2f} / the overall cap of ${max_total_usd:.2f} "
                "was reached; in-flight pages finished. Re-run `hoctap build full` with a "
                "higher --max-total-usd to continue where it stopped."
            )
            _finish_row(
                engine,
                run_id,
                report.status,
                stop_reason=STOP_BUDGET,
                unstarted=report.unstarted,
                **common,
            )
            break
        if bp.needs_work:
            worked_grades.add(bp.book.grade)
        _finish_row(engine, run_id, "done", **common)
        following = runnable[idx + 1 :]
        if bp.probe:
            report.books[-1].status = "stopped_checkpoint"
            stop_between(
                idx + 1,
                STOP_CHECKPOINT,
                f"Điểm dừng lớp {bp.book.grade} / Checkpoint: the first pages of "
                f"{bp.book.book_id} ran as a pilot. Review them in the Parent Area (draw a new "
                f"Kiểm tra ngẫu nhiên sample, check it, approve the gate again), then run "
                f"`hoctap build full` again to continue grade {bp.book.grade}.",
            )
            break
        if (
            following
            and bp.book.grade in PAUSE_GRADES
            and bp.book.grade in worked_grades
            and following[0].book.grade != bp.book.grade
        ):
            report.books[-1].status = "stopped_checkpoint"
            stop_between(
                idx + 1,
                STOP_CHECKPOINT,
                f"Đã xong lớp {bp.book.grade}; kiểm tra rồi chạy lại `hoctap build full` để "
                f"tiếp tục (Tiếp tục) / Grade {bp.book.grade} is done: review it, then run "
                "`hoctap build full` again to continue.",
            )
            break

    for b in report.books:
        b.quality = book_quality(engine, b.book_id)
    processed = {b.book_id for b in report.books}
    total = Quality()
    for bid in sorted(processed):
        q = next(b.quality for b in report.books if b.book_id == bid)
        total.problems += q.problems
        total.fallback += q.fallback
        total.disagree += q.disagree
    report.quality = total
    report.cost_usd = sum(b.cost_usd for b in report.books)
    return report


def exit_code(report: FullReport) -> int:
    """0 done or paused at a checkpoint, 1 failed pages, 3 the approval no longer holds,
    4 the cap was reached."""
    if report.status == "stopped_gate":
        return 3
    if report.status == "stopped_budget":
        return 4
    return 1 if report.failed_pages else 0
