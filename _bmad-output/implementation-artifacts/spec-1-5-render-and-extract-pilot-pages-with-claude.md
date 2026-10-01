---
title: 'Story 1.5: Render and extract pilot pages with Claude'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'tree:0ca268c199f12251e552890ffe3edadd1d32b6ab'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/reference/anthropic-python-batches.md'
  - '{project-root}/docs/reference/anthropic-python-structured-output.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The scanned pages must become validated ProblemDocs. Extraction must be resumable, idempotent and cost-tracked, and it must never spend money by accident.

**Approach:**
- A `builder` pipeline with the stages `render` → `extract` → `validate`, recorded in `build_jobs` and keyed by (`page_ref`, `stage`, `input_hash`).
- `render` writes a page PNG.
- `extract` sends one Message Batches request per page to `claude-opus-5`, with adaptive thinking and structured output built from a page-level `PageExtraction` model that reuses the ProblemDoc Part union.
- `validate` assigns the structural keys deterministically (carried forward in page order) and turns each draft into a ProblemDoc.
- All Claude access goes through a `ClaudeClient` protocol, and a `FakeClaudeClient` drives every test.

## Boundaries & Constraints

**Always:**
- **`page_ref`** = `{book_id}#p{page:03d}`, using 1-based pages.
- **`render`**: PyMuPDF renders at the largest scale where the long edge is ≤ 2576 px, as a PNG in `data/assets/pages/{book_id}/p{page:03d}.png`. `input_hash` = the book fingerprint + page + render settings.
- **`PageExtraction`** is the model's output for one page. Its fields:
  - `unit_heading: {label, title} | null`: the "TUẦN 3" (week 3) or chapter heading, if one is printed on this page.
  - `lesson_heading: {label, title} | null`: the "Tiết 2" (lesson 2) or "Phiếu tự luyện cuối tuần" (end-of-week practice sheet) heading, if printed.
  - `problems`: a list of drafts. Each draft has: `problem_label` ("bai3"), `display_label`, `instruction`, `layout`, `images` (bbox on this page), `parts` (the ProblemDoc Part union: answer, hint and solution included), `concept_proposals`, and `continues_on_next_page: bool`.
  - `worked_examples`: a list of `{title, text}` from theory boxes and "Ví dụ" blocks. These are kept for the Concept Guides in Epic 5, never as Problems.
  - `page_notes`: short text, for example "blank page" or "cover".
- **The request** sends the page image, plus the next page's image only as context for problems that continue onto it. The prompt says:
  - extract only problems that start on this page;
  - use Vietnamese NFC text and the inline LaTeX subset;
  - use the exact Part types;
  - ignore watermarks, the GomNhom QR code, headers and footers;
  - use canonical numbers with a decimal comma;
  - use `fallback` when the problem can't be made interactive.
- **The schema** is passed as `output_config.format` from `anthropic.transform_schema(PageExtraction)`. The same test guard as Story 1.4 checks that no answer schema collapses.
- **`validate`**:
  - It carries the unit and lesson headings forward in page order within a book. `unit_key`/`lesson_key` are slugs of the labels ("tuan03", "tiet2", "phieu"); pages before the first heading use "u00"/"l00".
  - It builds `problem_id` via the ProblemDoc rule, merges a draft that has `continues_on_next_page` with the next page's page reference and images, and validates with Pydantic.
  - An invalid draft is recorded with its errors and does not fail the other pages.
  - Duplicate `problem_id`s get `-2`, `-3` suffixes, and the duplicate is flagged.
- **Cost:** every batch result records its input, output and cache tokens in `build_costs`. Prices come from config: `claude-opus-5` input $5 and output $25 per MTok, with a 50% batch discount.
- **Spending guard:** any command that would call the API prints the page count and a pre-flight cost estimate (from a count-tokens estimate or a fixed per-page estimate) and refuses to run without `--yes-spend`. `--dry-run` builds and saves the requests without sending them.
- **Resume:** a stage is skipped when a `done` job with the same `input_hash` exists. A batch already submitted is re-polled and collected by its stored batch id, never resubmitted. A `refusal` or `errored` result marks that page `failed`, and the run continues.
- **Storage:** `build_*` tables only: `build_jobs`, `build_batches`, `build_costs`, `build_page_results` (validated ProblemDoc JSON per problem, plus invalid drafts with errors). Publishing to `content_catalog_*` is Story 1.7.

