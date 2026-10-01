---
title: 'Story 1.10: Extraction control from the Parent Area'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:b0314c82dc58cbd4c9ebc662d8929a3fc7d64552'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `hoctap build pilot` today only runs synchronously from a terminal, blocking until it finishes and printing to stdout. Anh needs to start, watch and pause it from the Parent Area in a browser (FR-5, AD-7's "builder.jobs is the only control surface").

**Approach:** A `builder.jobs` control module runs the existing pilot pipeline (render → extract → validate → verify → crop → publish) in a background thread inside the FastAPI process, recording its live state in a new `build_runs` table so progress survives a page reload. Parent-guarded API endpoints start, pause/resume and poll it. A "Chạy thử" (trial run) screen in the Parent Area shows progress by page, cost so far, and failed pages, and drives Tạm dừng / Tiếp tục.

## Boundaries & Constraints

**Always:**
- **One run at a time.** Starting a run while one is `running` or `pausing` returns 409 `RUN_IN_PROGRESS`.
- **`build_runs`** (new table): `id` (UUIDv7), `book_id`, `first_page`, `last_page`, `status` (`running`|`pausing`|`paused`|`done`|`failed`|`cancelled`), `stage` (`render`|`extract`|`validate`|`verify`|`crop`|`publish`|null), `pages_total`, `pages_done`, `cost_usd`, `cost_unknown_count`, `failed_pages_json` (list of `{page, reason}`), `error` (nullable text), `started_at`, `updated_at`, `finished_at`.
- **Background execution:** the run executes in a `threading.Thread` owned by an in-process `RunManager` singleton on `app.state`. It uses its own DB connection (never the request's). Progress is written to `build_runs` after each page-level step so a poller sees it.
- **Start** (`POST /build/runs`): body `{book_id, pages: "5-7", yes_spend: bool}`.
  - Validates the book and range exactly as `plan_pilot` does today (reuse it); a validation failure returns 422 with the same messages the CLI gives.
  - Computes the same pre-flight estimate as the CLI and refuses with 402-style `SPEND_NOT_CONFIRMED` (422) unless `yes_spend` is true — mirroring the CLI's `--yes-spend` guard exactly, including the total-budget cap (AD-7, Story 1.9's `run_kind`).
  - Marks new page-level `build_jobs` rows for this range with `run_kind="pilot"` (existing behaviour, unchanged) and creates the `build_runs` row `status="running"`, then starts the thread and returns the row (202).
- **Pause** (`POST /build/runs/{id}/pause`): sets `status="pausing"`. The running thread checks this flag between pages (never mid-page-call) and, when set, stops submitting new pages, finishes collecting any in-flight page's result, writes final state, and sets `status="paused"`. No `build_jobs` row is left half-written.
- **Resume** (`POST /build/runs/{id}/resume`): only valid when `status="paused"`. Starts a **new** run (new `build_runs` row referencing `resumed_from`) over the same `book_id`/range; because completed pages are already `done` in `build_jobs`, no page already finished is redone or repaid (existing idempotency from Stories 1.5–1.7 is the mechanism — this story adds no new dedup logic).
- **Cancel** (`POST /build/runs/{id}/cancel`): like pause but ends in `status="cancelled"`; resuming a cancelled run is allowed the same way as a paused one.
- **Poll** (`GET /build/runs/current` and `GET /build/runs/{id}`): returns the row plus a human-readable current activity line (e.g. "Đang trích xuất trang 6/7"). `GET /build/runs` lists recent runs (paginated, newest first) for history.
- **Errors surfaced, run continues:** a page that fails (extraction refusal, verify failure, crop error) is appended to `failed_pages_json` with its stage and reason; the run proceeds to the next page. The run only becomes `status="failed"` on an unrecoverable error (e.g. the book file went missing, or the DB write itself fails).
- **UI (Vietnamese, Parent Area, reachable from ParentHome):**
  - Pick a Book and a page range (reuse the catalogue list).
  - "Chạy thử" button; disabled with a tooltip while a run is active elsewhere.
  - While running: a progress bar (`pages_done`/`pages_total`), the current stage and page, running cost, and a live list of failed pages with their reason.
  - "Tạm dừng" while running (becomes disabled + "Đang dừng…" while `pausing`); "Tiếp tục" when paused; "Hủy" to cancel.
  - Polls `GET /build/runs/current` every 2s while a run is active; stops polling once `done`/`failed`/`cancelled`/`paused`.
  - On mount, if a run is already active (e.g. after a reload), the screen resumes showing it rather than the picker.

