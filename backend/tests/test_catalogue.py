"""Story 1.3: the book catalogue table and `hoctap build catalogue`.

One test per row of the I/O matrix, run against tiny generated PDFs in a temporary
source folder (never the real `Sach_Arch/`), plus checks on the constant table.
"""

from __future__ import annotations

import os
import sqlite3
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import Engine

from hoctap.builder.catalogue import (
    ENCRYPTED,
    NO_PAGES,
    NOT_A_FILE,
    CatalogueError,
    build_catalogue,
    resolve_source,
)
from hoctap.cli import main as cli_main
from hoctap.config import REPO_ROOT, load_settings
from hoctap.content.catalog.books import BOOKS
from hoctap.content.catalog.service import BookRow, list_books, upsert_books
from hoctap.db.engine import create_db_engine, run_migrations

T0 = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
DUPLICATES = {
    "Sach_moi/Huong_Dan_Hoc_Toan_1_Tap_1_Archimede_2024_2025-compressed.pdf",
    "Sach_moi/Huong_Dan_Hoc_Toan_2_Tap_1_Archimede_2024_2025-compressed.pdf",
    "Sach_moi/Huong_Dan_Hoc_Toan_4_Tap_1_Archimede_2024_2025-fromzip.pdf",
}


def _pages_for(index: int) -> int:
    return index % 3 + 1


def _write_pdf(path: Path, pages: int, title: str = "AAAA", **save_kw: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"{path.name} page {i + 1}")
    doc.set_metadata({"title": title})
    doc.save(path, **save_kw)
    doc.close()


ZERO_PAGE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    root = tmp_path / "Sach_Arch"
    for i, book in enumerate(BOOKS):
        _write_pdf(root / book.source_path, _pages_for(i))
    # Duplicates and other subjects sit next to the real files and must be ignored.
    for dup in DUPLICATES:
        _write_pdf(root / dup, 7)
    _write_pdf(root / "Lớp 1" / "tiếng việt q1.pdf", 5)
    return root


@pytest.fixture
def engine(tmp_path: Path):
    eng = create_db_engine(tmp_path / "data" / "hoctap.db")
    run_migrations(eng)
    yield eng
    eng.dispose()


def _db(engine: Engine) -> list[tuple]:
    con = sqlite3.connect(engine.url.database)
    try:
        return con.execute("SELECT * FROM content_catalog_books ORDER BY book_id").fetchall()
    finally:
        con.close()


# --- The constant table -----------------------------------------------------------


def test_table_has_30_unique_books_one_file_each() -> None:
    ids = [b.book_id for b in BOOKS]
    paths = [b.source_path for b in BOOKS]
    assert len(BOOKS) == 30
    assert len(set(ids)) == 30
    assert len(set(paths)) == 30  # exactly one file per id, no file shared
    assert not DUPLICATES & set(paths)
    assert all(p == unicodedata.normalize("NFC", p) for p in paths)
    by_edition = {e: [b for b in BOOKS if b.edition == e] for e in ("2020", "2024-25")}
    assert len(by_edition["2020"]) == 20 and len(by_edition["2024-25"]) == 10
    for grade in range(1, 6):
        assert sorted(b.volume for b in by_edition["2020"] if b.grade == grade) == [1, 2, 3, 4]
        assert sorted(b.volume for b in by_edition["2024-25"] if b.grade == grade) == [1, 2]


def test_ids_and_titles() -> None:
    books = {b.book_id: b for b in BOOKS}
    assert books["toan1-2020-q1"].source_path == "Lớp 1/toán q1.pdf"
    assert books["toan1-2020-q1"].title_vi == "Toán 1 – Quyển 1 (2020)"
    assert books["toan3-2020-q4"].source_path == "Lớp 3/Toan3 -Q4.pdf"
    assert books["toan2-2024-t2"].title_vi == "Toán 2 – Tập 2 (2024–25)"
    assert books["toan5-2024-t2"].source_path == (
        "Sach_moi/Hướng dẫn học Toán Lớp 5 Trường Archimedes Quyển 2 mới nhất 2024.pdf"
    )
    for b in BOOKS:
        kind = "q" if b.edition == "2020" else "t"
        assert b.book_id == f"toan{b.grade}-{b.edition[:4]}-{kind}{b.volume}"


# --- First run --------------------------------------------------------------------


