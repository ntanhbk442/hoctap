"""Health router."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from hoctap import __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health", response_model=Health, operation_id="get_health")
def get_health() -> Health:
    return Health(status="ok", version=__version__)
