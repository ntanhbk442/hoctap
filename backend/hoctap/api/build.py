"""Build control (status stub until Story 1.10) and the go/no-go gate (Story 1.9).
Guarded by the parent session."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now, get_settings
from hoctap.api.errors import ErrorResponse
from hoctap.builder import gate
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


class BuildStatus(BaseModel):
    state: Literal["idle"]


@router.get("/status", response_model=BuildStatus, operation_id="get_build_status")
def get_build_status() -> BuildStatus:
    return BuildStatus(state="idle")


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