**Never:**
- No multi-run concurrency, no distributed workers, no process-level restart-safety beyond what `build_jobs` idempotency already gives (a hard server crash mid-run leaves the run row `running` forever stale — Deferred: a startup reconciliation pass is out of scope for this story, but the UI must handle a stale `running` row gracefully by showing "Tiếp tục" instead of only "Tạm dừng" when the row is older than 5 minutes with no `updated_at` movement).
- No changes to the extraction pipeline, the go/no-go gate (Story 1.9), or `hoctap build pilot`'s existing CLI behaviour — the CLI keeps working unchanged, run in-process by the same functions the API now also drives.
- Real Claude calls are exactly as today (mocked in tests via `FakeClaudeClient`); no test exercises the real `claude` executable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start ok | valid book/range, yes_spend true | 202, run row `running`, thread started | N/A |
| Start needs confirm | yes_spend false/omitted, cost > 0 | 422 SPEND_NOT_CONFIRMED with the estimate | nothing started |
| Start invalid range | bad book_id or page range | 422 VALIDATION_ERROR (same message as CLI) | nothing started |
| Start while running | another run `running`/`pausing` | 409 RUN_IN_PROGRESS | nothing started |
| Poll during run | run active | 200 with pages_done increasing across polls | N/A |
| Page fails | a fake failure injected mid-run | run continues; page appears in failed_pages_json | N/A |
| Pause | run `running` | status -> `pausing` then `paused`; no new build_jobs submitted after the flag flips | N/A |
| Resume | run `paused` | new run row; already-done pages are not resubmitted (0 new calls for them) | N/A |
| Cancel | run `running` or `paused` | status -> `cancelled` | N/A |
| Poll unknown id | bad run id | 404 RUN_NOT_FOUND | N/A |
| Auth | any endpoint, no parent cookie | 401 | N/A |
| Stale running row | `running`, `updated_at` > 5 min old, no live thread | UI shows "Tiếp tục" affordance instead of only pause | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/pilot.py` -- `plan_pilot`, `pending_pages`, `run_pilot` (the existing synchronous pipeline). Call these from the new run manager; do not duplicate their logic.
- `backend/hoctap/cli.py` `_build_pilot`, `_spend_client`, `_run_build` -- the existing CLI guard and estimate printing to mirror in the API's start validation.
- `backend/hoctap/builder/costs.py` -- `estimate()` for the pre-flight figure.
- `backend/hoctap/api/build.py` -- existing `/build/status`, `/build/gate*` router; add the `/build/runs*` routes here.
- `backend/hoctap/db/alembic/versions/0009_build_jobs_run_kind.py` -- the latest migration; add `0010_build_runs.py` after it.
- `frontend/src/pages/GateCard.tsx`, `frontend/src/pages/ParentHome.tsx` -- the polling and card patterns to follow for the new Extraction screen.
- `frontend/src/api/queries.ts`, `client.ts` -- add the run endpoints; regenerate types with `npm run gen:api`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/builder/jobs.py` (new) -- `RunManager`: `start()`, `pause()`, `cancel()`, `current()`, thread body that drives `run_pilot`'s stages page-by-page with pause checks and progress writes.
- [x] `backend/hoctap/builder/models.py` + `0010_build_runs.py` -- the `build_runs` table.
- [x] `backend/hoctap/api/build.py` -- the run endpoints; wire `RunManager` into `app.state` at startup (`app.py`).
- [x] `backend/tests/test_runs.py` -- every matrix row, using `FakeClaudeClient` and a short injectable page range so tests run fast; use a small polling loop with a timeout to await thread progress rather than fixed sleeps.
- [x] `frontend/src/pages/ExtractionPage.tsx` (+ picker, progress, tests) + route + ParentHome link.
- [x] `frontend/src/api/{client,queries}.ts` -- run endpoints and `useCurrentRun` polling hook.

**Acceptance Criteria:**
- Given a validated book with a small unextracted page range, when Anh starts a trial run from the Extraction screen with the cost accepted, then progress advances to completion, the Content Review counts reflect the new Problems, and reloading the page mid-run shows the same live progress.
- Given a running trial run, when Anh taps Tạm dừng, then no further Claude calls are made and Tiếp tục later finishes the remaining pages with zero calls repeated for pages already done.

## Implementation Notes

