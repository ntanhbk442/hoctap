"""Serves the built PWA (`frontend/dist`) at `/` with a client-routing fallback."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.routing import compile_path

from hoctap.api.errors import error_response

log = logging.getLogger(__name__)

# Files that must be revalidated so a new build (and service worker) is picked up.
_NO_CACHE = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}

# A missing file with one of these suffixes is a real 404, not a client route.
_STATIC_SUFFIXES = {
    ".js", ".css", ".map", ".png", ".svg", ".ico", ".webmanifest", ".json",
    ".woff2", ".woff", ".txt", ".mp3", ".webp", ".jpg",
}  # fmt: skip

_OTHER_METHODS = ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def build_spa_router(dist_dir: Path) -> APIRouter:
    router = APIRouter(include_in_schema=False)
    warned = False

    def _file(path: Path) -> FileResponse:
        headers = {"Cache-Control": "no-cache"} if path.name in _NO_CACHE else None
        return FileResponse(path, headers=headers)

    @router.api_route("/api", methods=_OTHER_METHODS)
    @router.api_route("/api/{api_path:path}", methods=_OTHER_METHODS)
    def unknown_api(request: Request, api_path: str = "") -> Response:
        # Unknown API paths are 404 for every method (never a 405 from the SPA route).
        # A known API path hit with the wrong method keeps its 405. Known paths come from
        # the (cached) OpenAPI schema, so API routes must stay include_in_schema=True.
        for template, ops in request.app.openapi().get("paths", {}).items():
            regex, _, _ = compile_path(template)
            if regex.match(request.url.path):
                allow = ", ".join(sorted(m.upper() for m in ops if m != "parameters"))
                raise HTTPException(status_code=405, headers={"Allow": allow})
        raise HTTPException(status_code=404)

    @router.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def spa(full_path: str, request: Request) -> Response:
        nonlocal warned
        # Anything under /api that reached here is an unknown API route: JSON, never HTML.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        index = dist_dir / "index.html"
        if not index.is_file():
            if not warned:
                log.warning("frontend not built", extra={"dist_dir": str(dist_dir)})
                warned = True
            return error_response(
                503,
                "FRONTEND_NOT_BUILT",
                "Giao diện chưa được build. Chạy `npm run build` trong thư mục frontend.",
            )

        if full_path:
            if "\x00" in full_path:
                raise HTTPException(status_code=404)
            root = dist_dir.resolve()
            try:
                candidate = (dist_dir / full_path).resolve()
                found = candidate.is_relative_to(root) and candidate.is_file()
            except OSError, ValueError:
                raise HTTPException(status_code=404) from None
            if found:
                return _file(candidate)
            if Path(full_path).suffix.lower() in _STATIC_SUFFIXES:
                raise HTTPException(status_code=404)
        return _file(index)

    return router
