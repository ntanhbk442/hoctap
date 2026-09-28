"""`builder.jobs`: `RunManager`, the only control surface for a background pilot run
(Story 1.10, AD-7, FR-5).

One run at a time. `RunManager.start()` validates the book and range exactly as
`plan_pilot` does, computes the same pre-flight estimate as the CLI and refuses without
`yes_spend` when a call would be made -- mirroring `hoctap build pilot`'s own spending
guard. It then starts a `threading.Thread` that drives `run_pilot()` one page at a time
(render -> extract -> validate -> verify -> crop -> publish for that page), recording
progress in `build_runs` after each page. Pause and cancel only take effect between pages
(the thread checks its flag before starting the next page's `run_pilot()` call, so a page
already in flight always finishes and is written). No new dedup logic is added: a resumed
run relies on the existing `build_jobs` idempotency (Stories 1.5-1.7) to skip pages already
done.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine, insert, select, update

from hoctap.api.errors import AppError
from hoctap.builder import costs
from hoctap.builder.claude_client import ClaudeCliClient, ClaudeClient
from hoctap.builder.models import build_runs
from hoctap.builder.pilot import (
    PilotError,
    PilotPlan,
    pending_pages,
    pending_verify_pages,
    plan_pilot,
    run_pilot,
)
from hoctap.config import Settings
from hoctap.ids import from_iso, new_id, to_iso, utc_now

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("running", "pausing")
STOPPABLE_STATUSES = (*ACTIVE_STATUSES, "paused")
# A `running` row untouched this long, with no live thread, is treated as a crashed
# server's leftover: the UI offers "Tiếp tục" instead of only "Tạm dừng".
STALE_AFTER = timedelta(minutes=5)
# `current()` only falls back to a settled (done/failed/cancelled) run this recent; an
# older one no longer blocks the picker on page load.
RECENT_SETTLED = timedelta(hours=24)

_STAGE_VI = {
    "render": "vẽ",
    "extract": "trích xuất",
    "validate": "kiểm tra",
    "verify": "kiểm tra đáp án",
    "crop": "cắt ảnh",
    "publish": "xuất bản",
}
_STATUS_VI = {
    "pausing": "Đang dừng…",
    "paused": "Đã tạm dừng",
    "done": "Đã xong",
    "failed": "Lỗi",
    "cancelled": "Đã hủy",
}

ClientFactory = Callable[[Settings], ClaudeClient]


def default_client_factory(settings: Settings) -> ClaudeClient:
    """The real client, exactly as the CLI's own `_spend_client` picks it."""
    if shutil.which(settings.claude_executable) is None:
        raise AppError(
            503,
            "CLAUDE_NOT_AVAILABLE",
            f"Không tìm thấy lệnh `{settings.claude_executable}` (Claude Code CLI) trong "
            f"PATH / `{settings.claude_executable}` (the Claude Code CLI) is not on PATH.",
        )
    return ClaudeCliClient(settings.claude_executable)


@dataclass
class _RunHandle:
    thread: threading.Thread
    pause: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "book_id": row.book_id,
        "first_page": row.first_page,
        "last_page": row.last_page,
        "status": row.status,
        "stage": row.stage,
        "pages_total": row.pages_total,
        "pages_done": row.pages_done,
        "cost_usd": row.cost_usd,
        "cost_unknown_count": row.cost_unknown_count,
        "failed_pages": json.loads(row.failed_pages_json),
        "error": row.error,
        "resumed_from": row.resumed_from,
        "started_at": row.started_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }


def activity_line(run: dict[str, Any]) -> str:
    """A human-readable current activity line, e.g. "Đang trích xuất trang 6/7"."""
    if run["status"] == "running":
        if run["stage"] is None:
            return "Đang chuẩn bị…"
        page = min(run["first_page"] + run["pages_done"], run["last_page"])
        verb = _STAGE_VI.get(run["stage"], run["stage"])
        return f"Đang {verb} trang {page}/{run['last_page']}"
    return _STATUS_VI.get(run["status"], "")


