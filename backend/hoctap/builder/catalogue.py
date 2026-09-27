"""`hoctap build catalogue`: check the catalogue's source files and upsert the rows.

Every file is resolved, opened and fingerprinted before anything is written; any
missing or unreadable file aborts the run with nothing written. File names are
compared NFC-normalised, one path component at a time, because Windows and WSL can
store Vietnamese names in different Unicode forms. No globbing: only the paths in
`hoctap.content.catalog.books.BOOKS` are looked up.
"""

from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pymupdf
from sqlalchemy import Engine

from hoctap.content.catalog.books import BOOKS, CatalogueBook
from hoctap.content.catalog.service import BookRow, UpsertResult, upsert_books

FINGERPRINT_BYTES = 1024 * 1024

NOT_A_FILE = "not a file"
NOT_A_PDF = "not a readable PDF"
ENCRYPTED = "password-protected"
NO_PAGES = "no pages"
READ_ERROR = "read error"


class CatalogueError(Exception):
    """Source files are missing or unreadable. `message` is Vietnamese + English.

    `paths` lists the catalogue paths at fault; `reasons` (same length) says why.
    """

    def __init__(self, message: str, paths: list[str], reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.paths = paths
        self.reasons = reasons or [""] * len(paths)

    def __str__(self) -> str:
        lines = [self.message]
        for path, reason in zip(self.paths, self.reasons, strict=True):
            lines.append(f"  - {path} ({reason})" if reason else f"  - {path}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CatalogueReport:
    rows: list[BookRow]
    result: UpsertResult

    @property
    def total_pages(self) -> int:
        return sum(r.page_count for r in self.rows)


@dataclass(frozen=True)
class Resolution:
    """Where a catalogue path points on disk. `problem` is None when it is a file."""

    path: Path | None
    problem: str | None = None


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def resolve_source(source_dir: Path, rel_path: str) -> Resolution:
    """Finds `rel_path` under `source_dir`, matching each component by its NFC form.

    An exact name wins. Without one, exactly one entry must NFC-match; several
    candidates are an error naming them. Missing: `Resolution(None, None)`.
    """
    current = source_dir
    for part in rel_path.split("/"):
        exact = current / part
        if os.path.lexists(exact):
            current = exact
            continue
        wanted = _nfc(part)
        try:
            names = sorted(os.listdir(current))
        except OSError:
            return Resolution(None)
        matches = [n for n in names if _nfc(n) == wanted]
        if not matches:
            return Resolution(None)
        if len(matches) > 1:
            listed = " | ".join(repr(n) for n in matches)
            return Resolution(None, f"several names match: {listed}")
        current = current / matches[0]
    if not current.is_file():  # a directory, a broken symlink, a device
        return Resolution(current, NOT_A_FILE)
    return Resolution(current)


def fingerprint(path: Path) -> tuple[int, str]:
    """(file size, sha256 hex of the first 1 MB), both from one open handle."""
    with path.open("rb") as fh:
        head = fh.read(FINGERPRINT_BYTES)
        size = os.fstat(fh.fileno()).st_size
    return size, hashlib.sha256(head).hexdigest()


def _page_count(path: Path) -> int | str:
    """The page count, or the reason the PDF cannot be used."""
    try:
        with pymupdf.open(path, filetype="pdf") as doc:
            if doc.needs_pass:
                return ENCRYPTED
            if doc.page_count < 1:
                return NO_PAGES
            return doc.page_count
    except Exception:  # noqa: BLE001 - any PyMuPDF failure means "unreadable"
        return NOT_A_PDF


def collect_rows(source_dir: Path, books: tuple[CatalogueBook, ...] = BOOKS) -> list[BookRow]:
    """Checks every file and builds the rows. Raises CatalogueError; writes nothing."""
    if not source_dir.is_dir():
        raise CatalogueError(
            f"Không tìm thấy thư mục sách {source_dir} (cài đặt source_dir / HOCTAP_SOURCE_DIR) / "
            f"Source folder not found: {source_dir} (setting source_dir / HOCTAP_SOURCE_DIR)",
            [],
        )

    resolved: dict[str, Path] = {}
    missing: list[str] = []
    bad: list[tuple[str, str]] = []
    for book in books:
        res = resolve_source(source_dir, book.source_path)
        if res.problem is not None:
            bad.append((book.source_path, res.problem))
        elif res.path is None:
            missing.append(book.source_path)
        else:
            resolved[book.book_id] = res.path
    if missing:
        raise CatalogueError(
            f"Thiếu {len(missing)} tệp sách trong {source_dir} / "
            f"{len(missing)} source file(s) missing under {source_dir}:",
            missing,
        )

    previous = pymupdf.TOOLS.mupdf_display_errors()
    pymupdf.TOOLS.mupdf_display_errors(False)
    try:
        rows: list[BookRow] = []
        for book in books:
            path = resolved.get(book.book_id)
            if path is None:
                continue  # already in `bad`
            pages = _page_count(path)
            if isinstance(pages, str):
                bad.append((book.source_path, pages))
                continue
            try:
                size, digest = fingerprint(path)
            except OSError:
                bad.append((book.source_path, READ_ERROR))
                continue
            rows.append(
                BookRow(
                    book_id=book.book_id,
                    edition=book.edition,
                    grade=book.grade,
                    volume=book.volume,
                    title_vi=book.title_vi,
                    source_path=book.source_path,
                    page_count=pages,
                    file_size=size,
                    fingerprint=digest,
                )
            )
    finally:
        pymupdf.TOOLS.mupdf_display_errors(bool(previous))
    if bad:
        order = {b.source_path: i for i, b in enumerate(books)}
        bad.sort(key=lambda item: order[item[0]])
        raise CatalogueError(
            f"Không đọc được {len(bad)} tệp sách / {len(bad)} source file(s) could not be read:",
            [p for p, _ in bad],
            [r for _, r in bad],
        )
    return rows


def write_catalogue(
    engine: Engine, rows: list[BookRow], now: datetime | None = None
) -> CatalogueReport:
    """Upserts already-validated rows in one transaction."""
    with engine.begin() as conn:
        result = upsert_books(conn, rows, now)
    return CatalogueReport(rows=rows, result=result)


def build_catalogue(
    engine: Engine,
    source_dir: Path,
    now: datetime | None = None,
    books: tuple[CatalogueBook, ...] = BOOKS,
) -> CatalogueReport:
    """Validates all files, then upserts every row in one transaction."""
    return write_catalogue(engine, collect_rows(source_dir, books), now)
