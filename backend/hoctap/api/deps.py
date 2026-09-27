"""Shared request dependencies for routers."""

from __future__ import annotations

from datetime import datetime

from fastapi import Request
from sqlalchemy import Engine

from hoctap.config import Settings
from hoctap.parent.auth import get_clock


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_now(request: Request) -> datetime:
    return get_clock(request)()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
