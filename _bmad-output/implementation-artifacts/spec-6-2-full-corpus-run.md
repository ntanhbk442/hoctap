---
title: 'Story 6.2: Full corpus run'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: '9587b3f4e0ef7171a1a8f4eed29187cb2e97655f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `hoctap build full` only checks the go/no-go approval, then prints "not implemented" (`cli.py::_build_full`). The pilot machinery (`run_pilot`, `RunManager`) is capped at `pilot_max_pages` (30) per run, tags every job `run_kind='pilot'` (`CallJob` default), and has no whole-corpus plan, cap, per-Book checkpoint or quality stop. The corpus is 30 Books, 2,140 pages (grade 1: 433, grade 2: 600, grade 3: 449, grade 4: 316, grade 5: 342).

**Approach:** Add a `full` run: an ordered plan of Books, each processed through the existing resumable stages (render, extract, validate, verify, crop, publish) with `run_kind='full'`, gated by `gate.require_approval()`, spend-guarded (`--yes-spend`, an explicit overall cap), reporting cost, progress and a failed-page list, and stopping at Book checkpoints. CLI first; a Parent Area "Chạy toàn bộ" control on the existing extraction page reuses the same manager. **Implementing this story does NOT run the corpus.** Running it for real is a separate, explicitly human-approved operation by Anh. No test may call the real Claude CLI or spend money; all tests use `FakeClaudeClient`.

## Boundaries & Constraints

**Always:**
- Refuse to start unless `gate.require_approval()` passes (`GATE_NOT_APPROVED`, CLI exit 3), and re-check it before each Book. Spending needs `--yes-spend` (or `yes_spend` in the API) plus an explicit overall cap `--max-total-usd`; without either, print the pre-flight estimate and exit 2 with nothing sent. `--dry-run` writes requests only.
- Reuse the stages, `build_jobs` idempotency (skip `done` for the same input hash) and `calls.run_calls` cap; no new dedup. Thread `run_kind` through `stages/extract.py` and `stages/verify.py` `CallJob`s. Killed then restarted: no completed page is called again.
- The overall cap spans all Books: remaining budget is passed as each Book's `max_total_usd`; unknown-cost calls count at the per-call cap. A cap hit finishes the in-flight pages, records the run as stopped (`budget`), lists unstarted Books/pages and is resumable.
- Fix `gate._cost()`: today it sums every call on any page that ever had a pilot job, so a full-run re-extraction of a pilot page (its hash changed with prompt p3) raises `pilot_cost`, changes `est_cost` and silently revokes the approval mid-run. Count only calls whose (`page_ref`, `stage`, `input_hash`) match a `run_kind='pilot'` job. Pilot scope stays `pilot_refs()`, so approval stays valid while the full run proceeds.
- Report per Book and in total: pages done/failed, cost so far vs estimate, Problems, `fallback` share, verify disagreements, and a failed-page list (page, stage, reason). After the run, print the interactive share (Problems without a `fallback` Part, target at least 95%) and point to "Kiểm tra ngẫu nhiên" (`content/review/spotcheck.py`) for the 100-Problem check (target 98% Answer Keys correct). The run never marks itself "accepted".
- Order: sorted by (grade, edition, volume) unless `--books` / `--grade` narrows it. One run at a time, shared with the pilot run lock.
- Failed pages never abort the run: they are listed, and retried by the next `full` invocation (same idempotent path).

**Human decisions (Anh, 2026-09-30):** (1) Spend cap: an explicit `--max-total-usd` is REQUIRED on every full run (and an explicit cap field in the Parent Area card); there is no default and no config ceiling substituting for it, so nothing spends without a number Anh chose. (2) Order: ascending grade (1 to 5), all Editions, Books in (grade, edition, volume) order. (3) Checkpoints and quality guard: the run pauses for a human "Tiếp tục" after each grade for grades 1 and 2 (already piloted); for grades 3, 4 and 5 (never piloted) the FIRST Book of each grade runs as a small pilot-scale run, then the run stops until the gate is re-reviewed and re-approved for that grade, before the rest of the grade continues (no automatic disagreement-rate stop). (4) The story stays one story. Implementing it never runs the corpus: a real run is a separate operation Anh starts and approves.

