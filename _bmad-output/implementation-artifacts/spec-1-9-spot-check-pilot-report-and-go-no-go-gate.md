---
title: 'Story 1.9: Spot-check, pilot report and go/no-go gate'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'tree:196c9323e4c55c6b27f21c6f6d9f9ec8080bbced'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Before money is spent on all 30 books, Anh must see the pilot's real quality and cost, and explicitly approve or stop the full run. Nothing may run the full corpus without that approval (FR-5, AD-7).

**Approach:**
- **Spot-check:** a Kiểm tra ngẫu nhiên (random spot-check) tab draws a stratified random sample of published pilot Problems. Anh marks each Answer Key Đúng or Sai (right or wrong), and the verdicts are stored by `content.review`.
- **Gate report:** a pilot report computes three things — `fallback_share`, `key_accuracy` and `est_cost` — and checks them against the thresholds.
- **Approval:** a `build_gate` record holds Anh's approval.
- **Guard:** every full-corpus entry point refuses to run without a current approval, returning `GATE_NOT_APPROVED`.

## Boundaries & Constraints

**Always:**
- **Pilot scope:**
  - The pilot scope is the set of page references that went through extraction before any gate approval. These are the extract `build_jobs` marked done, across books.
  - `pilot_pages` = the count of those pages.
  - Metrics count only published, non-retired Problems whose first page is in pilot scope.
- **Metrics:**
  - `fallback_share` = pilot Problems with any `fallback` Part ÷ pilot Problems.
  - `key_accuracy` = Đúng ÷ (Đúng + Sai) over the current sample's verdicts. A verdict counts only if the Problem's effective hash has not changed since it was given; stale verdicts are shown as "cần kiểm tra lại" (needs re-checking) and are not counted.
  - `pilot_cost` = the sum of `build_costs` for pilot-scope page references. Unknown-cost calls count at the per-call cap and are shown separately.
  - `est_cost` = (pilot_cost ÷ pilot_pages) × (total catalogue pages − pilot_pages). Both the extraction and verification cost are included.
- **Thresholds:** they come from config, as `gate_max_fallback_share` (default 0.15), `gate_min_key_accuracy` (default 0.98) and `gate_min_sample` (default 30).
  - A check passes when the value meets its threshold.
  - The accuracy check also needs at least `gate_min_sample` verdicts, otherwise it shows "chưa đủ mẫu" (not enough samples) and fails.
  - Cost is not threshold-checked; Anh accepts it explicitly.
- **Sample:**
  - The sample is drawn once: stratified across Problem Types in proportion to their counts, with at least 1 per type present, and `gate_min_sample` in size (or all pilot Problems if there are fewer).
  - The seed is stored, and the sample is kept in `content_review_spot_checks` (`sample_id`, `problem_id`, `position`, `verdict` null|correct|wrong, `verdict_hash`, `note`, `checked_at`).
  - "Rút mẫu mới" (draw a new sample) creates a new sample, and the old one is kept for history. Only the latest sample counts.
  - Only visible-or-reviewable Problems are sampled: not retired and not hidden. Problems still awaiting review can be sampled.
- **Spot-check screen:** the tab shows one Problem at a time with its crop, its effective answer (read-only, human-readable per type), the hint and the solution. The buttons are Đúng, Sai with an optional note, and "Sửa" (open the editor, from Story 1.8). Progress shows as "12/30". A Sai verdict also adds the Problem to Cần duyệt (the review queue) as an open `parent`-kind note, not an Error Report. Correcting the Problem changes its hash, so the verdict needs re-checking.
- **Gate report:** available on the API as `GET /api/v1/build/gate` (parent-guarded) and in the CLI as `hoctap build gate`. It shows the three checks with pass/fail, the numbers behind them, the unknown-cost count and the per-book pilot page counts.
- **Approval:** `POST /api/v1/build/gate/approve` with `{accept_cost: true, est_cost_seen}`.
  - It is refused unless both checks pass and `est_cost_seen` equals the current estimate to the cent (so a changed estimate must be seen again).
  - It stores `build_gate` (`id`, `approved_at`, `metrics_json`, `thresholds_json`, `est_cost`, `sample_id`).
  - The latest approval is valid while the pilot scope, the sample and the thresholds are unchanged. A new pilot page, a new sample or a changed threshold invalidates it.
  - `POST /api/v1/build/gate/revoke` withdraws it.