def test_first_run(engine: Engine, source_dir: Path) -> None:
    report = build_catalogue(engine, source_dir, now=T0)
    assert len(report.result.inserted) == 30
    assert report.result.changed == report.result.unchanged == []
    assert report.total_pages == sum(_pages_for(i) for i in range(30))

    with engine.connect() as conn:
        rows = {r.book_id: r for r in list_books(conn)}
    assert set(rows) == {b.book_id for b in BOOKS}
    for i, book in enumerate(BOOKS):
        row = rows[book.book_id]
        path = source_dir / book.source_path
        assert (row.edition, row.grade, row.volume) == (book.edition, book.grade, book.volume)
        assert row.title_vi == book.title_vi
        assert row.source_path == book.source_path
        assert row.page_count == _pages_for(i)
        assert row.file_size == path.stat().st_size
        assert len(row.fingerprint) == 64
    db_rows = _db(engine)
    assert len(db_rows) == 30
    assert {(r[-2], r[-1]) for r in db_rows} == {(T0.isoformat(timespec="microseconds"),) * 2}


# --- Re-run -----------------------------------------------------------------------


def test_rerun_changes_nothing(engine: Engine, source_dir: Path) -> None:
    build_catalogue(engine, source_dir, now=T0)
    before = _db(engine)
    report = build_catalogue(engine, source_dir, now=T1)
    assert report.result.inserted == report.result.changed == []
    assert len(report.result.unchanged) == 30
    assert _db(engine) == before  # updated_at untouched


# --- Changed file -----------------------------------------------------------------


def test_changed_file_updates_that_row(engine: Engine, source_dir: Path) -> None:
    build_catalogue(engine, source_dir, now=T0)
    before = {r[0]: r for r in _db(engine)}
    target = BOOKS[4]
    _write_pdf(source_dir / target.source_path, 9)

    report = build_catalogue(engine, source_dir, now=T1)
    assert report.result.changed == [target.book_id]
    assert len(report.result.unchanged) == 29
    after = {r[0]: r for r in _db(engine)}
    assert after[target.book_id][6] == 9  # page_count
    assert after[target.book_id][-2] == before[target.book_id][-2]  # created_at kept
    assert after[target.book_id][-1] == T1.isoformat(timespec="microseconds")
    assert {k: v for k, v in after.items() if k != target.book_id} == {
        k: v for k, v in before.items() if k != target.book_id
    }


def test_fingerprint_change_detected_with_same_size(engine: Engine, source_dir: Path) -> None:
    target = BOOKS[0]
    path = source_dir / target.source_path
    build_catalogue(engine, source_dir, now=T0)
    size_before, bytes_before = path.stat().st_size, path.read_bytes()
    _write_pdf(path, _pages_for(0), title="BBBB")  # same pages, same length metadata
    assert path.stat().st_size == size_before
    assert path.read_bytes() != bytes_before
    report = build_catalogue(engine, source_dir, now=T1)
    assert report.result.changed == [target.book_id]


# --- Missing file -----------------------------------------------------------------


def test_missing_file_writes_nothing(engine: Engine, source_dir: Path) -> None:
    (source_dir / BOOKS[3].source_path).unlink()
    (source_dir / BOOKS[25].source_path).unlink()
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert err.value.paths == [BOOKS[3].source_path, BOOKS[25].source_path]
    assert "Thiếu" in err.value.message and "missing" in err.value.message
    assert _db(engine) == []


def test_missing_file_after_first_run_changes_nothing(engine: Engine, source_dir: Path) -> None:
    build_catalogue(engine, source_dir, now=T0)
    before = _db(engine)
    _write_pdf(source_dir / BOOKS[1].source_path, 9)  # would be a change
    (source_dir / BOOKS[2].source_path).unlink()
    with pytest.raises(CatalogueError):
        build_catalogue(engine, source_dir, now=T1)
    assert _db(engine) == before


# --- Unreadable PDF ---------------------------------------------------------------


def test_unreadable_pdf_writes_nothing(engine: Engine, source_dir: Path) -> None:
    bad = BOOKS[7]
    path = source_dir / bad.source_path
    path.write_bytes(path.read_bytes()[:16])  # truncated: header only, no objects or xref
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert err.value.paths == [bad.source_path]
    assert "Không đọc được" in err.value.message and "could not be read" in err.value.message
    assert bad.source_path in str(err.value)
    assert _db(engine) == []


