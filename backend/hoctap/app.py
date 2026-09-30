"""App factory: API at /api/v1, the built PWA at /, one origin."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from hoctap import __version__
from hoctap.api import (
    assignments,
    build,
    dashboard,
    flags,
    health,
    library,
    parent,
    profiles,
    review,
    sessions,
    setup,
    worksheets,
)
from hoctap.api.assets import build_assets_router
from hoctap.api.errors import ErrorResponse, error_response, install_error_handlers
from hoctap.api.spa import build_spa_router
from hoctap.builder import jobs
from hoctap.config import Settings, load_settings
from hoctap.db.engine import create_db_engine, run_migrations
from hoctap.ids import utc_now
from hoctap.logging import configure_logging, shutdown_logging
from hoctap.parent.auth import load_or_create_secret
from hoctap.parent.backup import MSG_MAINTENANCE, Maintenance

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
HEALTH_PATH = f"{API_PREFIX}/health"


class MaintenanceMiddleware:
    """While a restore swaps the database, every route except health answers 503
    `MAINTENANCE` with a retry hint. Requests already running are counted so the restore
    can wait for them to finish before it touches the file."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == HEALTH_PATH:
            await self.app(scope, receive, send)
            return
        maintenance: Maintenance = scope["app"].state.maintenance
        if not maintenance.enter():
            response = error_response(
                503, "MAINTENANCE", MSG_MAINTENANCE, headers={"Retry-After": "5"}
            )
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            maintenance.leave()


def build_api_router() -> APIRouter:
    api = APIRouter(
        prefix=API_PREFIX,
        responses={
            404: {"model": ErrorResponse, "description": "Not found"},
            422: {"model": ErrorResponse, "description": "Validation error"},
        },
    )
    api.include_router(health.router)
    api.include_router(setup.router)
    api.include_router(parent.router)
    api.include_router(dashboard.router)
    api.include_router(assignments.router)
    api.include_router(review.router)
    api.include_router(profiles.router)
    api.include_router(library.router)
    api.include_router(flags.router)
    api.include_router(sessions.router)
    api.include_router(build.router)
    api.include_router(worksheets.router)
    return api


def create_app(
    settings: Settings | None = None, run_client_factory: jobs.ClientFactory | None = None
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        configure_logging(settings.logs_dir, settings.log_level)
        try:
            app.state.secret_key = load_or_create_secret(settings.data_dir)
            engine = create_db_engine(settings.db_path)
            try:
                run_migrations(engine)
            except BaseException:
                engine.dispose()
                raise
            app.state.engine = engine
            app.state.run_manager = jobs.RunManager(
                engine,
                settings,
                run_client_factory or jobs.default_client_factory,
            )
            log.info(
                "startup",
                extra={"version": __version__, "data_dir": str(settings.data_dir)},
            )
            if not (settings.frontend_dist / "index.html").is_file():
                log.warning("frontend not built", extra={"dist_dir": str(settings.frontend_dist)})
            try:
                yield
            finally:
                engine.dispose()
        finally:
            shutdown_logging()

    app = FastAPI(title="Học Tập", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    # Injectable clock (tests replace it) for PIN lockout and cookie expiry.
    app.state.clock = utc_now
    app.state.maintenance = Maintenance()
    app.state.restore_lock = threading.Lock()
    app.add_middleware(MaintenanceMiddleware)
    install_error_handlers(app)
    app.include_router(build_api_router())
    app.include_router(build_assets_router(settings.data_dir))
    # Registered last so it only catches paths no API route matched.
    app.include_router(build_spa_router(settings.frontend_dist))
    return app