def is_stale(run: dict[str, Any], now: datetime) -> bool:
    """A `running` row whose `updated_at` has not moved in 5 minutes: almost certainly a
    crashed server's leftover row rather than a live run."""
    if run["status"] != "running":
        return False
    return now - from_iso(run["updated_at"]) > STALE_AFTER


class RunManager:
    """The in-process control surface for the pilot run started from the Parent Area.
    Owned by `app.state.run_manager`; every DB access opens its own connection off
    `engine` (never the request's)."""

    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        client_factory: ClientFactory = default_client_factory,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self._handles: dict[str, _RunHandle] = {}

    # ------------------------------------------------------------------ reads

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(build_runs).where(build_runs.c.id == run_id)).first()
        return _row_to_dict(row) if row is not None else None

    def current(self) -> dict[str, Any] | None:
        """The active run (running/pausing), else the most recently started run if it
        settled recently (within `RECENT_SETTLED`); otherwise None, so an old finished
        run does not keep hiding the picker on page load."""
        with self._engine.connect() as conn:
            row = conn.execute(
                select(build_runs)
                .where(build_runs.c.status.in_(ACTIVE_STATUSES))
                .order_by(build_runs.c.id.desc())
                .limit(1)
            ).first()
            if row is None:
                row = conn.execute(
                    select(build_runs).order_by(build_runs.c.id.desc()).limit(1)
                ).first()
        if row is None:
            return None
        run = _row_to_dict(row)
        if run["status"] not in ACTIVE_STATUSES and utc_now() - from_iso(run["updated_at"]) > (
            RECENT_SETTLED
        ):
            return None
        return run

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(build_runs).order_by(build_runs.c.id.desc()).limit(limit)
            ).all()
        return [_row_to_dict(r) for r in rows]

    def _active_row(self, conn: Connection) -> Any | None:
        return conn.execute(
            select(build_runs).where(build_runs.c.status.in_(ACTIVE_STATUSES))
        ).first()

    # ------------------------------------------------------------------ start / resume

    def _needs_calls(self, plan: PilotPlan, todo: list[int]) -> bool:
        verify_todo = set(todo) | set(pending_verify_pages(self._engine, self._settings, plan))
        return bool(todo) or bool(verify_todo)

    def _spend_client(
        self, plan: PilotPlan, todo: list[int], yes_spend: bool
    ) -> ClaudeClient | None:
        needs_calls = self._needs_calls(plan, todo)
        if needs_calls and not yes_spend:
            estimate = costs.estimate(len(todo), self._settings)
            raise AppError(
                422,
                "SPEND_NOT_CONFIRMED",
                "Lệnh này sẽ gọi Claude và tốn tiền. Xác nhận yes_spend để chạy. / This "
                "calls Claude and costs money: confirm yes_spend to run it. "
                + estimate.describe(self._settings.extraction_model),
            )
        return self._client_factory(self._settings) if needs_calls else None

    def _insert_run(
        self,
        *,
        run_id: str,
        book_id: str,
        first: int,
        last: int,
        pages_total: int,
        resumed_from: str | None,
    ) -> None:
        now = to_iso(utc_now())
        with self._engine.begin() as conn:
            conn.execute(
                insert(build_runs).values(
                    id=run_id,
                    book_id=book_id,
                    first_page=first,
                    last_page=last,
                    status="running",
                    stage=None,
                    pages_total=pages_total,
                    pages_done=0,
                    cost_usd=0.0,
                    cost_unknown_count=0,
                    failed_pages_json="[]",
                    error=None,
                    resumed_from=resumed_from,
                    started_at=now,
                    updated_at=now,
                    finished_at=None,
                )
            )

    def _launch(self, run_id: str, plan: PilotPlan, client: ClaudeClient | None) -> None:
        handle = _RunHandle(thread=threading.Thread())
        thread = threading.Thread(target=self._run_body, args=(run_id, plan, client), daemon=True)
        handle.thread = thread
        self._handles[run_id] = handle
        thread.start()

    def start(self, book_id: str, first: int, last: int, yes_spend: bool) -> dict[str, Any]:
        with self._lock:
            with self._engine.connect() as conn:
                if self._active_row(conn) is not None:
                    raise AppError(409, "RUN_IN_PROGRESS", "Đang có một lượt chạy thử khác.")
            try:
                plan = plan_pilot(self._engine, self._settings, book_id, first, last)
            except PilotError as exc:
                raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc
            todo = pending_pages(self._engine, self._settings, plan)
            client = self._spend_client(plan, todo, yes_spend)
            run_id = new_id()
            self._insert_run(
                run_id=run_id,
                book_id=book_id,
                first=first,
                last=last,
                pages_total=len(plan.pages),
                resumed_from=None,
            )
            self._launch(run_id, plan, client)
        return self.get(run_id)  # type: ignore[return-value]

    def resume(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.get(run_id)
            if row is None:
                raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy lượt chạy.")
            # A `running`/`pausing` row with no live thread (a crashed server) is
            # resumable too, the same way `_request_stop` treats it as dead: it is first
            # closed out as `cancelled`, same as calling Hủy on it directly, so the UI's
            # Tiếp tục on a stale row works in one step.
            is_dead = self._handles.get(run_id) is None
            if row["status"] not in ("paused", "cancelled") and not (
                row["status"] in ACTIVE_STATUSES and is_dead
            ):
                raise AppError(
                    409, "RUN_NOT_PAUSED", "Chỉ có thể tiếp tục lượt đã tạm dừng hoặc đã hủy."
                )
            if row["status"] in ACTIVE_STATUSES and is_dead:
                self._finish(run_id, "cancelled", row["pages_done"], row["failed_pages"], None)
            with self._engine.connect() as conn:
                if self._active_row(conn) is not None:
                    raise AppError(409, "RUN_IN_PROGRESS", "Đang có một lượt chạy thử khác.")
            try:
                plan = plan_pilot(
                    self._engine,
                    self._settings,
                    row["book_id"],
                    row["first_page"],
                    row["last_page"],
                )
            except PilotError as exc:
                raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc
            todo = pending_pages(self._engine, self._settings, plan)
            # The original start already confirmed the spend; a resume never re-asks.
            client = self._client_factory(self._settings) if self._needs_calls(plan, todo) else None
            new_run_id = new_id()
            self._insert_run(
                run_id=new_run_id,
                book_id=row["book_id"],
                first=row["first_page"],
                last=row["last_page"],
                pages_total=len(plan.pages),
                resumed_from=run_id,
            )
            self._launch(new_run_id, plan, client)
        return self.get(new_run_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ pause / cancel

    def _request_stop(self, run_id: str, target_status: str) -> dict[str, Any]:
        # Holds the same lock as start()/resume(), so this never races them: the run
        # being stopped either fully exists (and its handle, if any, is registered) or
        # hasn't been launched yet -- there is no in-between state to observe.
        with self._lock:
            row = self.get(run_id)
            if row is None:
                raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy lượt chạy.")
            if row["status"] not in STOPPABLE_STATUSES:
                return row  # already done/failed/cancelled: nothing to do
            if row["status"] == "paused":
                if target_status == "cancelled":
                    self._finish(run_id, "cancelled", row["pages_done"], row["failed_pages"], None)
                    return self.get(run_id)  # type: ignore[return-value]
                return row  # already paused: pause is a no-op
            handle = self._handles.get(run_id)
            if handle is None:
                # A stale `running`/`pausing` row with no live thread (a crashed server).
                self._finish(run_id, target_status, row["pages_done"], row["failed_pages"], None)
                return self.get(run_id)  # type: ignore[return-value]
            if target_status == "cancelled":
                handle.cancel.set()
            else:
                handle.pause.set()
                if row["status"] == "running":
                    self._set(run_id, status="pausing")
            return self.get(run_id)  # type: ignore[return-value]

    def pause(self, run_id: str) -> dict[str, Any]:
        return self._request_stop(run_id, "paused")

    def cancel(self, run_id: str) -> dict[str, Any]:
        return self._request_stop(run_id, "cancelled")

    # ------------------------------------------------------------------ thread body

    def _set(self, run_id: str, **values: Any) -> None:
        values["updated_at"] = to_iso(utc_now())
        with self._engine.begin() as conn:
            conn.execute(update(build_runs).where(build_runs.c.id == run_id).values(**values))

    def _finish(
        self,
        run_id: str,
        status: str,
        pages_done: int,
        failed_pages: list[dict[str, Any]],
        error: str | None,
        cost_usd: float | None = None,
        cost_unknown_count: int | None = None,
    ) -> None:
        now = to_iso(utc_now())
        values: dict[str, Any] = {
            "status": status,
            "stage": None,
            "pages_done": pages_done,
            "failed_pages_json": json.dumps(failed_pages, ensure_ascii=False),
            "error": error,
            "updated_at": now,
            "finished_at": now,
        }
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if cost_unknown_count is not None:
            values["cost_unknown_count"] = cost_unknown_count
        with self._engine.begin() as conn:
            conn.execute(update(build_runs).where(build_runs.c.id == run_id).values(**values))

    def _run_body(self, run_id: str, plan: PilotPlan, client: ClaudeClient | None) -> None:
        handle = self._handles.get(run_id)
        engine, settings = self._engine, self._settings
        book = plan.book
        prefix = f"{book.book_id}#p"
        with engine.connect() as conn:
            baseline = costs.total_cost(conn, prefix)
        failed_pages: list[dict[str, Any]] = []
        pages_done = 0
        cost_unknown_count = 0
        status = "done"
        error: str | None = None
        try:
            for page in plan.pages:
                if handle is not None and handle.cancel.is_set():
                    status = "cancelled"
                    break
                if handle is not None and handle.pause.is_set():
                    status = "paused"
                    break
                self._set(run_id, pages_done=pages_done)
                page_plan = PilotPlan(book, plan.pdf_path, [page])
                try:
                    report = run_pilot(
                        engine,
                        settings,
                        page_plan,
                        client,
                        dry_run=False,
                        out=lambda _line: None,
                        on_stage=lambda stage: self._set(run_id, stage=stage),
                    )
                except PilotError as exc:
                    status, error = "failed", str(exc)
                    break
                failed, unknown = _page_outcome(page, report)
                failed_pages.extend(failed)
                cost_unknown_count += unknown
                pages_done += 1
                with engine.connect() as conn:
                    cost_now = costs.total_cost(conn, prefix) - baseline
                self._set(
                    run_id,
                    stage=None,
                    pages_done=pages_done,
                    cost_usd=cost_now,
                    cost_unknown_count=cost_unknown_count,
                    failed_pages_json=json.dumps(failed_pages, ensure_ascii=False),
                )
        except Exception as exc:  # noqa: BLE001 - an unrecoverable run failure
            status, error = "failed", str(exc)
            log.exception("build run failed", extra={"run_id": run_id})
        finally:
            with engine.connect() as conn:
                cost_final = costs.total_cost(conn, prefix) - baseline
            self._finish(
                run_id, status, pages_done, failed_pages, error, cost_final, cost_unknown_count
            )
            with self._lock:
                self._handles.pop(run_id, None)


def _page_outcome(page: int, report: Any) -> tuple[list[dict[str, Any]], int]:
    """The failed pages (stage + reason) and unknown-cost call count of one page's report."""
    out: list[dict[str, Any]] = []
    unknown = report.extract.unknown_cost_calls
    for reason in report.extract.failed.values():
        out.append({"page": page, "stage": "extract", "reason": reason})
    if report.verify is not None:
        unknown += report.verify.calls.unknown_cost_calls
        for reason in report.verify.calls.failed.values():
            out.append({"page": page, "stage": "verify", "reason": reason})
    if report.publish_report is not None:
        for problem_id, reason in report.publish_report.failed.items():
            out.append({"page": page, "stage": "crop", "reason": f"{problem_id}: {reason}"})
    return out, unknown
