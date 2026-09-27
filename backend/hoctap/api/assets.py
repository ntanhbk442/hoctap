"""Serves `data/assets` at `/assets-data/*`.

Crops (`/assets-data/crops/**`) are open to anyone on the LAN: the child needs them.
Source pages (`/assets-data/pages/**`) are whole book scans and need the parent cookie.
Registered before the SPA fallback; not part of the OpenAPI schema.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from hoctap.content.assets import ASSETS_URL
from hoctap.parent.auth import require_parent


def _serve(root: Path, rel: str) -> FileResponse:
    if not rel or "\x00" in rel or "\\" in rel:
        raise HTTPException(status_code=404)
    try:
        base = root.resolve()
        candidate = (root / rel).resolve()
        found = candidate.is_relative_to(base) and candidate.is_file()
    except OSError, ValueError:
        raise HTTPException(status_code=404) from None
    if not found:
        raise HTTPException(status_code=404)
    return FileResponse(candidate, headers={"Cache-Control": "no-cache"})


def build_assets_router(data_dir: Path) -> APIRouter:
    router = APIRouter(prefix=ASSETS_URL, include_in_schema=False)
    assets = data_dir / "assets"

    @router.get("/crops/{path:path}")
    def crops(path: str) -> FileResponse:
        return _serve(assets / "crops", path)

    @router.get("/pages/{path:path}", dependencies=[Depends(require_parent)])
    def pages(path: str) -> FileResponse:
        return _serve(assets / "pages", path)

    return router