- **`build_runs` (migration `0010_build_runs`):** exactly the columns in the frozen spec, plus `resumed_from` (nullable text, the paused/cancelled run a Resume was started from) which the Resume bullet requires but the column list omitted. `stage` and `status` are `CheckConstraint`-enforced to the listed enums.
- **`RunManager` (`backend/hoctap/builder/jobs.py`):** a singleton on `app.state.run_manager`, constructed in `app.create_app()`'s lifespan alongside the engine, with an injectable `client_factory` (tests pass one that returns `FakeClaudeClient`; the default checks `shutil.which` and returns `ClaudeCliClient`, exactly mirroring the CLI's `_spend_client`). `start()`/`resume()` hold a `threading.Lock` while checking for another active run and inserting the new row, so two concurrent starts cannot both pass the `RUN_IN_PROGRESS` check; the background thread itself never holds that lock except briefly to drop its handle when it finishes.
- **One page at a time, not one `run_pilot()` call for the whole range:** the thread body loops over `plan.pages`, building a fresh single-page `PilotPlan` and calling the existing `run_pilot()` (verify and publish included, matching the CLI's default pipeline) once per page. This is what makes "check the pause/cancel flag between pages" a literal, race-free boundary: a flag set while a page's `run_pilot()` call is executing is only observed at the top of the *next* iteration, so the in-flight page's render/extract/verify/crop/publish always finishes and is written before the run stops. Reusing `plan_pilot`/`pending_pages`/`run_pilot` means no extraction logic is duplicated, and the existing `build_jobs` idempotency (keyed by `page_ref, stage, input_hash`) is what makes a resumed page's already-done stages free, exactly as the spec requires ("this story adds no new dedup logic").
- **Cost so far** is the delta of `costs.total_cost(conn, f"{book_id}#p")` between the run's start and each page's completion (not the book's all-time total), so "cost so far" on screen reflects only this run/resume, matching the Extraction screen's intent.
- **Spend guard (`RunManager._spend_client`/`_needs_calls`):** mirrors `hoctap build pilot`'s guard exactly, including deciding "needs a call" from *both* pending extract pages and pending verify pages (a page can be fully extracted already but still need its independent verify call) -- the same condition the CLI computes before asking for `--yes-spend`. `resume()` never re-asks (the original `start` already got consent) but still only requests a client when there is actually pending work, using the same `_needs_calls` check.
- **Stale detection:** `is_stale()` flags a `running` row whose `updated_at` has not moved in 5 minutes; the API returns this as `stale` on every run payload, and `activity_line()` gives the Vietnamese status text ("Đang trích xuất trang 6/7", "Đang dừng…", "Đã tạm dừng", …). No startup reconciliation pass was added (out of scope, as specified). `resume()` accepts a stale `running`/`pausing` row directly (no live thread + `is_stale`): it closes the dead row out as `cancelled` first, then starts a new run over the same range, so the UI's single Tiếp tục click on a stale row (the crash case the spec calls out) works in one step rather than requiring the parent to Hủy it first.
- **`GET /build/books` (new, not in the original file/code map):** the picker needs a book list with `page_count` to validate a range client-side and show it; no such endpoint existed (Content Review's `/parent/review/books` only lists books with published Problems, which is empty before the very first pilot run). Added `list_catalogue_books` to `api/build.py`, thin over `content.catalog.service.list_books()` (read-only, no new writer of `content_catalog_*`).
- **Frontend:** `ExtractionPage.tsx` has a `Picker` (book select + from/to page inputs) and a `Progress` view; `useCurrentRun()` polls `GET /build/runs/current` every 2s via TanStack Query's `refetchInterval`, stopping once `status` is not `running`/`pausing` (including "no run at all", i.e. `null`). A `SPEND_NOT_CONFIRMED` 422 from Start shows the estimate text inline with a "Xác nhận & chạy" button that resubmits with `yes_spend: true`, mirroring GateCard's accept-then-confirm pattern. On mount, an active or just-settled run is shown instead of the picker (per AC); "Chọn sách và trang khác" dismisses a settled run locally to show the picker again for a new run.

### 2026-10-01: Fixed finding #17 (medium) from the orchestrator's audit

`is_stale()` (`backend/hoctap/builder/jobs.py`) only flagged a `running` row as stale, never a
`pausing` one, even though `resume()` already accepted a dead `pausing` row the same way it
accepts a dead `running` one (see the Implementation Notes entry above on stale detection). A
server crash between `POST /pause` flipping the row to `pausing` and the in-flight page's
`run_pilot()` call finishing (writing `paused`) left that row permanently stuck: `ExtractionPage.tsx`
only showed "Tiếp tục" for `paused` or `(running && stale)`, so the parent's only way out was
noticing "Hủy" still worked and starting over (losing the resume UX this story specifically
built for the running-crash case).

- `is_stale()` now also returns true for a `pausing` row whose `updated_at` has not moved in
  5 minutes (`run["status"] not in ("running", "pausing")` instead of `!= "running"`).
- `ExtractionPage.tsx`'s stale note (around the "Tiếp tục" hint) and its "Tiếp tục" button
  condition were both extended from `run.status === 'running' && run.stale` to
  `(run.status === 'running' || run.status === 'pausing') && run.stale`; the "Đang dừng…"
  disabled button now only renders for a `pausing` row that is *not* stale
  (`run.status === 'pausing' && !run.stale`), so a stale `pausing` row shows the actionable
  "Tiếp tục" button instead of a permanently-disabled one.
- Added `test_stale_pausing_row` and `test_resume_on_a_stale_pausing_row` to
  `backend/tests/test_runs.py`, mirroring the existing `test_stale_running_row`/
  `test_resume_on_a_stale_running_row` pair for the `pausing` case.

## Spec Change Log

- 2026-09-28 -- Note (orchestrator, independently re-verified): after the review-fix round, backend re-run in full and independently by the orchestrator: 616/616 tests pass, ruff check clean. npm run build, tsc --noEmit, and npm run lint all clean (type-checked against the real generated API types). Frontend Vitest component tests (including the new ExtractionPage.test.tsx) could NOT be run to completion on this machine across ~8 separate attempts (default pool, forks pool, single-fork, constrained heap) -- worker processes consistently time out starting under severe memory pressure from ~8 unrelated concurrent Claude sessions and other heavy processes sharing this machine (verified via repeated free -h showing <1GB free throughout). One partial run did complete 5 of ~11 test files (52/55 tests passing, 0 failures) before the remaining files hit the same worker-start timeout, consistent with resource starvation rather than a code defect. Same class of environment issue recorded in Story 1.9's Change Log. Owner should run `cd frontend && npm run test -- --run` once machine memory is free, particularly src/pages/ExtractionPage.test.tsx, before relying on this story's frontend interaction behaviour beyond what type-checking and manual review confirm.

- 2026-09-28 — Addition (implementer): added `resumed_from` to `build_runs` (required by the Resume bullet's own text, missing from the column list) and a `GET /build/books` catalogue-listing endpoint (required for the Picker to have anything to pick from; no prior endpoint listed the catalogue with page counts). Both are additive, no frozen behaviour changed.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `stage` never set beyond "extract"; render/validate/verify/crop/publish never surfaced | high | confirmed in code (jobs.py only sets stage="extract"/None); breaks spec's promised fine-grained progress → patch: run_pilot's per-page pipeline must report its current sub-stage back to RunManager via a callback, or jobs.py must call the sub-stage functions directly instead of run_pilot() as one call |
| 2 | `_request_stop` (pause/cancel) mutates `_handles` and calls `_set`/`_finish` without `self._lock`, racing `start`/`resume` | high | confirmed at jobs.py:312 vs :144/243/265 → patch: acquire `self._lock` in `_request_stop` |
| 3 | `GET /build/books` has no real TestClient test (only frontend-mocked) | medium | → patch: add a test seeding the catalogue and hitting the real route |
| 4 | `activity_line`'s Vietnamese text never asserted against real API output | medium | → patch: assert `body["activity"]` in a couple of test_runs.py cases |
| 5 | `current()` has no time cutoff; an old settled run can hide the picker indefinitely | low | → patch: only auto-show a settled run if updated_at is within e.g. 24h, else default to picker |
| 6 | Picker has no client-side page-range validation (min/max) | low | → patch: add `min={first}` on "Đến trang" |
| 7 | progressbar missing aria-valuemin/valuemax; no aria-live region | low | → patch |
| 8 | `GET /build/runs` limit has no upper bound | low | → patch: `Query(20, ge=1, le=100)` |
| 9 | local import of list_books inside function; CatalogueBookOut duplicates catalog service fields | low | reject (minor style, not worth the churn) |
| 10 | migration downgrade untested | low | → patch: add to existing migration up/down test pattern |
| 11 | build_runs.book_id has no FK to catalogue books | low | reject (SQLite FK enforcement is off by default in this codebase's other tables too; consistent with existing pattern) |
| 12 | "Đang dừng…" gives no hint pause can take a while with a real client | low | → patch: tooltip/caption text |
| 13 | resume() rejects a 'failed' run; only paused/cancelled/stale-active resumable | low | reject — spec says "only valid when status=paused"; failed is intentionally terminal, resuming a failed run is out of scope here |
| 14 | resume()'s stale-check requires `is_stale()` in addition to handle-less, inconsistent with `_request_stop`'s handle-less-only check | medium | → patch: align resume()'s dead-handle check with _request_stop's (handle-less is enough, drop the additional is_stale time requirement) |
| 15 | "one run at a time" enforced only in-process, no DB constraint, no multi-instance test | low | defer (single-instance deployment per architecture; out of scope for this story) |
| 16 | `GET /build/runs` (list) has no consumer in the frontend and no 200-path test | low | → patch: add a 200-path test at minimum since the route is public API surface now |
| 17 | (2026-10-01, Orchestrator's Independent Audit) `is_stale()` only flags staleness for `status == "running"` -- a server crash between `POST /pause` flipping a row to `pausing` and the in-flight page's `run_pilot()` call finishing and writing `paused` is just as plausible as a crash during `running`, but lands in a status `is_stale()` never checks. `ExtractionPage.tsx` only shows "Tiếp tục" for `paused` or `(running && stale)`, never for a stale `pausing` row -- the row is stuck forever, the UI shows a permanently-disabled "Đang dừng…" button, and the only recovery is noticing "Hủy" still works and starting a fresh run (losing the one-click "zero pages repeated" resume UX this story specifically designed in for the running-crash case). The backend's `resume()` already accepts a dead `pausing` row the same way it accepts a dead `running` one -- the frontend just never offers it for this one status | medium | confirmed by 1 reviewer via direct trace; sits right next to the already-fixed #14 (resume/`_request_stop` staleness alignment) -- this is the one case that patch didn't close -> patch: extend `is_stale()` to also flag a stale `pausing` row, and have `ExtractionPage.tsx` show "Tiếp tục" for it too -> **patched (2026-10-01)**: `is_stale()` now flags a stale `pausing` row too, and `ExtractionPage.tsx` shows "Tiếp tục" (and the stale note) for a stale `pausing` row the same as for a stale `running` row; the "Đang dừng…" disabled button now only shows while `pausing` and not stale |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context). 3 parallel reviewers confirmed no accidental-spend path exists (frontend requires a genuine two-step confirm before `yes_spend: true` is ever sent; `start()`/`start_full()` both hard-refuse with 422 without it), confirmed the prior HIGH findings (#1 stage-reporting, #2 `_request_stop` lock race) are genuinely landed in code, and confirmed cost-shown-so-far is correctly a delta against the run's own baseline (can't under-report by mixing in unrelated prior spend). One new finding (#17, medium) above -- a real UX gap in crash-recovery for the `pausing` state specifically.

## Verification

**Commands run:**
- `cd backend && uv run pytest -q` -- 610 passed (609 + the one fixed below). One pre-existing test failed on the first run and was fixed as part of this story: `test_app.py::test_fresh_data_dir_created_with_wal_and_migrations` hardcoded the latest Alembic head (`0009_build_jobs_run_kind`) and the full table set; updated to `0010_build_runs` and added `build_runs` to the expected table set. Re-run of `tests/test_app.py` alone confirms the fix (see note below on machine load).
- `cd backend && uv run ruff check .` -- all checks passed; `uv run ruff format` applied to the new/changed files.
- `cd frontend && npm run gen:api` (via `uv run hoctap export-openapi` first, since no server was running) -- `RunOut`, `CatalogueBookOut`, `FailedPage`, `RunStartIn` etc. generated into `schema.d.ts` as expected.
- `cd frontend && npm run build` -- `tsc -b && vite build` succeeded, no type errors.
- `cd frontend && npm run lint` -- clean.
- `cd frontend && npm run test -- --run src/pages/ExtractionPage.test.tsx` -- **could not be run to completion**: the Vitest fork worker repeatedly failed to start (`Timeout waiting for worker to respond`) under severe memory pressure from unrelated, concurrent processes on this shared machine (`free -h` showed under 250Mi free and 3-4Gi of swap in use throughout, from other unrelated sessions/services, not from this work) -- the same class of environment issue already recorded in Story 1.9's Spec Change Log, not a code issue. The backend's own `test_runs.py` (13/13 passed) exercises the same run lifecycle the frontend calls, and `npm run build`'s type-check passed against the real generated types, so the API contract the page relies on is verified; only the component-level rendering/interaction tests in `ExtractionPage.test.tsx` are unconfirmed by an actual run. Owner should run `cd frontend && npm run test -- --run` once machine memory is free.

**Expected vs actual:** all pass except the one noted frontend-test-run gap (environment-caused, tracked above), consistent with the Verification section's own caveat ("verify machine has available memory before relying on a red result").