**Never:**
- No real API call in any test. No `ANTHROPIC_API_KEY` needed for tests.
- No verification pass (Story 1.6), no crops or publish (Story 1.7), no UI (Story 1.10).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dry run | `hoctap build pilot --book toan1-2020-q1 --pages 5-7 --dry-run` | 3 PNGs rendered, 3 request JSONs saved, estimate printed, no API call | N/A |
| Guard | same, without `--dry-run` or `--yes-spend` | exit 2, nothing sent, message explains `--yes-spend` | N/A |
| Happy path (fake) | fake returns valid extractions | 3 pages done; ProblemDocs stored with carried-forward keys; costs recorded | N/A |
| Resume | re-run the same command | 0 new renders, 0 new requests | N/A |
| Crash mid-batch | batch id stored, results not collected | re-run polls the stored batch and does not resubmit | N/A |
| Continuation | problem on p5 has `continues_on_next_page` | one ProblemDoc with source_pages p5+p6 | N/A |
| Refusal/error | fake returns refusal for p6 | p6 `failed`; p5, p7 done; exit code 0 with a warning | N/A |
| Invalid draft | fake returns a Part violating ProblemDoc | draft stored as invalid with the errors; other problems saved | N/A |
| No API key | `--yes-spend` with no key | exit 2 with a clear message before any render or submit | N/A |
| Bad range | page 0 or beyond page_count | exit 2 | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/content/schema.py` -- the ProblemDoc v1 and Part union (Story 1.4). Reuse the Part models, `answer_map` and `parse_number`. Do not duplicate them.
- `backend/hoctap/content/catalog/service.py` -- `list_books()` gives page_count and fingerprint, used for range checks and `input_hash`.
- `backend/hoctap/builder/catalogue.py` -- the pattern for validate-before-write and CatalogueError.
- `backend/hoctap/cli.py` -- the `build` group with `catalogue`. Add `pilot`.
- `backend/hoctap/config.py` -- add `extraction_model` (default `claude-opus-5`), prices and `render_long_edge` (2576).
- Migrations: the latest is `0003_catalog_books`. Add `0004_build_tables`.
- The SDK usage (Message Batches, `output_config.format`, `transform_schema`, refusal handling) must follow the two reference docs in `context`. Don't guess method names.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/builder/extraction/models.py` -- `PageExtraction` and the draft models, reusing the Part union, plus the transform-schema guard test.
- [x] `backend/hoctap/builder/extraction/prompt.py` -- the system prompt and user content builder (in Vietnamese-aware English instructions).
- [x] `backend/hoctap/builder/claude_client.py` -- the `ClaudeClient` protocol, `AnthropicBatchClient` (real) and `FakeClaudeClient` (tests).
- [x] `backend/hoctap/builder/stages/{render,extract,validate}.py` + `builder/jobs_store.py` -- the stage runners and the idempotent job records.
- [x] `backend/hoctap/builder/costs.py` -- token-to-cost conversion and the pre-flight estimate.
- [x] `db/alembic/versions/0004_build_tables.py` + the models -- the four `build_*` tables.
- [x] `backend/hoctap/cli.py build pilot` -- with `--book`, `--pages a-b`, `--dry-run` and `--yes-spend`.
- [x] `backend/tests/test_extraction.py` -- one test per matrix row, using small generated PDFs and the fake client.

**Acceptance Criteria:**
- Given the real catalogue, when `hoctap build pilot --book toan1-2020-q1 --pages 5-7 --dry-run` runs, then the three page PNGs and requests exist and an estimate is printed, and no network call happens.

