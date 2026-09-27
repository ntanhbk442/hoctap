"""Child Profiles (read-only; the child picks one without a PIN)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from hoctap.api.deps import get_engine
from hoctap.parent import service
from hoctap.parent.schemas import Profile

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[Profile], operation_id="list_profiles")
def list_profiles(engine: Annotated[Engine, Depends(get_engine)]) -> list[Profile]:
    return service.list_profiles(engine)
