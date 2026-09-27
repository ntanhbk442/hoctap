---
title: 'Story 1.3: Book catalogue'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_commit: 'tree:eee716fce4f855b2abc7a40404afc3363a85790b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Extraction, the Library and Assignments all need one fixed list of the 30 Toán Books, with stable `book_id`s. Duplicate scan files must be ignored.

**Approach:** An explicit, code-owned catalogue table maps each `book_id` to its Edition, Grade, volume, Vietnamese title and source file under `Sach_Arch/`. `hoctap build catalogue` checks the files, reads page counts with PyMuPDF, and upserts the rows into `content_catalog_books` through `content.catalog`. Running it again changes nothing.

## Boundaries & Constraints

**Always:**
- The catalogue is exactly these 30 books. The `book_id`s are permanent (AD-3).

| book_id | Edition | Grade | Vol | Source file (relative to `Sach_Arch/`) |
|---|---|---|---|---|
| toan1-2020-q1…q4 | 2020 | 1 | 1–4 | `Lớp 1/toán q1.pdf` … `toán q4.pdf` |
| toan2-2020-q1 | 2020 | 2 | 1 | `Lớp 2/Toán Arc - Lớp 2- Quyển 1.pdf` |
| toan2-2020-q2 | 2020 | 2 | 2 | `Lớp 2/Toán Arc- lớp 2-quyển 2.pdf` |
| toan2-2020-q3 | 2020 | 2 | 3 | `Lớp 2/Toán Arc - lớp 2 - quyển 3.pdf` |
| toan2-2020-q4 | 2020 | 2 | 4 | `Lớp 2/Toán Arc - Lớp 2- quyển 4.pdf` |
| toan3-2020-q1…q4 | 2020 | 3 | 1–4 | `Lớp 3/Toan 3- Q1.pdf`, `Toan 3- Q2.pdf`, `Toan 3-Q3.pdf`, `Toan3 -Q4.pdf` |
| toan4-2020-q1…q4 | 2020 | 4 | 1–4 | `Lớp 4/toasn 4 q1.pdf` … `toasn 4 q4.pdf` |
| toan5-2020-q1…q4 | 2020 | 5 | 1–4 | `Lớp 5/toán lớp 5 q1.pdf` … `q4.pdf` |
| toan1-2024-t1 | 2024-25 | 1 | 1 | `Sach_moi/Huong_Dan_Hoc_Toan_1_Tap_1_Archimede_2024_2025.pdf` |
| toan1-2024-t2 | 2024-25 | 1 | 2 | `Sach_moi/Huong_Dan_Hoc_Toan_1_Tap_2_Archimede_2024_2025.pdf` |
| toan2-2024-t1 | 2024-25 | 2 | 1 | `Sach_moi/Huong_Dan_Hoc_Toan_2_Tap_1_Archimede_2024_2025.pdf` |
| toan2-2024-t2 | 2024-25 | 2 | 2 | `Sach_moi/Huong_Dan_Hoc_Toan_2_Tap_2_Archimede_2024_2025-compressed.pdf` |
| toan3-2024-t1 | 2024-25 | 3 | 1 | `Sach_moi/Huong_Dan_Hoc_Toan_3_Tap_1_Archimede_2024_2025-compressed.pdf` |
| toan3-2024-t2 | 2024-25 | 3 | 2 | `Sach_moi/Huong_Dan_Hoc_Toan_3_Tap_2_Archimede_2024_2025-compressed.pdf` |
| toan4-2024-t1 | 2024-25 | 4 | 1 | `Sach_moi/Huong_Dan_Hoc_Toan_4_Tap_1_Archimede_2024_2025.pdf` |
| toan4-2024-t2 | 2024-25 | 4 | 2 | `Sach_moi/Huong_Dan_Hoc_Toan_4_Tap_2_Archimede_2024_2025.pdf` |
| toan5-2024-t1 | 2024-25 | 5 | 1 | `Sach_moi/Hướng dẫn học Toán Lớp 5 Trường Archimedes Quyển 1 mới nhất 2024.pdf` |
| toan5-2024-t2 | 2024-25 | 5 | 2 | `Sach_moi/Hướng dẫn học Toán Lớp 5 Trường Archimedes Quyển 2 mới nhất 2024.pdf` |

- The skipped duplicates are the `-compressed` copies of Toán 1 T1 and Toán 2 T1, and the `-fromzip` copy of Toán 4 T1. The full-quality file of each pair is used.
- Vietnamese display titles: "Toán {g} – Quyển {n} (2020)" and "Toán {g} – Tập {n} (2024–25)".
- File-name matching compares NFC-normalised names, because Windows and WSL can store Vietnamese names in different Unicode forms.
- Only `content.catalog.upsert_books()` writes `content_catalog_books` (AD-2). The builder calls it.
- The source root comes from a `source_dir` setting (default `<repo>/Sach_Arch`, override with `HOCTAP_SOURCE_DIR`).