## Implementation Notes

- **Client (per the 2026-09-27 change log):** `ClaudeCliClient` runs this command in a fresh temp directory:

  `claude -p <prompt> --output-format json --json-schema <schema> --system-prompt <prompt> --tools Read --add-dir <pages dir> --restricted --strict-mcp-config --disable-slash-commands --no-session-persistence --model <m> --max-budget-usd <x.xx>`

  - `--restricted` ignores the user, project and local settings files. `--strict-mcp-config` loads no MCP servers. `--disable-slash-commands` turns off skills. `--bare` was not used because it requires `ANTHROPIC_API_KEY`.
  - The prompt comes straight after `-p` because `--tools` and `--add-dir` take several values.
  - The process is started with `Popen` so that Ctrl-C can terminate it.
  - The schema is the committed `builder/extraction/page_extraction.schema.json`, generated by `hoctap export-extraction-schema` (`transform_schema(PageExtraction)` without the cosmetic titles). The runtime doesn't import anthropic at all; that import takes about 38 s on `/mnt/c`.
- **Failures and costs:** the result is the whole stdout, or failing that the last JSON line.
  - Failures: a non-zero exit, `is_error`, a `subtype` other than `success`, or a missing `structured_output`.
  - Not retried: `error_max_budget_usd`, `error_max_structured_output_retries`, a missing `structured_output`, and auth, login or unknown-model errors.
  - Retried once: other errors, and an ok output that fails `PageEnvelope`.
  - A timeout or unparsable output is recorded with `cost_unknown = 1`.
  - Every attempt goes to `build_costs`, including attempts made before a later attempt raised. A DB write error doesn't stop the other pages; the first error is re-raised at the end.
- **Run budget:** no new page starts once this run's spend reaches `extraction_max_total_usd` (default 10) or `--max-total-usd`. Calls of unknown cost count at the per-call cap. Pages that were not started are reported. The estimate also prints a worst case: pages × per-call cap × 2, because a retry can double a page's cost. `pilot_max_pages` (default 30) limits the size of `--pages`.
- **Render:** each page is a JPEG (`p{page:03d}.jpg`) at quality 85, stepping down to 45 until the file is at most 3.5 MB. Real pages come out at about 0.65 MB. A zero-size page raises `RenderError`, which the CLI reports as exit 1.
- **Extract hash:** covers the model, prompt version, system prompt, schema, and the sha256 of the page image and of the next-page image. It doesn't cover library versions.
- **Next-page context:** the page after the range is rendered too, so a dry run for 5-7 writes 4 images.
- **PageExtraction:** each draft has `bbox` and `next_page_bbox`, required exactly when `continues_on_next_page`. Images have `on_next_page`. Headings have `y`, the top of the heading on the page. The transformed schema has 10 optional fields and 11 unions, and a test pins these numbers.
- **Validate:** it rebuilds every `build_page_results` row of the book in one transaction.
  - It uses only `done` extractions whose hash equals the page's current hash, computed from the images on disk.
  - Pages that have rows or extractions but no current extraction lose their rows and are reported as stale.
  - The book-level job `{book_id}#book` is the skip check, and the most recent one wins. `VALIDATE_VERSION` and `SCHEMA_VERSION` are both part of the hash.
  - A heading applies from its `y` downwards. A problem whose bbox top is above the heading keeps the previous keys.
  - A heading label that gives no key keeps the previous keys and adds a page warning.
  - Only canonical Roman numerals are accepted.
  - Duplicate suffixes skip ids already taken, shorten the label so it stays a valid 16-character key, and count valid drafts only.
- **Dry-run output:** `data/build/requests/{book_id}/p{page:03d}.json` (`page_ref`, `input_hash`, the full `argv`) plus `p{page:03d}.prompt.txt`.

