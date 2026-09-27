"""`crop`: the images of a ProblemDoc, cut from the rendered page JPEGs.

Each Problem gets, under `data/assets/crops/{book_id}/{problem_id}/`:

- `{image_key}.jpg` for every entry of its `images`;
- `_problem.jpg`, the bbox of its first source page (the whole Problem, e.g. for the
  Fallback type and the review screen);
- for a Problem spanning pages, also `_problem_p{n}.jpg` for each source page n.

A crop is the bbox grown by `PADDING` (normalised units, 2% of the page) on every side,
clamped to the page, rounded outward to whole pixels, saved as JPEG quality 90.

Each file is one `build_jobs` row (stage `crop`, `page_ref`
`{book_id}#p{page:03d}/{problem_id}/{file}`); `input_hash` = sha256 of the page image
hash, the bbox and the crop version (padding and quality). A crop is skipped when its job
is `done` and its file exists. A Problem whose page images are missing, whose image_key
is not a safe file name, or whose page image cannot be read is reported as failed, so it
is not published. After a Problem is cropped, the other files of its folder are removed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from sqlalchemy import Engine, select

from hoctap.builder import jobs_store
from hoctap.builder.models import build_jobs
from hoctap.builder.stages import render
from hoctap.content.schema import ProblemDoc

STAGE = "crop"
CROP_VERSION = 1  # bump when PADDING, JPEG_QUALITY or the cutting changes
PADDING = 0.02
JPEG_QUALITY = 90
PROBLEM_CROP = "_problem"


def crop_rel_dir(book_id: str, problem_id: str) -> str:
    return f"assets/crops/{book_id}/{problem_id}"


@dataclass(frozen=True)
class CropSpec:
    name: str  # file stem: an image_key, "_problem" or "_problem_p{n}"
    page: int
    bbox: tuple[float, float, float, float]


def _check_name(name: str) -> str:
    """A crop file stem from an image_key: never empty, a path, or a reserved `_` name."""
    if not name or name.startswith(("_", ".")) or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"image_key {name!r} cannot be a crop file name")
    return name


def crop_specs(doc: ProblemDoc) -> list[CropSpec]:
    """Every crop file of a Problem, in a stable order. Raises ValueError for an image_key
    that is not a safe file name."""
    specs = [CropSpec(_check_name(i.image_key), i.page, tuple(i.bbox)) for i in doc.images]
    pages = sorted(doc.source_pages, key=lambda s: s.page)
    first = pages[0]  # the lowest source page
    specs.append(CropSpec(PROBLEM_CROP, first.page, tuple(first.bbox)))
    if len(pages) > 1:
        specs += [CropSpec(f"{PROBLEM_CROP}_p{s.page}", s.page, tuple(s.bbox)) for s in pages]
    return specs


def crop_input_hash(page_sha: str, bbox: Sequence[float]) -> str:
    value = {
        "page_sha256": page_sha,
        "bbox": list(bbox),
        "version": CROP_VERSION,
        "padding": PADDING,
        "quality": JPEG_QUALITY,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def pixel_rect(bbox: Sequence[float], width: int, height: int) -> pymupdf.IRect:
    """The padded bbox in pixels, clamped to the page, at least one pixel each way."""
    x0, y0, x1, y1 = bbox
    left = max(0.0, x0 - PADDING)
    top = max(0.0, y0 - PADDING)
    right = min(1.0, x1 + PADDING)
    bottom = min(1.0, y1 + PADDING)
    px0 = min(max(0, math.floor(left * width)), width - 1)
    py0 = min(max(0, math.floor(top * height)), height - 1)
    px1 = max(px0 + 1, min(width, math.ceil(right * width)))
    py1 = max(py0 + 1, min(height, math.ceil(bottom * height)))
    return pymupdf.IRect(px0, py0, px1, py1)


def cut(page: pymupdf.Pixmap, bbox: Sequence[float]) -> bytes:
    """The JPEG bytes of the padded bbox of a page pixmap."""
    rect = pixel_rect(bbox, page.width, page.height)
    target = pymupdf.Pixmap(page.colorspace, rect, False)
    target.copy(page, rect)
    target.set_origin(0, 0)
    return target.tobytes("jpg", jpg_quality=JPEG_QUALITY)


@dataclass
class CropReport:
    cut: int = 0  # files written now
    skipped: int = 0  # done and on disk
    removed: int = 0  # files no longer in a Problem's crops
    failed: dict[str, str] = field(default_factory=dict)  # problem_id -> why
    ok: list[str] = field(default_factory=list)  # problem_ids with every crop on disk


_PYMUPDF_ERRORS: tuple[type[BaseException], ...] = tuple(
    e
    for e in (
        getattr(pymupdf, "FileDataError", None),
        getattr(getattr(pymupdf, "mupdf", None), "FzErrorBase", None),
    )
    if isinstance(e, type)
)
_CROP_ERRORS = (OSError, RuntimeError, ValueError, *_PYMUPDF_ERRORS)


@dataclass(frozen=True)
class _Cut:
    problem_id: str
    spec: CropSpec
    ref: str
    input_hash: str
    rel: str


def _done_jobs(engine: Engine, book_id: str) -> set[tuple[str, str]]:
    """(page_ref, input_hash) of every `done` crop job of the book, in one query."""
    t = build_jobs
    prefix = t.c.page_ref.startswith(f"{book_id}#p", autoescape=True)
    with engine.connect() as conn:
        rows = conn.execute(
            select(t.c.page_ref, t.c.input_hash).where(
                t.c.stage == STAGE, t.c.status == "done", prefix
            )
        ).all()
    return {(r.page_ref, r.input_hash) for r in rows}


def load_page(path: Path) -> pymupdf.Pixmap:
    return pymupdf.Pixmap(str(path))


def run_crop(
    engine: Engine, data_dir: Path, book_id: str, docs: Sequence[ProblemDoc]
) -> CropReport:
    """Cuts every crop of every Problem that is not already done and on disk, page by page
    (one page image in memory at a time), then removes the files of each cropped Problem's
    folder that are no longer among its crops. The job records are written in one
    transaction at the end (also when a cut raises)."""
    report = CropReport()
    shas: dict[int, str | None] = {}

    def page_path(page: int) -> Path:
        return data_dir / render.image_rel_path(book_id, page)

    def page_sha(page: int) -> str | None:
        if page not in shas:
            shas[page] = render.image_sha256(page_path(page))
        return shas[page]

    done = _done_jobs(engine, book_id)
    planned: dict[str, list[str]] = {}  # problem_id -> its crop file names
    todo: list[_Cut] = []
    for doc in docs:
        try:
            specs = crop_specs(doc)
        except ValueError as exc:
            report.failed[doc.problem_id] = f"crop failed: {exc}"
            continue
        missing = sorted({s.page for s in specs if page_sha(s.page) is None})
        if missing:
            paths = ", ".join(render.image_rel_path(book_id, p) for p in missing)
            report.failed[doc.problem_id] = (
                f"thiếu ảnh trang / page image missing: {paths} "
                "(run `hoctap build pilot` for these pages to render it again)"
            )
            continue
        folder_rel = crop_rel_dir(book_id, doc.problem_id)
        planned[doc.problem_id] = [f"{spec.name}.jpg" for spec in specs]
        for spec in specs:
            rel = f"{folder_rel}/{spec.name}.jpg"
            ref = f"{jobs_store.page_ref(book_id, spec.page)}/{doc.problem_id}/{spec.name}"
            input_hash = crop_input_hash(page_sha(spec.page), spec.bbox)  # type: ignore[arg-type]
            if (ref, input_hash) in done and (data_dir / rel).is_file():
                report.skipped += 1
                continue
            todo.append(_Cut(doc.problem_id, spec, ref, input_hash, rel))

    records: list[tuple[str, str, dict[str, object]]] = []
    loaded: tuple[int, pymupdf.Pixmap] | None = None
    try:
        for job in sorted(todo, key=lambda c: c.spec.page):
            if job.problem_id in report.failed:
                continue
            try:
                if loaded is None or loaded[0] != job.spec.page:
                    loaded = None  # release the previous page first
                    loaded = (job.spec.page, load_page(page_path(job.spec.page)))
                data = cut(loaded[1], job.spec.bbox)
                path = data_dir / job.rel
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".jpg.tmp")
                tmp.write_bytes(data)
                os.replace(tmp, path)
            except _CROP_ERRORS as exc:
                report.failed[job.problem_id] = f"crop failed ({job.spec.name}): {exc}"
                continue
            records.append((job.ref, job.input_hash, {"path": job.rel, "bytes": len(data)}))
            report.cut += 1
    finally:
        loaded = None
        if records:
            with engine.begin() as conn:
                for ref, input_hash, output in records:
                    jobs_store.record(conn, ref, STAGE, input_hash, "done", output=output)

    for problem_id, names in planned.items():
        if problem_id in report.failed:
            continue
        folder = data_dir / crop_rel_dir(book_id, problem_id)
        keep = set(names)
        for path in folder.iterdir() if folder.is_dir() else ():
            if path.is_file() and path.name not in keep:
                path.unlink()
                report.removed += 1
        report.ok.append(problem_id)
    return report
