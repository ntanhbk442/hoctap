---
title: 'Story 1.9: Spot-check, pilot report and go/no-go gate'
type: 'feature'
created: '2026-09-27'
status: 'in-review'
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

- **Pilot scope:** every page ref with a `done` extract job. No full-run extraction exists yet, so every extraction so far counts as pilot; Story 6.2 must keep full-run pages out of `gate.pilot_refs()` (for example by a distinct stage or marker). Otherwise the full run would invalidate its own approval.
- **Problem Type for strata:** the type of the Problem's first Part (from the effective doc). Allocation gives each present type 1, then splits the rest in proportion to (count − 1) by largest remainder (`spotcheck.allocate`).
- **Sai note:** stored with `review.add_error_report(kind="parent")`, because that is the only existing way into Cần duyệt. The note is prefixed "Kiểm tra ngẫu nhiên: đáp án sai." A side effect of the open parent note is that the Problem is also hidden from the child until the note is resolved. A repeated Sai for the same hash does not open a second note.
- **Verdict API:** `PUT /parent/review/spot-check/{sample_id}/items/{problem_id}` takes `content_hash`. A different current hash gets 409 STALE, and an older sample gets 409 SAMPLE_OUTDATED. A retired sampled Problem's verdict counts as stale.
- **`build_gate` extras:** `scope_hash` (sha256 of the sorted pilot refs) and `revoked_at` were added beside the listed columns. `metrics_json` also stores the pilot refs. Revoke is idempotent. `accept_cost: false` gets 422 COST_NOT_ACCEPTED.
- **Pilot cost:** the reported `cost_usd` of every call for scope pages (extract and verify), plus `extraction_max_budget_usd` per unknown-cost call. `total_pages` is the sum of `content_catalog_books.page_count`.
- **Fallback share:** computed on the effective doc (or the extracted doc when the merge is invalid), over published, non-retired pilot Problems. Hidden Problems are included.
- **CLI:** `hoctap build gate` prints the report and exits 0. `hoctap build full` exits 2 with `GATE_NOT_APPROVED: …` on stderr, or prints "chưa triển khai (Story 6.2)" and exits 0. `build pilot` warns on stderr whenever a valid approval exists.
- **Editor link:** "Sửa" opens `/parent/review/problems/{id}?from=spot-check`, whose back link returns to the spot-check tab. Saving in the editor refetches the spot-check and the gate report.

## Spec Change Log

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

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd frontend && npm run gen:api && npm run build && VITEST_MAX_WORKERS=2 npm run test -- --run && npm run lint` -- expected: success