**Never:**
- No discovery by globbing or guessing file names. The table above is the source of truth.
- No page rendering or extraction (Story 1.5). No Library UI (Story 2.3).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First run | all 30 files present | 30 rows with book_id, edition, grade, volume, title_vi, source_path, page_count, file_size, sha256-of-first-1MB; CLI prints a summary and exits 0 | N/A |
| Re-run | unchanged files | 0 rows changed; `updated_at` untouched; exit 0 | N/A |
| Changed file | a source file's size or fingerprint differs | that row is updated and reported as changed | N/A |
| Missing file | one listed file absent | nothing written; exit 1 listing the missing paths | Vietnamese + English message |
| Unreadable PDF | PyMuPDF cannot open a file | nothing written; exit 1 naming the file | same |
| NFD file name | the name on disk is decomposed Unicode | still matched | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/config.py` -- `Settings`: add `source_dir` (with `HOCTAP_SOURCE_DIR`) following the existing pattern for the `data_dir` and `frontend_dist` fields.
- `backend/hoctap/cli.py` -- subcommands `serve` and `export-openapi` exist. Add a `build` group with `catalogue`.
- `backend/hoctap/db/alembic/versions/0002_parent.py` -- the latest revision. Add `0003_catalog_books` after it.
- `backend/hoctap/content/` -- currently empty. New: `catalog/models.py`, `catalog/service.py` (`upsert_books`, `list_books`), `catalog/books.py` (the constant table).
- `backend/hoctap/builder/` -- currently empty. New: `catalogue.py` (checks files, reads page counts, calls `upsert_books`).
- `backend/hoctap/ids.py` -- UUIDv7 helper (not needed here; `book_id` is the primary key).

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/content/catalog/books.py` -- the 30-entry constant table.
- [x] `backend/hoctap/content/catalog/models.py` + `db/alembic/versions/0003_catalog_books.py` -- the `content_catalog_books` table (the fields from the matrix, plus `created_at` and `updated_at`).
- [x] `backend/hoctap/content/catalog/service.py` -- `upsert_books(conn, rows) -> {inserted, changed, unchanged}` and `list_books(conn)`.
- [x] `backend/hoctap/builder/catalogue.py` + `cli.py build catalogue` -- resolves NFC names, validates all files before writing anything, and fingerprints each file (size plus sha256 of the first 1 MB).
- [x] `backend/tests/test_catalogue.py` -- the matrix rows, using tiny generated PDFs in a temporary source dir (never the real 1.5 GB folder), plus a test that the table has exactly 30 unique ids and exactly 1 file per id.
- [x] Run `hoctap build catalogue` once against the real `Sach_Arch/`, and record the output summary (30 books, total pages) in Implementation Notes.

**Acceptance Criteria:**
- Given the real `Sach_Arch/`, when `uv run hoctap build catalogue` runs, then 30 books are listed with page counts matching `pdfinfo` (about 2,140 pages in total), and a second run reports 0 changes.

## Implementation Notes

- `upsert_books(conn, rows, now=None)` returns an `UpsertResult` with the `book_id` lists `inserted`, `changed` and `unchanged`. A row is rewritten only when one of its fields (including `page_count`, `file_size` or `fingerprint`) differs, so unchanged rows keep `updated_at`. The builder calls it inside one `engine.begin()` transaction, after every file has been resolved, opened and fingerprinted.
- The fingerprint is stored in the `fingerprint` column (the sha256 hex of the first 1 MB). `source_path` stores the catalogue's NFC, `/`-separated relative path, not the name as spelled on disk.
- Name resolution goes one path component at a time: the exact name first, then a directory entry whose NFC form equals the wanted name. There is no globbing.
- `source_dir` can also be set in `hoctap.toml` (`[server] source_dir`), the same way as `data_dir`.
- Real run on 2026-09-26 (WSL, `/mnt/c/.../Sach_Arch`): `30 books, 2140 pages: 30 new, 0 changed, 0 unchanged` (about 8 s). The second run printed `30 books, 2140 pages: 0 new, 0 changed, 30 unchanged`. All 30 page counts match `pdfinfo`, 2140 in total. The two `Hướng dẫn học Toán Lớp 5 … 2024.pdf` files are stored on disk in a non-NFC form and were matched through NFC comparison.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | CLI creates/migrates DB before validating files, then says "Nothing was written" | medium | contradicts matrix "nothing written" on fresh dir → patch (validate first) |
| 2 | Missing/mistyped source_dir reported as 30 missing files | medium | hides misconfiguration → patch |
| 3 | Directory/broken symlink reported as "missing" | low | trivial → patch |
| 4 | mupdf_display_errors forced to True afterwards | low | global state → patch (restore previous) |
| 5 | Fingerprint only hashes first 1 MB | low | frozen intent specifies first 1 MB → reject |
| 6 | Size/hash/page count from separate reads | low | trivial fstat on same handle → patch |
| 7 | Orphan DB rows (ids no longer in BOOKS) never reported | medium | AD-3 permanence; → patch (report in summary) |
| 8 | No UNIQUE source_path / CHECK page_count>0 | low | migration unshipped → patch |
| 9 | Several NFC matches pick sort-first silently | low | → patch (ambiguity is an error) |
| 10 | DB errors in CLI give raw traceback | low | → patch |
| 11 | Concurrent catalogue runs | low | single-user tool → reject |
| 12 | NFD test fails on normalisation-insensitive FS | low | → patch (skip there) |
| 13 | CatalogueError str lacks paths; "30" hard-coded in help/docs; README reflow | low | trivial → patch |
| 14 | Untested: encrypted PDF, zero-page PDF, unreadable after first run leaves rows intact, CLI per-row markers/changed summary | medium | verification gaps → patch |
| 15 | Fingerprint OSError branch untested | low | defer per reviewer |
| 16 | Corrupt-PDF test flips a byte whose location isn't guaranteed | low | → patch (deterministic corruption) |
| 17 | models.py vs migration drift unchecked | low | reject (covered by fresh-DB test) |

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd backend && uv run hoctap build catalogue` (twice) -- expected: 30 books; the second run reports 0 changed