- **2026-10-01 fix (finding #22):** `_record()` in `builder/calls.py` now commits the `build_costs` rows in their own `engine.begin()` transaction, separate from (and strictly before) a second transaction that writes the `build_jobs` done/failed row. Previously both writes shared one transaction, so a job-row write failure after a successful, paid call rolled back the cost row too, leaving a billed call with no trace and causing the next run to re-extract (and re-spend) from scratch. Finding #23 (transient total-budget overshoot from already in-flight calls) is left as documented, not patched -- see the Review Triage Log row for why. Finding #24 (doc said "9 optional fields", test pins 10) is corrected below.

## Spec Change Log

- 2026-09-27 — Trigger: user instruction "use claude cli instead of anthropic api". Amended (user-owned change, applies over the frozen block): the real client is `ClaudeCliClient` running `claude -p` headless per page instead of `AnthropicBatchClient`/Message Batches. Invocation: `claude -p <user prompt> --output-format json --json-schema <PageExtraction JSON schema> --system-prompt <extraction system prompt> --tools Read --add-dir <pages dir> --no-session-persistence [--model <extraction_model>]`, where the prompt names the page PNG path (and the next-page PNG for context), which the CLI reads with its Read tool. The result comes from the JSON field `structured_output`; errors come from `is_error`/`subtype`/non-zero exit; cost comes from `total_cost_usd` plus `usage`, recorded in `build_costs`. Bounded parallelism (config `extraction_concurrency`, default 3) replaces batching; there is no batch id to poll, and resume relies on the per-page `build_jobs` records only. Timeouts and one retry on a transient failure; after that the page is `failed`. No `ANTHROPIC_API_KEY`: the guard checks that the `claude` executable is on PATH instead. The spend guard stays (`--yes-spend`), and `--max-budget-usd` is passed per call from config. Tests still use `FakeClaudeClient` and never spawn the real CLI (a test may stub the subprocess to check the argv and JSON parsing). Known-bad state avoided: requiring an API key the user doesn't use. KEEP: stages, PageExtraction, validate/carry-forward, job idempotency, dry-run, cost table.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | page_extraction.schema.json missing from diff | false | exists; excluded from review diff |
| 2 | Claims: no Message Batches / AnthropicBatchClient / 4th table / 3 PNGs | false | superseded by the 2026-09-27 Change Log (CLI; next-page context PNG) |
| 3 | Stale build_page_results: failed re-extraction keeps old rows; out-of-range pages use old-hash extractions; hash A→B→A reports stale rows current; neighbours not rewritten | high | stale drafts look current → patch (validate rebuilds the whole book from current-hash done extractions, deleting rows without one) |
| 4 | Validate hash omits SCHEMA_VERSION | medium | schema rule changes skipped → patch |
| 5 | PyMuPDF version in render hash re-bills every page on upgrade | high | money → patch (extract hash uses rendered image content hash; drop lib version) |
| 6 | Cost undercounted: timeouts $0, lost attempt on exception, DB write crash loses in-flight results | medium | cost tracking is intent → patch (cost_unknown flag, keep attempts, per-future write guard) |
| 7 | No total-run budget cap; retries can double per-call cap | high | spend safety → patch (--max-total-usd / config cap checked as costs arrive; estimate states retry worst case) |
| 8 | CLI subprocess runs in repo cwd with user settings/MCP/CLAUDE.md | medium | variance, extra tokens, can read hoctap.toml → patch (temp cwd + isolation flags) |
| 9 | Retry classification: auth/model errors retried; envelope-invalid output never retried | medium | double billing / lost pages → patch |
| 10 | ok=False with error=None recorded as done | medium | page never retried → patch |
| 11 | Non-JSON text around stdout JSON treated as failure | low | paid call lost → patch (parse last JSON line) |
| 12 | Duplicate suffix: collides with real label, exceeds 16 chars, invalid drafts consume numbers | medium | duplicate ids / always-invalid drafts → patch |
| 13 | Unparsable heading resets to u00; non-canonical roman numerals accepted | medium | wrong keys → patch |
| 14 | Ctrl-C waits up to 15 min per in-flight call | low | → patch (cancel + terminate children) |
| 15 | nan/inf floats in config; `:g` budget formatting | low | trivial → patch |
| 16 | pymupdf RuntimeError uncaught; zero-size page ZeroDivisionError | low | → patch |
| 17 | --pages unbounded "pilot" | medium | → patch (config pilot_max_pages, default 30) |
| 18 | Migration downgrade asymmetric | low | trivial → patch |
| 19 | Tests missing: changed model re-extracts; malformed ok output fails page; headings across runs; deleted PNG re-renders; permanent subtype row; [build] config validation + env override | medium | verification gaps → patch |
| 20 | (orchestrator) Page PNGs are 5.2–6.0 MB, above the ~5 MB image limit | high | real call would fail/degrade → patch (JPEG quality 85, verify ≤ 3.5 MB) |
| 21 | (orchestrator) Mid-page heading applies to problems above it | high | wrong lesson keys → patch (headings carry a y position; problems above keep the previous heading) |
| 22 | (2026-10-01, Orchestrator's Independent Audit) `_record()` in `builder/calls.py` writes the `build_costs` row and the `build_jobs` done-status row inside the SAME transaction -- if the job-row write raises after a successful, paid Claude call (disk full, transient lock, constraint violation), the whole transaction rolls back, including the cost row for the attempt that was already billed. The page then has no job row, so the next run re-extracts from scratch and spends again, with zero trace the first attempt was ever paid for | medium | confirmed by 1 reviewer via direct trace; narrower/more severe than the already-resolved #9/#10 above, which assumed cost rows survive independently of the job-row write -> **patched (2026-10-01)**: `_record()` now writes the cost rows in their own `engine.begin()` transaction, committed before a second, separate transaction writes the job-status row; a failure in the second transaction no longer touches the already-committed cost rows |
| 23 | (2026-10-01, Orchestrator's Independent Audit) Total-budget cap (`extraction_max_total_usd`, resolving prior finding #7) only gates new job SUBMISSION -- with `extraction_concurrency=3`, up to ~2 already-in-flight jobs can complete after the cap is crossed, producing a transient overshoot of roughly `(workers-1) × max_budget_usd × 2` (~$4 beyond a $10 default) | low | confirmed by 1 reviewer; never bypasses the `--yes-spend` consent gate itself, a budget-tightness nit not a safety hole -> **deferred (2026-10-01)**: left as documented, per the audit's own "accept and document" option -- tightening it would mean cancelling in-flight, already-dispatched (and potentially already-billed) CLI calls, which trades a bounded, already-documented worst-case margin for a more complex and riskier cancellation path; not worth it at low priority |
| 24 | (2026-10-01, Orchestrator's Independent Audit) Implementation Notes claim "the transformed schema has 9 optional fields and 11 unions, and a test pins these numbers" -- the actual pinned test (`tests/test_extraction.py:240`) asserts `_count(schema) == (10, 11)`, i.e. 10 optional fields, not 9. The guard test itself is real and passing (no functional bug), just a documentation miscount | low | confirmed by 1 reviewer who ran the test directly -> **patched (2026-10-01)**: Implementation Notes corrected to "10 optional fields, 11 unions" |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context -- this epic predates the separately-discovered unsupervised-build incident and had simply never been independently re-audited before being marked `review`). 3 parallel reviewers confirmed every HIGH/MEDIUM prior finding (#4/#5/#7/#12/#14/#20 above) is genuinely fixed in current code, the hard no-real-Claude-API-spend-in-tests rule is respected throughout (every test uses `FakeClaudeClient` or a stubbed `subprocess.Popen`, no real `claude` binary invoked, no `ANTHROPIC_API_KEY` reference anywhere in the suite), and the full backend suite passes (1148/1148, independently run by the reviewer). New findings #22-24 above; #22 is the one worth fixing given it's a real (if narrow) spend-tracking gap, #23/#24 are low-priority polish.

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd backend && uv run hoctap build pilot --book toan1-2020-q1 --pages 5-7 --dry-run` -- expected: PNGs and requests written, estimate printed
