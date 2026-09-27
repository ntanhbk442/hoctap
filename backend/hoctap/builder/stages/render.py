"""`render`: one page of a book PDF to `data/assets/pages/{book_id}/p{page:03d}.jpg`.

The scale is the largest at which the long edge is at most `render_long_edge` pixels.
The page is a JPEG (quality 85, lowered stepwise until the file is at most
`MAX_IMAGE_BYTES`), because Claude refuses images above about 5 MB and full-page PNG scans
are 5-6 MB. `input_hash` = sha256 of the book fingerprint, the page and the render
settings. Later stages key on the image's content hash (`image_sha256`), not on this.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import pymupdf
from sqlalchemy import Engine

from hoctap.builder import jobs_store

STAGE = "render"
RENDER_VERSION = 2
JPEG_QUALITIES = (85, 75, 65, 55, 45)
MAX_IMAGE_BYTES = 3_500_000


class RenderError(RuntimeError):
    """A page cannot be rendered (zero size, or too large even at the lowest quality)."""


def image_rel_path(book_id: str, page: int) -> str:
    return f"assets/pages/{book_id}/p{page:03d}.jpg"


def image_sha256(path: Path) -> str | None:
    """The sha256 of an image file, or None when it does not exist."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def render_input_hash(fingerprint: str, page: int, long_edge: int) -> str:
    settings = {
        "fingerprint": fingerprint,
        "page": page,
        "long_edge": long_edge,
        "colorspace": "rgb",
        "alpha": False,
        "format": "jpeg",
        "qualities": JPEG_QUALITIES,
        "max_bytes": MAX_IMAGE_BYTES,
        "version": RENDER_VERSION,
        "pymupdf": pymupdf.VersionBind,  # a re-render is cheap; extract keys on content
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def render_pixmap(doc: pymupdf.Document, page: int, long_edge: int) -> pymupdf.Pixmap:
    """Renders 1-based `page` with its long edge at most `long_edge` pixels."""
    pdf_page = doc[page - 1]
    rect = pdf_page.rect
    if not (rect.width > 0 and rect.height > 0):
        raise RenderError(f"page {page} has zero size ({rect.width} x {rect.height} pt)")
    zoom = long_edge / max(rect.width, rect.height)
    for _ in range(8):  # PyMuPDF rounds the pixel box outward; shrink until it fits
        pix = pdf_page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        if max(pix.width, pix.height) <= long_edge:
            return pix
        zoom *= math.nextafter(1.0, 0.0) * (long_edge / max(pix.width, pix.height))
    raise RenderError(f"cannot render page {page} within {long_edge} px")


def encode_jpeg(pix: pymupdf.Pixmap, page: int, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    """JPEG at the first quality in `JPEG_QUALITIES` whose file is at most `max_bytes`."""
    for quality in JPEG_QUALITIES:
        data = pix.tobytes("jpg", jpg_quality=quality)
        if len(data) <= max_bytes:
            return data
    raise RenderError(f"page {page} is over {max_bytes} bytes even at JPEG quality 45")


def render_image(doc: pymupdf.Document, page: int, long_edge: int) -> bytes:
    return encode_jpeg(render_pixmap(doc, page, long_edge), page)


def run_render(
    engine: Engine,
    doc: pymupdf.Document,
    data_dir: Path,
    book_id: str,
    fingerprint: str,
    page: int,
    long_edge: int,
) -> tuple[Path, bool]:
    """Renders the page unless a `done` job with the same input hash exists and its image
    is still on disk. Returns (the image path, whether it was rendered now)."""
    ref = jobs_store.page_ref(book_id, page)
    input_hash = render_input_hash(fingerprint, page, long_edge)
    rel = image_rel_path(book_id, page)
    path = data_dir / rel
    with engine.connect() as conn:
        done = jobs_store.find_done(conn, ref, STAGE, input_hash)
    if done is not None and path.is_file():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    pix = render_pixmap(doc, page, long_edge)
    data = encode_jpeg(pix, page)
    tmp = path.with_suffix(".jpg.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    with engine.begin() as conn:
        jobs_store.record(
            conn,
            ref,
            STAGE,
            input_hash,
            "done",
            output={
                "path": rel,
                "width": pix.width,
                "height": pix.height,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
    return path, True