def test_encrypted_pdf_is_unreadable(engine: Engine, source_dir: Path) -> None:
    bad = BOOKS[2]
    _write_pdf(
        source_dir / bad.source_path,
        1,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="user",
        owner_pw="owner",
    )
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert (err.value.paths, err.value.reasons) == ([bad.source_path], [ENCRYPTED])
    assert _db(engine) == []


def test_zero_page_pdf_is_unreadable(engine: Engine, source_dir: Path) -> None:
    bad = BOOKS[5]
    (source_dir / bad.source_path).write_bytes(ZERO_PAGE_PDF)
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert err.value.paths == [bad.source_path]
    assert err.value.reasons[0] in {NO_PAGES, "not a readable PDF"}
    assert _db(engine) == []


def test_unreadable_after_first_run_leaves_rows(engine: Engine, source_dir: Path) -> None:
    build_catalogue(engine, source_dir, now=T0)
    before = _db(engine)
    _write_pdf(source_dir / BOOKS[1].source_path, 9)  # would be a change
    (source_dir / BOOKS[2].source_path).write_bytes(ZERO_PAGE_PDF[:20])
    with pytest.raises(CatalogueError):
        build_catalogue(engine, source_dir, now=T1)
    assert _db(engine) == before


def test_directory_in_place_of_file_is_not_a_file(engine: Engine, source_dir: Path) -> None:
    bad = BOOKS[0]
    path = source_dir / bad.source_path
    path.unlink()
    path.mkdir()
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert (err.value.paths, err.value.reasons) == ([bad.source_path], [NOT_A_FILE])
    assert "missing" not in err.value.message
    assert _db(engine) == []


def test_missing_source_dir(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, tmp_path / "nowhere", now=T0)
    assert err.value.paths == []
    assert "HOCTAP_SOURCE_DIR" in str(err.value) and "source_dir" in str(err.value)
    assert _db(engine) == []


def test_ambiguous_nfc_names_are_an_error(engine: Engine, source_dir: Path) -> None:
    # "ớ" has three spellings with the same NFC form: U+1EDB, o+U+031B+U+0301, U+01A1+U+0301.
    nfc_dir = source_dir / "Lớp 1"
    decomposed = source_dir / "Lo\u031b\u0301p 1"
    partial = source_dir / "L\u01a1\u0301p 1"
    nfc_dir.rename(decomposed)
    if nfc_dir.exists():
        pytest.skip("filesystem is normalisation-insensitive")
    partial.mkdir()
    if len(os.listdir(source_dir)) < 7:  # the FS merged the two spellings
        pytest.skip("filesystem is normalisation-insensitive")
    book = BOOKS[0]
    res = resolve_source(source_dir, book.source_path)
    assert res.path is None and res.problem and "several names match" in res.problem
    with pytest.raises(CatalogueError) as err:
        build_catalogue(engine, source_dir, now=T0)
    assert [p for p in err.value.paths if p.startswith("Lớp 1/")] == [
        b.source_path for b in BOOKS if b.grade == 1 and b.edition == "2020"
    ]
    assert "several names match" in str(err.value)
    assert _db(engine) == []


# --- NFD file name ----------------------------------------------------------------


def test_nfd_file_name_still_matched(engine: Engine, source_dir: Path) -> None:
    book = next(b for b in BOOKS if b.book_id == "toan5-2024-t1")
    nfc_path = source_dir / book.source_path
    nfd_name = unicodedata.normalize("NFD", nfc_path.name)
    assert nfd_name != nfc_path.name
    nfc_path.rename(nfc_path.with_name(nfd_name))
    # The folder name, too.
    grade1 = source_dir / "Lớp 1"
    grade1.rename(source_dir / unicodedata.normalize("NFD", "Lớp 1"))
    if nfc_path.exists() or grade1.exists():
        pytest.skip("filesystem is normalisation-insensitive: NFC name opens the NFD file")

    assert resolve_source(source_dir, book.source_path).path == nfc_path.with_name(nfd_name)
    report = build_catalogue(engine, source_dir, now=T0)
    assert len(report.result.inserted) == 30
    with engine.connect() as conn:
        stored = {r.book_id: r.source_path for r in list_books(conn)}
    assert stored[book.book_id] == book.source_path  # stored NFC


