# Epic 1 Context: Anh loads and checks the first grade-1 lessons (pilot)

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build the foundation of Học Tập (a local FastAPI + React PWA that turns scanned Archimedes "Hướng dẫn học Toán" books into spoken, interactive practice) and the content-extraction pipeline, then prove quality and cost on a pilot of about 3 grade-1 Lessons before any money is spent on the full corpus of about 2,140 pages. At the end, Anh (the parent) can install the app on the home Windows PC, set a PIN and create the first Child Profile, run the pilot extraction, review and fix Problems beside their source scans, spot-check Answer Keys, and approve or stop the full run from a go/no-go report that shows the real cost.

## Stories

- Story 1.1: Project scaffold served from one origin
- Story 1.2: First-run setup with PIN and first Child Profile
- Story 1.3: Book catalogue
- Story 1.4: ProblemDoc contract and the grade-1 Problem Types
- Story 1.5: Render and extract pilot pages with Claude
- Story 1.6: Verify answers and flag disagreements
- Story 1.7: Crop, Concept tagging and publish
- Story 1.8: Content Review with overrides
- Story 1.9: Spot-check, pilot report and go/no-go gate
- Story 1.10: Extraction control from the Parent Area
- Story 1.11: HTTPS on the LAN and Windows runtime

## Requirements & Constraints

- **Catalogue:** exactly 30 Toán Books (20 from the 2020 edition: 4 volumes per grade, Tuần → Tiết → Bài; 10 from 2024-25: 2 volumes per grade, Chương/Chủ đề → theory box → Ví dụ → exercises). Skip the duplicate pairs (Toán 1 T1 and Toán 2 T1 full vs `-compressed`; Toán 4 T1 full vs `-fromzip`) and use the higher-quality file of each pair. Every page is a scan; ignore embedded text layers.
- **Extraction output per Problem:** Book, page(s), bounding box, Unit, Lesson, number, Vietnamese instruction with full diacritics, Parts, Problem Type and the images it needs. Keep maths notation (overlines, fractions, `<`/`>`/`=`, tables). Merge Problems that run across pages. Ignore watermarks (including the GomNhom.com QR), headers and footers. Worked examples and theory boxes become Concept Guide material, not Problems.
- **Answer safety:** every Part gets an Answer Key, one Hint and a Solution suited to a grade-1 to grade-5 child. Each key is generated twice independently, and arithmetic is also computed in code. Any disagreement sets `needs_review`, which hides the Problem from the child. A Hint must never contain the answer.
- **Concepts:** tag each Problem with 1–3 Concepts from a per-Grade list shared by both Editions, each about as broad as one Unit's topic. In the pilot, tags are proposals until Anh accepts them.
- **Resumability and reporting:** a killed-and-restarted run never reprocesses a completed page. Report per-page status, failures, pages per minute and API cost so far.
- **Go/no-go gate:** the full run needs fallback share ≤ 15%, Answer Key accuracy ≥ 98% on a spot-check of at least 30 random Problems spread across Problem Types, and Anh accepting the estimated cost. The full run is refused (`GATE_NOT_APPROVED`) until Anh confirms.
- **Content Review:** edit text, Answer Key, Hint, Solution or Problem Type beside the source page; approve (Duyệt) or hide (Ẩn). Edits survive re-extraction, and editing spoken text leads to new audio. New Problems are visible by default; only `needs_review`, parent-flagged and hidden Problems are hidden. `needs_review` Problems and Error Reports appear in the review list.
- **Parent access:** a 4-digit PIN (bcrypt) plus the first Child Profile (name, avatar, Grade) at first run. v1 supports up to 4 profiles but this epic creates only the first.
- **Non-functional:** Vietnamese UI with correct diacritics. All data stays on the home PC; only page images go to the extraction API. Runtime works offline over the home LAN from one local server (tablet plus PC Chrome/Edge).

## Technical Decisions