- **Guard:** `builder.gate.require_approval(engine, settings)` raises `GateNotApproved`. `hoctap build full` exists but only checks the gate and then prints "chưa triển khai (Story 6.2)" (not yet implemented), exiting 2 if there is no approval. The API gets the same guard later. `build pilot` never needs approval, but once an approval exists it warns that new pilot pages will invalidate it.
- **UI:** a new "Chạy thử & đánh giá" (trial run and evaluation) section on ParentHome shows the gate report card with green or red checks, the cost figures, a "Tôi chấp nhận chi phí ước tính …" (I accept the estimated cost) checkbox, and a Duyệt chạy toàn bộ (approve the full run) button. The button is enabled only when both checks pass and the checkbox is ticked. There is also a revoke link.

**Never:**
- No full-corpus extraction itself (Story 6.2). No extraction control UI (Story 1.10).
- Spot-check verdicts never modify content or approvals. They are evidence only.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No pilot | nothing extracted | gate report shows "chưa chạy thử"; approve refused | 409 NO_PILOT |
| Draw sample | 40 pilot problems, 5 types | 30 sampled, each type ≥1, proportional; seed stored | N/A |
| Few problems | 12 pilot problems | all 12 sampled; accuracy shows "chưa đủ mẫu" (12 < 30) | N/A |
| Mark verdicts | 29 Đúng, 1 Sai | accuracy 96.7% → fail (< 98%) | N/A |
| All correct | 30 Đúng | accuracy 100% pass | N/A |
| Stale verdict | a sampled problem edited after Đúng | verdict shown "cần kiểm tra lại", not counted | N/A |
| Fallback | 7 of 40 with fallback parts | 17.5% → fail | N/A |
| Cost | pilot $3.20 over 16 pages, 2,140 total | est $424.80 shown; unknown-cost count shown | N/A |
| Approve | both pass, accept_cost, matching est | build_gate stored; report shows "Đã duyệt" | N/A |
| Approve failing | a check fails | 409 GATE_CHECKS_FAILED | N/A |
| Approve stale est | est_cost_seen ≠ current | 409 ESTIMATE_CHANGED | N/A |
| Invalidation | approved, then a new pilot page is extracted | approval no longer valid | N/A |
| Full guard | `hoctap build full` without approval | exit 2 GATE_NOT_APPROVED | N/A |
| Full with approval | valid approval | prints "chưa triển khai (Story 6.2)", exit 0 | N/A |
| Auth | gate endpoints without parent cookie | 401 | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/costs.py` -- `total_cost(conn, ref_prefix)` and `record_call`. Extend it to sum over a set of page references and count unknown-cost calls.
- `backend/hoctap/builder/jobs_store.py` + `builder/models.py` -- `build_jobs` (stage, page_ref, status) and `build_costs`. Define the pilot scope from these.
- `backend/hoctap/content/effective.py` -- `load_effective` / `effective_problem` for the effective hash and the answer shown.
- `backend/hoctap/content/review/{models,service}.py` -- add the spot-check tables and services. `content_review_*` belongs to `content.review` (AD-2).
- `backend/hoctap/content/catalog/*` -- the published Problems and book page counts.
- `backend/hoctap/api/build.py` -- the existing `build/status` stub, parent-guarded. Add the gate routes. Add spot-check routes in `api/review.py`.
- `backend/hoctap/cli.py` -- the `build` group. Add `gate` and `full`.
- `backend/hoctap/config.py` -- the `[build]` table. Add the three gate keys.
- `frontend/src/pages/review/ReviewPage.tsx` (the tabs) + `ProblemEditor.tsx` (the Sửa link) + `ParentHome.tsx`. Regenerate the API types.
- Migrations: the latest is `0007_review_tables`. Add `0008_gate_and_spot_checks`.

## Tasks & Acceptance

**Execution:**
- [x] `builder/gate.py` -- scope, metrics, report, approval validity, `require_approval`.
- [x] `content/review/spotcheck.py` (+ models) -- sample draw (stratified, seeded), verdicts, stale detection.
- [x] `0008_gate_and_spot_checks.py` -- `build_gate`, `content_review_spot_check_samples` and `content_review_spot_checks`.
- [x] `api/build.py` (gate, approve, revoke) + `api/review.py` (spot-check routes).
- [x] `cli.py` -- `build gate` and `build full` (guard only).
- [x] `backend/tests/test_gate.py` -- every matrix row.
- [x] `frontend/src/pages/review/SpotCheckTab.tsx`, `frontend/src/pages/GateCard.tsx` + wiring + tests (verdict flow, stale label, approve disabled until checks pass and checkbox ticked).

**Acceptance Criteria:**
- Given a fake-client pilot with 30+ published Problems, when Anh marks the sample all Đúng and accepts the cost, then `build_gate` is stored and `hoctap build full` passes the guard. Extracting one more pilot page makes the guard refuse again.

## Implementation Notes

Current behaviour, after the review patches (see the Spec Change Log for why it differs from the frozen text above).

- **Pilot scope (`gate.pilot_refs`):** every page ref with a `done` extract job whose `build_jobs.run_kind` is `pilot` (migration `0009_build_jobs_run_kind`; `pilot` is the default and existing rows became pilot rows). `jobs_store.record(..., run_kind=)` sets the kind on insert only; the full run (Story 6.2) must pass `full`, so its pages never enter the scope and never invalidate its own approval. `pilot_pages` is the count; `scope_hash` = sha256 of the sorted refs.
- **Pilot Problems:** published, non-retired, non-hidden Problems whose first page ref is in scope (see the 2026-10-01 note below: a Problem hidden before a sample is drawn is excluded here too, the same as it already was from the spot-check sample itself).
- **Fallback share:** Problems with any `fallback` Part (not only the first) in the effective doc, or the extracted doc when the merge is invalid, ÷ pilot Problems.
- **Sample (`gate.draw_sample` → `spotcheck.draw_sample`):** size `gate_min_sample + 5` (`DRAW_MARGIN`), or every eligible Problem when there are fewer. Eligible = not retired, not hidden, no `fallback` Part; Problems awaiting review can be drawn. It is stratified by the first Part's type: each present type gets 1, the rest is split in proportion to (count − 1) by largest remainder (`spotcheck.allocate`). The seed and the current `scope_hash` are stored on the sample. Only the latest sample (by UUIDv7 `sample_id`, not by timestamp) counts; old samples are kept and refuse verdicts. With no candidate it returns 409 NO_PILOT, and with no eligible one 409 NOTHING_TO_SAMPLE.
- **Not enough Problems:** the report carries `eligible_problems` and `enough_problems` (eligible ≥ `gate_min_sample`). When there are too few, the CLI and the GateCard say "Chưa đủ bài để đánh giá — hãy chạy thử thêm trang."
- **Key accuracy (first-wrong rule):** the spot-check measures extraction accuracy. The first Sai sets `first_wrong_at`, which is never cleared, so the item counts as wrong for good, even after the Problem is fixed and re-marked Đúng. A Đúng counts only while the Problem's effective hash equals `verdict_hash`; otherwise it is stale ("cần kiểm tra lại"), and a retired Problem's Đúng is stale too. Stale items leave both sides of Đúng ÷ (Đúng + Sai). The check passes when counted verdicts ≥ `gate_min_sample`, the value ≥ `gate_min_key_accuracy`, and the sample is not outdated.
- **Sample outdated:** a latest sample whose `scope_hash` differs from the current scope (new pilot pages were extracted after it was drawn). The report sets `accuracy.sample_outdated`, the accuracy check fails, the CLI and GateCard say "… cần rút mẫu mới", and approve returns 409 SAMPLE_OUTDATED.
- **Verdict API:** `PUT /parent/review/spot-check/{sample_id}/items/{problem_id}` with `{verdict, note, content_hash}`. It returns 409 SAMPLE_OUTDATED for a sample that is not the latest, 404 NOT_IN_SAMPLE, 409 PROBLEM_RETIRED, 409 INVALID_EFFECTIVE (the merged doc is invalid, so there is no hash) and 409 STALE (a different current hash). A Sai opens a `parent`-kind note prefixed "Kiểm tra ngẫu nhiên: đáp án sai." (so the Problem is in Cần duyệt and hidden from the child until resolved), unless the previous verdict was already Sai for the same hash. Verdicts never change content or approvals.
- **Pilot cost:** the reported `cost_usd` of every `build_costs` row (extract and verify, every attempt) whose page ref has any `pilot`-kind job of any stage or status. This includes failed pages, and pages whose extract call was cut off (they have a render job). Calls on `full`-only pages or pages with no job are not counted. Each unknown-cost call adds `extraction_max_budget_usd`. `per_page` = pilot_cost ÷ `pilot_pages` (done extract pages only). `est_cost` = round(per_page × (Σ `content_catalog_books.page_count` − pilot_pages), 2).
- **Approve (`POST /build/gate/approve`):** the body `ApproveIn` forbids unknown fields and takes `est_cost_seen` ≥ 0 with no NaN or Infinity; a bad body gets 422 VALIDATION_ERROR and stores nothing. The checks run in order: 409 NO_PILOT, 422 COST_NOT_ACCEPTED, 409 SAMPLE_OUTDATED, 409 GATE_CHECKS_FAILED (a check fails, or there is no sample or estimate), then 409 ESTIMATE_CHANGED (`est_cost_seen` ≠ current to the cent). The `build_gate` row stores `metrics_json` (with the pilot refs), `thresholds_json`, `est_cost`, `sample_id`, `scope_hash` and `revoked_at`.
- **Approval validity:** the latest `build_gate` row (by UUIDv7 id) is valid only while all of these hold:
  - it is not revoked;
  - `scope_hash` is unchanged (no new pilot page);
  - its `sample_id` is still the latest sample, and that sample is not outdated;
  - the thresholds are unchanged;
  - both checks still pass (a later Sai, or an edit that makes a Đúng stale and drops the counted verdicts below `gate_min_sample`, invalidates it);
  - `est_cost` is unchanged to the cent (a new cost row that moves the estimate by ≥ $0.01 invalidates it).

  `invalid_reasons` lists each failed condition in Vietnamese. A revoked latest row shows no approval at all. Revoke is idempotent.
- **Guard:** `gate.require_approval(engine, settings)` raises `GateNotApproved` (409 GATE_NOT_APPROVED, with the invalid reasons). `hoctap build full` prints `GATE_NOT_APPROVED: …` on stderr and exits **3** (`cli.EXIT_GATE_NOT_APPROVED`; 2 is argparse's usage error). With a valid approval it prints "chưa triển khai (Story 6.2)" and exits 0. `build pilot` warns on stderr only when a valid approval exists and the requested pages are outside the current scope (`gate.new_pages_would_invalidate`).
- **CLI report:** `hoctap build gate` prints each check as `[ĐẠT / PASS]` or `[KHÔNG ĐẠT / FAIL]` with its numbers, then the stale count, the sample-outdated and not-enough-Problems guidance, "Chưa rút mẫu kiểm tra" when there is no sample, the cost with the unknown-cost calls, and the approval state. It exits 0.
- **GateCard:** approve is enabled only when both checks pass, an estimate exists and the checkbox is ticked. The tick belongs to the estimate it was given for: any refetch showing a different `est_cost` unticks it. A 409 on approve (for example ESTIMATE_CHANGED) unticks it and refetches the report, so the new amount is shown. The card also shows the sample-outdated and "chạy thử thêm trang" notes.
- **Spot-check tab:** it shows one item at a time with every crop and the effective answer, hint and solution. For image_select, spot_difference and connect_dots, `AnswerOverlay` draws the regions (selected ones highlighted), the differences on the right image, or the numbered dots and their path on the Part's own crop. It uses `overlayGeometry.cropUrlByImageKey`, which mirrors the backend crop order. A 409 STALE verdict refetches the Problem and the spot-check. "Sửa" opens `/parent/review/problems/{id}?from=spot-check`, whose back link goes to `/parent/review?tab=spot-check`; saving in the editor refetches the spot-check and the gate report.
- **Tables:** `content_review_spot_check_samples` (`sample_id`, `seed`, `size`, `scope_hash`, `created_at`) and `content_review_spot_checks` (+ `first_wrong_at`; a foreign key to its sample, none to the Problem).

### 2026-10-01: Fixed finding #18 (low-medium) from the orchestrator's audit

`spotcheck.eligible()` already excludes any `hidden` Problem from ever being drawn into the
accuracy sample, but `gate.pilot_problem_ids()` (and therefore `fallback_share`'s
numerator/denominator and the `pilot_problems` count) did not: a Problem hidden before any
sample was ever drawn from it still counted toward `fallback_share` while permanently escaping
the accuracy check, so `key_accuracy` could look better than true extraction quality purely
because the worst candidates were never eligible to be sampled.

Chose the simpler of the two options the finding offered: `gate.pilot_problem_ids()`
(`backend/hoctap/builder/gate.py`) now excludes hidden Problems (an `outerjoin` against
`content_review_status` filtering `hidden == 0`) the same way `spotcheck.eligible()` already
excludes them from the sample draw, instead of separately freezing the eligible set at
first-draw time. This is the single source both `report()`'s fallback/pilot-problem counts and
`draw_sample()`'s candidate set now go through, so they can no longer disagree about which
Problems "count". A Problem hidden *after* being sampled is unaffected by this change: its
verdict (and `first_wrong_at`) is tracked independently of its current hidden state, which is
already the correctly-covered case from finding #5 in the table below.

Added `test_hidden_before_sampling_is_excluded_from_fallback_share` and
`test_hiding_a_fallback_problem_before_sampling_also_excludes_it` to `backend/tests/test_gate.py`,
covering both a hidden non-fallback Problem (drops only the denominator) and a hidden Problem
that itself has a `fallback` Part (drops both numerator and denominator).

## Spec Change Log

- 2026-09-28 — Note (orchestrator, user-approved): frontend Vitest could not be run to completion locally (worker processes failed to start under severe memory pressure from unrelated concurrent sessions on the shared machine — verified via `free -h` showing <150MB free and `require('jsdom')` itself hanging; not a code issue). Backend (597 tests), `ruff check`, and `npm run build` all passed. `npm run lint` passed. Marked done on the user's explicit instruction, accepting the frontend-test-run gap. Owner should run `cd frontend && npm run test -- --run` once machine memory is free, before relying on this story's frontend behaviour.

- 2026-09-27 — Trigger: review. Amended (orchestrator decision, gate semantics): `key_accuracy` measures EXTRACTION accuracy — a `wrong` verdict on a sample item counts as wrong permanently (fixing the Problem does not remove it); a `correct` verdict counts only while the Problem's hash is unchanged. Approval validity additionally requires `checks_passed`, an unchanged estimate to the cent, and a sample whose recorded scope_hash equals the current scope. Samples exclude Problems with any `fallback` Part and are drawn with size `gate_min_sample + 5`. `build_jobs.run_kind` (pilot|full) defines the pilot scope. `build full` exits 3 on GATE_NOT_APPROVED. KEEP: all matrix rows.

- 2026-09-27 — Accepted deviation (orchestrator): a Sai spot-check verdict is stored as an open `parent`-kind note via the Error Report mechanism, so the Problem is also hidden from the child until resolved. Rationale: a Problem with a known-wrong Answer Key must not reach Bin. KEEP.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Approval stays valid after checks fail or est changes | high | 2 reviewers → patch (valid requires checks_passed and unchanged est to the cent) |
| 2 | Old sample re-approves after scope grows | high | 3 reviewers → patch (sample records scope_hash; approve and validity require match) |
| 3 | Fixing sampled errors inflates key_accuracy | high | gate must estimate extractor accuracy → patch (a `wrong` verdict counts wrong permanently; `correct` counts only for current hash) |
| 4 | fallback Problems sampled for answer accuracy | medium | → patch (exclude any Problem with a fallback Part) |
| 5 | Hidden after sampling still counts | false | Sai itself hides the Problem; its verdict must keep counting |
| 6 | Sample exactly min size; small pilot has no guidance | medium | → patch (draw min+5; UI/CLI say "chạy thử thêm trang" when eligible < min) |
| 7 | Cost ignores failed/pending pilot pages; loads all rows | medium | → patch (scope costs = all pilot-kind jobs' page_refs incl. failed; SQL filter) |
| 8 | est_cost_seen NaN/inf → 500; assert for control flow; 422 undocumented | medium | → patch |
| 9 | Sai note never resolved | false | resolvable via "Đã xử lý" in the editor (Story 1.8) |
| 10 | Answer view unusable for image_select/spot_difference/connect_dots; only first crop shown | medium | → patch (render regions/dots over the crop; all crops) |
| 11 | Pilot warning fires when scope won't change | low | → patch |
| 12 | build full exit 2 collides with argparse | low | → patch (exit 3) |
| 13 | GateCard: accepted not reset on est change; stale error | medium | → patch |
| 14 | Pilot/full separation unenforced | high | → patch (build_jobs.run_kind pilot|full, default pilot; scope filters pilot) |
| 15 | Latest ordering by timestamp | low | → patch (order by UUIDv7 id) |
| 16 | Tests missing (STALE in SpotCheckTab, GateCard refetch, editor back link, set_verdict errors, NaN, re-approve with old sample, CLI FAIL output) | medium | → patch |
| 17 | No FKs on spot-check tables | low | → patch |
| 18 | (2026-10-01, Orchestrator's Independent Audit) `spotcheck.eligible()` excludes any `hidden` Problem from ever being drawn into the accuracy sample, but `gate.py`'s `pilot_problem_ids`/`fallback_share` math does NOT exclude hidden Problems. A parent hiding a batch of visibly-bad pilot Problems for any ordinary reason (not even to game the gate) BEFORE a sample is drawn permanently removes those Problems from the accuracy sampling pool while they keep counting toward `fallback_share` -- `key_accuracy` can then look better than true extraction quality, since the worst candidates were never eligible to be sampled. Distinct from the already-covered case (prior finding, Sai-verdict-hides-a-Problem) where `first_wrong_at` correctly keeps it counted -- this gap is specifically for Problems hidden before sampling for unrelated reasons | low-medium | confirmed by 1 reviewer; requires only a legitimate parent action, not an adversarial bypass, but undermines "the sample reflects true pilot quality" which is the entire point of the gate -> patch: either exclude hidden-before-sampling Problems from `pilot_problem_ids`/`fallback_share` the same way `eligible()` already does, or (simpler) freeze the eligible/denominator set at first-sample-draw time so a later hide can't change which Problems "count" without also staying samplable -> **patched (2026-10-01)**: `gate.pilot_problem_ids()` now excludes hidden Problems the same way `spotcheck.eligible()` already does, so `fallback_share` and `pilot_problems` can no longer disagree with the accuracy sample about which Problems count |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context). 3 parallel reviewers traced every entry point to `hoctap build full`/the full-run API and confirmed **the gate genuinely cannot be bypassed via any CLI or API path** -- `require_approval()` is checked at CLI start, at API `start_full`/`_resume_full`, AND again per-book mid-run; the pilot-start request schema has no client-settable `run_kind` field; the whole `/build/*` router requires a real signed-cookie parent session. All prior HIGH/MEDIUM findings (including #14, pilot/full separation) were independently re-verified as genuinely landed in code, and a 45-function dedicated test file (`test_gate.py`) was confirmed to cover essentially every I/O matrix row and triage item by name; a reviewer also independently re-ran the relevant test subset directly (143/143 passed). One new finding (#18, low-medium) above -- a legitimate-use gap in the accuracy-sampling pool, not a bypass.

## Verification

### 2026-09-28 — Resumption pass (verify patches actually landed, finish what didn't)

Story 1.9 was left `in-progress` with the Review Triage Log above fully triaged, but several
rows marked `→ patch` had only their *evidence text* recorded, not a landed fix, and the test
suite had not been re-run against the patched code. This pass checked every `patch` row against
the current code, finished the ones that were still missing, and fixed the tests that were left
asserting the pre-patch behavior (a real gap: `uv run pytest` failed before this pass).

- Row 10 (image_select/spot_difference/connect_dots unusable in the spot-check Answer view) --
  **was not actually patched**: `SpotCheckTab.tsx` still sliced `crop_urls` to the first crop
  and `answerLines()` still rendered raw region/dot keys as text. Fixed: all crops are now shown;
  a new `AnswerOverlay` (`frontend/src/pages/review/answerOverlay.tsx` +
  `overlayGeometry.ts`) draws the regions (image_select), the numbered dots and their sequence
  (connect_dots), and the differences on the right image (spot_difference) directly on the
  Part's own crop, using the normalised bbox/x,y coordinates already in the Answer Key. Covered
  by a new SpotCheckTab test.
- Row 7 (pilot cost must include failed/pending pilot pages) -- the landed `_cost()` used
  `page_ref NOT IN (full-kind refs)`, which is a superset of "is a pilot page": a cost row for a
  page with no `build_jobs` row at all was still counted. Fixed to `page_ref IN (pilot-kind
  refs)`, matching the row's own evidence ("scope costs = all pilot-kind jobs' page_refs incl.
  failed").
- `backend/tests/test_gate.py` and `test_app.py` were still asserting pre-patch numbers and
  exit codes for already-landed patches (rows 2, 6, 12, 14): sample size 30 instead of
  `gate_min_sample + 5` = 35 (and its stratified allocation), `spotcheck.draw_sample` called
  without the now-required `scope_hash`, `build full`'s exit code 2 instead of 3, and the
  migration version stub `0008_gate_and_spot_checks` instead of `0009_build_jobs_run_kind`.
  Corrected each to the current, intended behavior (verified by re-deriving the expected
  numbers from the actual `allocate()` output, not guessed). One assertion was substantively
  wrong under the corrected semantics, not just stale: `test_stale_verdict` expected the check
  to still fail after one verdict went stale, but a stale verdict is excluded from *both* sides
  of the accuracy ratio (spec: "not counted"), so 34/34 correct passes; fixed the assertion to
  match the specified semantics.
- `frontend/openapi.json` (and the generated `schema.d.ts`) were stale relative to the backend:
  re-exporting via `hoctap export-openapi` picked up `sample_outdated`, `eligible_problems`,
  `enough_problems`, `first_wrong_at`, `counted` and the documented error responses that the
  landed backend code already had. Regenerated and fixed the two frontend fixtures
  (`gateFixtures.ts`) that the now-complete types exposed as incomplete.
- Environment blocker (not a Story 1.9 defect, but blocked all verification): this sandbox's
  Python 3.14 build is a pre-release (`3.14.0rc2`) whose `typing._eval_type` no longer accepts
  the `prefer_fwd_module` keyword that the pinned `pydantic==2.13.5` passes on Python ≥ 3.14 --
  `import fastapi` itself raised `TypeError` before any test ran. No compatible pydantic or
  final Python 3.14 build is reachable from this sandbox's package mirrors. Added a narrow,
  clearly-scoped compatibility shim (`backend/hoctap/_py314_compat.py`, applied from
  `hoctap/__init__.py` and `backend/tests/conftest.py`) that drops the unsupported keyword only
  when the running interpreter actually lacks it; a build where the interpreter and pydantic
  agree is unaffected. **Flag for the owner:** if the real dev/CI machine also runs a Python
  3.14 pre-release, the app would fail to start at all without this shim -- worth checking which
  exact 3.14 build is used there, and removing the shim once Python and pydantic agree again.

Verification after this pass: `cd backend && uv run pytest -q && uv run ruff check .` -- 572
passed, all checks passed. `cd frontend && npm run gen:api && npm run build && npm run test --
run --pool=threads && npm run lint` -- 67 passed, build and lint clean.

### 2026-09-28 — Test pass (row 16 and the untested patches)

- **Backend tests added in `backend/tests/test_gate.py`:**
  - first-wrong rule (a Sai then a fix and a Đúng still counts wrong);
  - a Đúng on an edited Problem is not counted;
  - approval invalidated by a later Sai, by an edit that makes a Đúng stale, and by an estimate change of ≥ 1 cent (a sub-cent change keeps it);
  - re-approving with the pre-scope sample returns SAMPLE_OUTDATED and the report says to draw again;
  - Problems with any fallback Part are never drawn (NOTHING_TO_SAMPLE when none is eligible);
  - draw size = min + 5, or all eligible, and `enough_problems`;
  - `run_kind` `full` is outside the scope and the cost, and failed and cut-off pilot pages are in the cost;
  - approve bodies with NaN, ±Infinity, a negative estimate or an unknown field get 422 and store nothing;
  - set_verdict NOT_IN_SAMPLE, PROBLEM_RETIRED and INVALID_EFFECTIVE;
  - `build full` exits 3;
  - `build gate` prints the FAIL marks and the "chạy thử thêm trang" guidance;
  - the latest sample and approval are chosen by id even when the timestamps are equal or reversed.
- **Frontend tests added:**
  - SpotCheckTab: a STALE verdict refetches the Problem and the spot-check; the spot_difference and connect_dots overlays.
  - GateCard: ESTIMATE_CHANGED refetches and shows the new amount; the tick resets when the estimate changes; the sample-outdated and not-enough-Problems notes.
  - ProblemEditor: the `?from=spot-check` back link.
- **Bugs found and fixed:** GateCard (rows 6 and 13 had not landed in the UI).
  - The "Tôi chấp nhận…" tick survived a refetch that changed `est_cost`. The tick is now bound to the estimate it was given for.
  - The card never showed the sample-outdated or "chạy thử thêm trang" guidance. Both are now shown as notes.
  - No backend code change was needed.
- **Pending-page wording:** `build_jobs.status` allows only done or failed, so a "pending" pilot page is one whose extract call was cut off. Its cost is recorded and it has only its `render` job, so it is counted through that job.

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd frontend && npm run gen:api && npm run build && VITEST_MAX_WORKERS=2 npm run test -- --run && npm run lint` -- expected: success