**Never:**
- No real Claude, TTS or network call in any test; no `--yes-spend` in any test without `FakeClaudeClient`.
- No automatic `speak-missing`, guide generation or gate approval/revoke as part of the run.
- No new Problem Types, prompt changes, or edits to `build_gate` semantics beyond the `_cost` fix.
- No auto-retry loops beyond `calls.MAX_ATTEMPTS`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No approval | `build full --yes-spend --max-total-usd 50` | exit 3, nothing sent | `GATE_NOT_APPROVED` message |
| No spend flag | approved, no `--yes-spend` | prints per-Book plan, pages to call and estimate, exit 2 | `SPEND_NOT_CONFIRMED` |
| No cap | `--yes-spend` without `--max-total-usd` | exit 2 | "cần đặt --max-total-usd" |
| Happy path | approved, Fake client, 2 Books | stages run, jobs `run_kind=full`, report with cost and failures | N/A |
| Restart | killed after 3 pages, rerun | those pages not called again (Fake call count) | N/A |
| Cap hit | cap below remaining estimate | in-flight pages finish, run status `stopped_budget`, unstarted Books listed | exit 4, resumable |
| Failed page | Fake returns refusal on one page | listed with reason, other pages continue, retried on rerun | exit 1 |
| Approval invalidated mid-run | new pilot page or revoke between Books | run stops before the next Book | `GATE_NOT_APPROVED` |
| Pilot page re-extracted | full run, changed hash | `gate.report().approved` stays true; `est_cost` unchanged | N/A |
| Source changed | Book fingerprint differs from catalogue | that Book skipped and listed | "chạy lại build catalogue" |
| Concurrent run | pilot or full already running | 409 `RUN_IN_PROGRESS` | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/full.py` -- new: `plan_full()` (Books, per-Book pending pages, estimate), `run_full()` (Book loop, cap, checkpoints, report)
- `backend/hoctap/builder/pilot.py` -- `run_pilot` gains `run_kind`; new `plan_book()` without the `pilot_max_pages` limit
- `backend/hoctap/builder/stages/{extract,verify}.py`, `calls.py` -- pass `run_kind` to `CallJob`
- `backend/hoctap/builder/gate.py` -- `_cost()` counts pilot-kind calls only; `require_approval()` reused per Book
- `backend/hoctap/builder/jobs.py`, `models.py` -- `RunManager` full-run mode (one build_runs row per Book with run kind and overall cap); Alembic `0019_full_run` (from head `0018_concept_guides`)
- `backend/hoctap/api/build.py` -- `POST /build/full` (plan, estimate, start), reuse pause/resume/cancel and `runs/current`
- `backend/hoctap/cli.py` -- real `_build_full` with `--yes-spend`, `--max-total-usd`, `--dry-run`, `--grade`, `--books`
- `frontend/src/pages/ExtractionPage.tsx` -- "Chạy toàn bộ" card: plan table, estimate vs cap, confirm, live per-Book progress, failures; `frontend/src/api/schema.d.ts` regenerated
- `backend/tests/test_full_run.py`, `test_gate.py`, `test_cli.py`; `ExtractionPage.test.tsx`

## Tasks & Acceptance

**Execution:**
- [x] `builder/full.py` plan and Book loop with cap, per-Book gate re-check, stop reasons, report
- [x] Thread `run_kind='full'`; unlimited-range `plan_book`
- [x] Fix `gate._cost` and add the regression test
- [x] CLI `build full` and exit codes (2 usage/spend, 3 gate, 4 budget stop, 1 failures)
- [x] Migration `0019_full_run` and `RunManager` full mode; API and Parent Area card
- [x] Tests with `FakeClaudeClient` only

**Acceptance Criteria:**
- Given an approved `build_gate` and `--yes-spend --max-total-usd N`, when `build full` runs against the Fake client, then Books are processed in order, jobs are `run_kind='full'`, and cost, progress and failures are printed and stored.
- Given no valid approval, nothing is sent and the exit code is 3.
- Given a restart, no page with a `done` job for the current hash is called again.
- Given a cap hit or gate invalidation, the run stops between pages or Books and resumes cleanly.
- Given a full run finishes, the report shows the interactive share and a link to "Kiểm tra ngẫu nhiên".
- No test invokes the real Claude CLI.

## Verification

- `cd backend && uv run pytest tests/test_full_run.py tests/test_gate.py tests/test_cli.py -q`
- `cd backend && uv run pytest -q && uv run ruff check . && uv run mypy hoctap`
- `cd frontend && npm run gen:api && npm run typecheck && npx vitest run src/pages/ExtractionPage.test.tsx`

## Implementation Notes

- (2026-09-30) **The corpus was NOT run and no money was spent.** Implementing this story only adds the machinery; a real run is a separate, human-approved operation Anh starts with an explicit `--max-total-usd` (or the Parent Area card's required cap field). Every test uses `FakeClaudeClient` and temp data dirs; a read-only check of the real database after the work showed zero recorded costs and no change to it.
- `builder/full.py`: `plan_full()` (writes and calls nothing) orders Books by grade, edition, volume; `run_full()` re-checks the approval before each Book, shares one overall cap across Books, finishes in-flight pages on a cap hit and lists failed pages and unstarted work. Grades 1 and 2 stop after each grade for a human "Tiếp tục" (run again); for grades 3 to 5 the first Book of the grade runs as a small pilot-scale probe (`pilot` jobs), which voids the approval until it is re-approved, before the rest of the grade continues. Migration `0019_full_run` adds columns and three `stopped_*` statuses to `build_runs` (no new tables).
- `gate._cost()` fix: it now counts only calls that match a `pilot` job by (page, stage, input hash), so re-extracting pilot pages under the new prompt version (Story 6.1) can no longer change the estimate or silently void the approval mid-run; regression test added.
- CLI `hoctap build full [--dry-run] [--yes-spend] --max-total-usd N [--grade G] [--books ...]`: exit 2 without the spend flag or the cap, 3 without approval, 4 on a cap stop, 1 on failed pages or an error, 130 on interrupt, 0 on done or a checkpoint stop. `--dry-run` writes request files but sends nothing. API: `POST /build/full/plan`, `POST /build/full`, `GET /build/full/current`; pause, resume and cancel reuse the run endpoints; a "Chạy toàn bộ" card on the extraction page.
- Found in review and fixed: a run's overall status was copied from its latest per-Book row, so between two Books it wrongly read "done" while the run was still going (worst when a pause landed on a Book boundary; it made `test_api_pause_and_resume` fail intermittently). `RunManager.current_full()` now reports "running" while the run's thread is alive; deterministic regression test `test_full_current_is_running_between_books`.
- Known limits: each run has its own cap (after a cap stop you start a new run with a new cap; only pause and resume carry earlier spend forward); a pause requested exactly between two Books is not recorded; a CLI process killed with `kill -9` leaves a `running` row that the next CLI run closes as `cancelled` after 5 minutes; the Parent Area runs one page at a time so pause takes effect between pages. The 3 `ExtractionPage` test failures and 38 `mypy` errors are pre-existing, in code this story did not change.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_full_run.py tests/test_gate.py tests/test_runs.py tests/test_extraction.py tests/test_verify.py tests/test_publish.py tests/test_app.py tests/test_review.py tests/test_guides.py tests/test_sessions.py` — 542 passed and 1 failed (the between-Books race above); after the fix, `tests/test_full_run.py tests/test_runs.py tests/test_gate.py` — 100 passed. The implementing agent reported the full backend suite at 1069 passed. Regenerated OpenAPI file and types are unchanged.
- Frontend `tsc -b` and `eslint .` clean; `src/pages` with `--pool=vmThreads`: 248 passed, 4 failed — the same three known `ExtractionPage` failures and `ProblemPlayer.speaker.test.tsx` (needs `--pool=threads`); `speech.test.ts` and `ProblemPlayer.speaker.test.tsx` pass with `--pool=threads` (31 tests).
- Not checked: the "Chạy toàn bộ" card in a real browser; the full run against real Claude or real Books.
