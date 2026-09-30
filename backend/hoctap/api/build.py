"""Build control (status stub until Story 1.10) and the go/no-go gate (Story 1.9).
Guarded by the parent session."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now, get_run_manager, get_settings
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.builder import gate, jobs
from hoctap.builder.jobs import RunManager
from hoctap.builder.pilot import PilotError, parse_pages
from hoctap.config import Settings
from hoctap.parent.auth import require_parent

router = APIRouter(
    prefix="/build",
    tags=["build"],
    dependencies=[Depends(require_parent)],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in"},
        403: {"model": ErrorResponse, "description": "Setup required"},
    },
)

EngineDep = Annotated[Engine, Depends(get_engine)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
NowDep = Annotated[datetime, Depends(get_now)]
RunManagerDep = Annotated[RunManager, Depends(get_run_manager)]


class BuildStatus(BaseModel):
    state: Literal["idle"]


@router.get("/status", response_model=BuildStatus, operation_id="get_build_status")
def get_build_status() -> BuildStatus:
    return BuildStatus(state="idle")


class CatalogueBookOut(BaseModel):
    book_id: str
    title_vi: str
    page_count: int


@router.get("/books", response_model=list[CatalogueBookOut], operation_id="list_catalogue_books")
def list_catalogue_books(engine: EngineDep) -> list[CatalogueBookOut]:
    """The book catalogue (Story 1.3), for the Extraction screen's book picker."""
    from hoctap.content.catalog.service import list_books

    with engine.connect() as conn:
        return [
            CatalogueBookOut(book_id=b.book_id, title_vi=b.title_vi, page_count=b.page_count)
            for b in list_books(conn)
        ]


@router.get("/gate", response_model=gate.GateReport, operation_id="get_build_gate")
def get_gate(engine: EngineDep, settings: SettingsDep) -> gate.GateReport:
    with engine.connect() as conn:
        return gate.report(conn, settings)


@router.post(
    "/gate/approve",
    response_model=gate.GateReport,
    operation_id="approve_build_gate",
    responses={
        409: {
            "model": ErrorResponse,
            "description": "NO_PILOT, SAMPLE_OUTDATED, GATE_CHECKS_FAILED or ESTIMATE_CHANGED",
        },
        422: {
            "model": ErrorResponse,
            "description": "COST_NOT_ACCEPTED (accept_cost false) or VALIDATION_ERROR",
        },
    },
)
def approve_gate(
    body: gate.ApproveIn, engine: EngineDep, settings: SettingsDep, now: NowDep
) -> gate.GateReport:
    with engine.begin() as conn:
        return gate.approve(conn, settings, body.accept_cost, body.est_cost_seen, now)


@router.post("/gate/revoke", response_model=gate.GateReport, operation_id="revoke_build_gate")
def revoke_gate(engine: EngineDep, settings: SettingsDep, now: NowDep) -> gate.GateReport:
    with engine.begin() as conn:
        return gate.revoke(conn, settings, now)


# --------------------------------------------------------------------------- runs (1.10)

RunStatus = Literal[
    "running",
    "pausing",
    "paused",
    "done",
    "failed",
    "cancelled",
    "stopped_budget",
    "stopped_checkpoint",
    "stopped_gate",
]
RunStage = Literal["render", "extract", "validate", "verify", "crop", "publish"]


class FailedPage(BaseModel):
    page: int
    stage: str
    reason: str
    book_id: str | None = Field(default=None, description="set on a full run's failures")


class UnstartedOut(BaseModel):
    book_id: str
    pages: int = Field(description="pages that would still call Claude")
    reason: str


class RunOut(BaseModel):
    id: str
    book_id: str
    first_page: int
    last_page: int
    status: RunStatus
    stage: RunStage | None
    pages_total: int
    pages_done: int
    cost_usd: float
    cost_unknown_count: int
    failed_pages: list[FailedPage]
    error: str | None
    resumed_from: str | None
    started_at: str
    updated_at: str
    finished_at: str | None
    activity: str = Field(description="human-readable current activity line (Vietnamese)")
    stale: bool = Field(
        description="a `running` row with no progress in 5 minutes: offer Tiếp tục too"
    )
    run_kind: Literal["pilot", "full"] = "pilot"
    full_id: str | None = Field(default=None, description="groups the Book rows of a full run")
    max_total_usd: float | None = Field(default=None, description="a full run's overall cap")
    stop_reason: Literal["budget", "checkpoint", "gate"] | None = None
    unstarted: list[UnstartedOut] = []


class RunListOut(BaseModel):
    runs: list[RunOut]


class RunStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str
    pages: str = Field(description='1-based page range, e.g. "5-7"')
    yes_spend: bool = False


def _run_out(row: dict, now: datetime) -> RunOut:
    return RunOut(**row, activity=jobs.activity_line(row), stale=jobs.is_stale(row, now))


def _pages(pages: str) -> tuple[int, int]:
    try:
        return parse_pages(pages)
    except PilotError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc


@router.post(
    "/runs",
    response_model=RunOut,
    status_code=202,
    operation_id="start_build_run",
    responses={
        409: {"model": ErrorResponse, "description": "RUN_IN_PROGRESS"},
        422: {"model": ErrorResponse, "description": "SPEND_NOT_CONFIRMED or VALIDATION_ERROR"},
    },
)
def start_run(body: RunStartIn, manager: RunManagerDep, now: NowDep) -> RunOut:
    first, last = _pages(body.pages)
    return _run_out(manager.start(body.book_id, first, last, body.yes_spend), now)