# --- CLI and config ---------------------------------------------------------------


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source_dir: Path) -> Path:
    monkeypatch.setenv("HOCTAP_CONFIG", str(tmp_path / "hoctap.toml"))
    (tmp_path / "hoctap.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(tmp_path / "cli-data"))
    monkeypatch.setenv("HOCTAP_SOURCE_DIR", str(source_dir))
    return tmp_path / "cli-data"


def test_cli_build_catalogue_twice(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    total = sum(_pages_for(i) for i in range(30))
    assert cli_main(["build", "catalogue"]) == 0
    out = capsys.readouterr().out
    assert f"30 books, {total} pages: 30 new, 0 changed, 0 unchanged, 0 orphaned" in out
    assert "Toán 1 – Quyển 1 (2020)" in out
    book_lines = [line for line in out.splitlines() if line.startswith("toan")]
    assert len(book_lines) == 30 and all(line.endswith("  new") for line in book_lines)

    assert cli_main(["build", "catalogue"]) == 0
    out = capsys.readouterr().out
    assert f"30 books, {total} pages: 0 new, 0 changed, 30 unchanged, 0 orphaned" in out
    assert (cli_env / "hoctap.db").is_file()


def test_cli_changed_file_marked(
    cli_env: Path, source_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["build", "catalogue"]) == 0
    capsys.readouterr()
    _write_pdf(source_dir / BOOKS[4].source_path, 9)
    assert cli_main(["build", "catalogue"]) == 0
    out = capsys.readouterr().out
    assert "0 new, 1 changed, 29 unchanged" in out
    marked = [line for line in out.splitlines() if line.endswith("changed")]
    assert len(marked) == 1 and marked[0].startswith(BOOKS[4].book_id)


def test_cli_missing_file_exit_1(
    cli_env: Path, source_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (source_dir / BOOKS[0].source_path).unlink()
    assert cli_main(["build", "catalogue"]) == 1
    err = capsys.readouterr().err
    assert BOOKS[0].source_path in err
    assert "Thiếu" in err and "missing" in err and "Nothing was written" in err
    assert not (cli_env / "hoctap.db").exists()


def test_cli_unreadable_file_exit_1(
    cli_env: Path, source_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (source_dir / BOOKS[9].source_path).write_bytes(ZERO_PAGE_PDF[:20])
    assert cli_main(["build", "catalogue"]) == 1
    err = capsys.readouterr().err
    assert BOOKS[9].source_path in err
    assert "Không đọc được" in err and "could not be read" in err
    assert not (cli_env / "hoctap.db").exists()


ORPHAN = BookRow("toan1-2019-q1", "2020", 1, 1, "Toán cũ", "old/toan.pdf", 3, 100, "0" * 64)


def test_orphaned_ids_reported_not_deleted(engine: Engine, source_dir: Path) -> None:
    with engine.begin() as conn:
        upsert_books(conn, [ORPHAN], now=T0)
    report = build_catalogue(engine, source_dir, now=T1)
    assert report.result.orphaned == [ORPHAN.book_id]
    assert len(_db(engine)) == 31  # kept, not deleted


def test_cli_shows_orphaned(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eng = create_db_engine(cli_env / "hoctap.db")
    try:
        run_migrations(eng)
        with eng.begin() as conn:
            upsert_books(conn, [ORPHAN], now=T0)
    finally:
        eng.dispose()
    assert cli_main(["build", "catalogue"]) == 0
    out = capsys.readouterr().out
    assert f"orphaned (in the database, not in the catalogue): {ORPHAN.book_id}" in out
    assert "30 new, 0 changed, 0 unchanged, 1 orphaned" in out


def test_source_dir_setting(tmp_path: Path) -> None:
    absent = tmp_path / "absent.toml"
    assert load_settings(absent, env={}).source_dir == REPO_ROOT / "Sach_Arch"
    s = load_settings(absent, env={"HOCTAP_SOURCE_DIR": str(tmp_path / "src")})
    assert s.source_dir == tmp_path / "src"
    cfg = tmp_path / "hoctap.toml"
    cfg.write_text('[server]\nsource_dir = "books"\n', encoding="utf-8")
    assert load_settings(cfg, env={}).source_dir == (tmp_path / "books").resolve()
