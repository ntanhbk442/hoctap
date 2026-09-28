"""App factory: API at /api/v1, the built PWA at /, one origin."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from hoctap import __version__
from hoctap.api import build, health, parent, profiles, review, setup
from hoctap.api.assets import build_assets_router
from hoctap.api.errors import ErrorResponse, install_error_handlers
from hoctap.api.spa import build_spa_router
from hoctap.builder import jobs
from hoctap.config import Settings, load_settings
from hoctap.db.engine import create_db_engine, run_migrations
from hoctap.ids import utc_now
from hoctap.logging import configure_logging, shutdown_logging
from hoctap.parent.auth import load_or_create_secret

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


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
    api.include_router(review.router)
    api.include_router(profiles.router)
    api.include_router(build.router)
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
    install_error_handlers(app)
    app.include_router(build_api_router())
    app.include_router(build_assets_router(settings.data_dir))
    # Registered last so it only catches paths no API route matched.
    app.include_router(build_spa_router(settings.frontend_dist))
    return app