@router.post(
    "/runs/{run_id}/pause",
    response_model=RunOut,
    operation_id="pause_build_run",
    responses={404: {"model": ErrorResponse, "description": "RUN_NOT_FOUND"}},
)
def pause_run(run_id: str, manager: RunManagerDep, now: NowDep) -> RunOut:
    return _run_out(manager.pause(run_id), now)


@router.post(
    "/runs/{run_id}/resume",
    response_model=RunOut,
    operation_id="resume_build_run",
    responses={
        404: {"model": ErrorResponse, "description": "RUN_NOT_FOUND"},
        409: {"model": ErrorResponse, "description": "RUN_NOT_PAUSED or RUN_IN_PROGRESS"},
    },
)
def resume_run(run_id: str, manager: RunManagerDep, now: NowDep) -> RunOut:
    return _run_out(manager.resume(run_id), now)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunOut,
    operation_id="cancel_build_run",
    responses={404: {"model": ErrorResponse, "description": "RUN_NOT_FOUND"}},
)
def cancel_run(run_id: str, manager: RunManagerDep, now: NowDep) -> RunOut:
    return _run_out(manager.cancel(run_id), now)


@router.get("/runs/current", response_model=RunOut | None, operation_id="get_current_build_run")
def get_current_run(manager: RunManagerDep, now: NowDep) -> RunOut | None:
    row = manager.current()
    return _run_out(row, now) if row is not None else None


@router.get(
    "/runs/{run_id}",
    response_model=RunOut,
    operation_id="get_build_run",
    responses={404: {"model": ErrorResponse, "description": "RUN_NOT_FOUND"}},
)
def get_run(run_id: str, manager: RunManagerDep, now: NowDep) -> RunOut:
    row = manager.get(run_id)
    if row is None:
        raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy lượt chạy.")
    return _run_out(row, now)


@router.get("/runs", response_model=RunListOut, operation_id="list_build_runs")
def list_runs(
    manager: RunManagerDep, now: NowDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> RunListOut:
    return RunListOut(runs=[_run_out(r, now) for r in manager.list_runs(limit)])


# --------------------------------------------------------------------------- full run (6.2)


class FullPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: int | None = Field(default=None, ge=1, le=5)
    books: list[str] = []


class FullPlanBookOut(BaseModel):
    book_id: str
    title_vi: str
    grade: int
    pages_in_scope: int
    pages_to_call: int
    pages_to_verify: int
    probe: bool = Field(description="a grade 3-5 first Book: a small pilot first, then a stop")
    skipped: str | None = Field(description="why the Book cannot run now")


class FullPlanOut(BaseModel):
    approved: bool = Field(description="the go/no-go approval holds")
    books: list[FullPlanBookOut]
    pages_to_call: int
    estimate_usd: float
    worst_case_usd: float
    gate_est_cost: float | None = Field(description="the gate's estimate for the whole corpus")


class FullStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: int | None = Field(default=None, ge=1, le=5)
    books: list[str] = []
    max_total_usd: float = Field(
        gt=0, allow_inf_nan=False, description="the overall cap over all Books; required"
    )
    yes_spend: bool = False


class FullRunOut(BaseModel):
    full_id: str
    status: RunStatus
    max_total_usd: float
    spent_usd: float
    cost_usd: float
    stop_reason: Literal["budget", "checkpoint", "gate"] | None
    unstarted: list[UnstartedOut]
    books: list[RunOut]
    failed_pages: list[FailedPage]
    current_run_id: str


def _full_out(status: dict, now: datetime) -> FullRunOut:
    books = [_run_out(b, now) for b in status["books"]]
    return FullRunOut(**{**status, "books": books})


@router.post(
    "/full/plan",
    response_model=FullPlanOut,
    operation_id="plan_full_run",
    responses={422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"}},
)
def plan_full_run(
    body: FullPlanIn, manager: RunManagerDep, engine: EngineDep, settings: SettingsDep
) -> FullPlanOut:
    """The ordered plan and the pre-flight estimate. Writes and calls nothing."""
    plan = manager.plan_full(body.grade, tuple(body.books))
    with engine.connect() as conn:
        report = gate.report(conn, settings)
    return FullPlanOut(
        approved=report.approved,
        books=[
            FullPlanBookOut(
                book_id=p.book.book_id,
                title_vi=p.book.title_vi,
                grade=p.book.grade,
                pages_in_scope=len(p.scope),
                pages_to_call=len(p.pending),
                pages_to_verify=len(p.verify_pending),
                probe=p.probe,
                skipped=p.skipped,
            )
            for p in plan.books
        ],
        pages_to_call=plan.calls_pages,
        estimate_usd=plan.estimate_usd,
        worst_case_usd=plan.worst_case_usd,
        gate_est_cost=report.cost.est_cost,
    )


@router.post(
    "/full",
    response_model=FullRunOut | None,
    status_code=202,
    operation_id="start_full_run",
    responses={
        409: {"model": ErrorResponse, "description": "GATE_NOT_APPROVED or RUN_IN_PROGRESS"},
        422: {"model": ErrorResponse, "description": "SPEND_NOT_CONFIRMED or VALIDATION_ERROR"},
    },
)
def start_full_run(body: FullStartIn, manager: RunManagerDep, now: NowDep) -> FullRunOut | None:
    started = manager.start_full(
        body.grade, tuple(body.books), body.max_total_usd, body.yes_spend
    )
    status = manager.full_status(started["full_id"])
    return _full_out(status, now) if status is not None else None


@router.get("/full/current", response_model=FullRunOut | None, operation_id="get_current_full_run")
def get_current_full_run(manager: RunManagerDep, now: NowDep) -> FullRunOut | None:
    status = manager.current_full()
    return _full_out(status, now) if status is not None else None