- **Stack:** scaffold with `npm create @vite-pwa/pwa` (react-ts), then upgrade to Vite 8.3.1, @vitejs/plugin-react 6.1.1, TypeScript 6.0.3, React 19.3.0, vite-plugin-pwa 1.3.0, TanStack Query 5.104.0 and React Router 8.4.0. Backend: Python 3.14 via uv, FastAPI 0.141.1, Uvicorn 0.54.0, Pydantic 2.13.5, SQLAlchemy 2.1.1, Alembic 1.20.0, PyMuPDF 1.28.2, `anthropic>=1.8,<2`. Node 24 LTS. Tests: pytest, Vitest, Playwright.
- **Layout:** `backend/hoctap/{content,learning,parent,builder,api,db}`, `frontend/src/...`, and a gitignored `data/` (`hoctap.db`, `assets/{pages,crops,audio}`, `logs/`, `certs/`). `Sach_Arch/` is read-only.
- **Module dependencies:** api → parent/learning/content/builder.jobs; parent → learning, content; learning → content; builder → content. Nothing else. Routers hold no logic, and mutations happen only in module services inside a transaction.
- **One SQLite database** (`data/hoctap.db`, WAL, Alembic run at startup). Each table prefix has a single writer: `content_catalog_*` is written by the builder through `content.catalog` upserts; `content_review_*` by `content.review`; `parent_*` by `parent`; `build_*` by the builder.
- **ProblemDoc v1** in `hoctap/content/schema.py`: Parts form a union discriminated by `type`, with Problem Type names exactly as listed. Every Part has a `part_key` (the book's own a/b/c labels, otherwise `p1`… in reading order). Every Answer Slot has a `slot_key`. Everything addresses content by (`problem_id`, `part_key`, `slot_key`), never by array position. Text uses an inline LaTeX subset (`\overline`, `\frac`, `<`, `>`, `=`, `\times`, `:`). The extraction request sends `anthropic.transform_schema(ProblemDoc)` as the output format, and each result is re-validated with Pydantic. The TS types are generated with openapi-typescript (`npm run gen:api`) and never hand-written.
- **Stable IDs:** `book_id` values are fixed (e.g. `toan1-2020-q1`). `problem_id` = `{book_id}.{unit_key}.{lesson_key}.{problem_label}`, derived from the book structure, never page order. Re-extraction upserts by id; Problems not found again in a re-extracted Lesson get `retired_at`, and nothing is deleted. Curated Concepts use ids like `g1.so-sanh-so`. Extraction may tag only existing ids, and new ones go to `content_review_concept_proposals`.
- **Review overlay:** an override row is (`problem_id`|`concept_id`, `part_key`?, `field`, `value`, `base_hash`). Only `content.effective_problem()` merges extracted content with the overlay. A changed base sets `review_conflict`, and the override still wins. Each Problem has one `content_review_status` row (`approved_hash`, `hidden`, Error Reports). Approving records the current effective hash.
- **Visibility:** `content.visible_to_child()` is the only child-facing selector: not retired, not hidden, no open parent Error Report, and not `needs_review` unless approved for the current hash. `content.child_view()` is the only projection, and it never carries Answer Keys, Hints or Solutions.
- **Build pipeline:** page stages `render` → `extract` → `validate` → `verify` → `crop` → `publish`, each tracked in `build_jobs` keyed by (`page_ref`, `stage`, `input_hash`) and skipped if already done. Claude calls go through the Claude Code CLI in headless mode (`claude -p --output-format json --json-schema ...`), one call per page with bounded parallelism, with the result taken from `structured_output` and the cost from `total_cost_usd`. There is no API key and no Message Batches (user decision, 2026-09-27). The model is configurable. `verify` gets an independent second answer and runs `builder.arith.evaluate()`. Cost per batch goes to `build_costs`. `builder.jobs` is the only control surface: start, status and Pause (stop new submissions, still collect in-flight results). Gate metrics: `fallback_share`; `key_accuracy` (verdicts stored by `content.review`); `est_cost` = pilot cost per page × pages remaining. Approval is written to `build_gate`.
- **Speech hooks:** `speech_key = sha256(NFC(speech_text) + voice_id)[:16]`, computed by `effective_problem()`. A global `speak-missing` stage runs after publish and after review edits, through a `TtsEngine` adapter (the engine is not chosen yet).
- **Auth:** `/api/v1/parent/*` and `/api/v1/build/*` need a signed httpOnly cookie issued after the PIN, with a 30-minute idle expiry. While no PIN exists, only setup routes are open, and the other parent routes return 403 `SETUP_REQUIRED`. The PIN hash and settings live in `parent_settings`.
- **Serving:** FastAPI serves `frontend/dist` at `/`, the API at `/api/v1` and assets at `/assets-data/*` on one origin. An mkcert certificate for the reserved LAN IP gives TLS on port 8443, bound to the LAN interface only. Plain HTTP must still work, without the service worker. The runtime is native Windows (uv, Python 3.14) with a Private-network firewall rule. WSL is for development, and the builder may run there on the same `data/`.
- **Conventions:** UTF-8 NFC before hashing, comparing or storing. UUIDv7 for runtime rows. UTC ISO-8601 timestamps. snake_case JSON. Errors use `{"error":{"code":"SNAKE_CODE","message":"<vi text>"}}`. JSON-lines logs go to `data/logs/`. Config comes from `hoctap.toml` plus environment variables (`ANTHROPIC_API_KEY`, TTS keys), with no secrets in the database or repo.

## UX & Interaction Patterns

- **Parent Area style:** neutral, factual Vietnamese, numbers first, no exclamation marks. Grey `parent-surface` and `parent-border` with 1px borders (no chunky edge). The PC gets a two-column layout and the tablet one column. Everything must work from the keyboard.
- **First-run setup:** on first open, create the PIN and then the first Child Profile. A child Home with no content shows "Chưa có bài học. Nhờ bố mẹ tải sách nhé!" (No lessons yet. Ask your parents to load the books!). The Parent Area is entered by long-pressing 🔒 for 2 seconds, or from the PC. A wrong PIN shows "Mã PIN chưa đúng" (the PIN isn't right).
- **Content Review tabs:** Cần duyệt (to review: `needs_review`, conflicts, Error Reports), Tất cả (all, by Book), Kiểm tra ngẫu nhiên (spot-check, marked Đúng/Sai) and Khái niệm (accept, rename or merge Concepts). Each Problem opens an editor beside its source page, with Duyệt/Ẩn. An empty list shows "Không có bài cần duyệt." (No problems need review.)
- **Extraction screen:** "Chạy thử (pilot)" (trial run); while running, a progress bar by Book and page, cost so far, a failed-pages list and Tạm dừng/Tiếp tục (pause/resume). When the pilot finishes, a go/no-go report with three green or red checks and the cost estimate, and "Chạy toàn bộ" (run everything) enabled only when all checks pass and Anh confirms. The flow runs pilot → spot-check → report → full run.

## Cross-Story Dependencies

- 1.1 is the base for everything. 1.4 (the schema) must land before 1.5–1.8. Pipeline order: 1.3 → 1.5 → 1.6 → 1.7, then 1.8 (review) and 1.9 (spot-check and gate). 1.10 wraps the builder CLI from 1.5–1.9 in `builder.jobs`. 1.2 (PIN cookie) guards the parent and build routes used by 1.8–1.10. 1.11 can come late but is needed before tablet use.
- The builder CLI (`hoctap build catalogue|pilot|full|speak-missing`) and the Parent Area must share the same `builder.jobs` control and gate check.
- Later epics: Epic 2 relies on `child_view()`, `visible_to_child()`, `speech_key` and the ProblemDoc Part types defined here; its design tokens and Nunito (Story 2.1) come after, so Epic 1 parent screens need only minimal styling. Epic 5 builds Concept curation and Guides on the proposals and curated Concepts created here. Epic 6 reuses this pipeline for the full corpus after the gate passes. The actual TTS engine choice and synthesis may follow the pilot listening test.
