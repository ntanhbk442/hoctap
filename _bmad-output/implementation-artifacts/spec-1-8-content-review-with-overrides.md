---
title: 'Story 1.8: Content Review with overrides'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'tree:5456364c0375f6b5da99c12cb5fd76b9a76a99f7'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Anh must be able to check extracted Problems beside the scan, fix them, approve or hide them, and curate the Concept list. These edits must survive re-extraction and control what Bin can see (FR-4, FR-6, AD-3, AD-4, AD-5).

**Approach:**
- `content.review` gains:
  - field-level overrides with a `base_hash`;
  - a per-Problem review status (approved hash, hidden);
  - Error Report storage;
  - curated Concepts built from proposals.
- `content` gains `effective_problem()` and `visible_to_child()`: the only merge path and the only child selector.
- Parent-guarded APIs, plus a Parent "Duyệt nội dung" (Content Review) screen with the tabs Cần duyệt (to review), Tất cả (all problems) and Khái niệm (concepts). Kiểm tra ngẫu nhiên (random spot-check) is Story 1.9.

## Boundaries & Constraints

**Always:**
- **Overrides** live in `content_review_overrides`, unique on (`problem_id`, `part_key` or '' for the top level, `field`).
  - Top-level fields: `instruction`, `display_label`.
  - Per-Part fields: `prompt`, `answer`, `hint`, `solution`, and `part` (a whole Part replacement, used to change a Problem Type).
  - `value_json` holds the new value. `base_hash` = sha256 of the canonical JSON of the extracted value at save time.
- **`effective_problem(problem_id)`** returns the effective ProblemDoc together with its effective `content_hash` and a list of conflicts:
  - It applies the overrides onto the extracted `doc_json`: `part` first, then the fields.
  - A conflict is an override whose `base_hash` no longer equals the hash of the current extracted value, or whose `part_key` no longer exists. The override still wins where it can apply; one that cannot apply is skipped and listed.
  - A merged doc that fails ProblemDoc validation raises a clear error. Save-time validation must prevent that.
  - Curated Concept links (below) replace `concept_ids`.
- **Saving an override** validates the full merged doc first. An invalid merge is rejected with 422 and the validation messages in Vietnamese-friendly form, and nothing is stored. Saving a value equal to the extracted one deletes the override.
- **`content_review_status`** holds (`problem_id` PK, `approved_hash`, `hidden`, `updated_at`).
  - Approve (Duyệt) sets `approved_hash` = the current effective hash.
  - Hide (Ẩn) sets `hidden` = 1, and Unhide (Hiện) sets it back.
- **`content_review_error_reports`** holds (`id`, `problem_id`, `kind` parent|child, `note`, `status` open|resolved, `created_at`, `resolved_at`). This story creates the storage and a resolve action; creating reports from the UI is Story 4.4.
- **`visible_to_child(problem_ids | query)`** is the single gate. A Problem is visible only when all of these hold:
  - it is not retired;
  - it is not hidden;
  - it has no open `parent` Error Report;
  - it has no conflict;
  - it is not `needs_review`, unless `approved_hash` equals the current effective hash.

  `child_view()` is applied to the effective doc.
- **Review queue (Cần duyệt):** Problems that are not retired and have any of: `needs_review` and not approved for the current hash; a conflict; an open Error Report; a `duplicate` flag. Sorted by book, then position.
- **Concepts:**
  - Curated Concepts live in `content_review_concepts` (`concept_id` = `g{grade}.{slug}` matching the ProblemDoc pattern, `grade`, `name_vi`, `created_at`), with links in `content_review_problem_concepts`.
  - Accept a proposal creates the Concept from its text (NFC, a unique slug with a `-2` suffix on collision) and links all of the proposal's Problems.
  - Merge a proposal into an existing Concept links its Problems to that Concept.
  - Rename changes `name_vi` only; `concept_id` never changes.
  - Accepted and merged proposals get `status` accepted|merged plus the target `concept_id`. A Problem's links are replaced when a re-publish changes its proposals, which rebuilds the links from accepted/merged proposals.
- **API**, all under `/api/v1/parent/review/*` and guarded by `require_parent`:
  - `queue`
  - `problems?book_id=&unit_key=&lesson_key=` (paginated, 50 per page)
  - `problems/{id}` returns: extracted, effective, overrides, conflicts, status, reports, crop URLs, and source page image URLs
  - `PUT problems/{id}/overrides` (field-level payload) and `DELETE problems/{id}/overrides/{override_id}`
  - `POST problems/{id}/approve|hide|unhide`
  - `POST reports/{id}/resolve`
  - `concepts` (list of proposals with counts, and curated Concepts), with `POST` actions `accept`, `merge`, `rename`
- **Assets:** `/assets-data/crops/**` is served to anyone on the LAN (the child needs crops). `/assets-data/pages/**` requires the parent cookie.
- **UI** (Vietnamese, plain Parent Area styling from Story 1.2):
  - Three tabs. The problem list shows the badges `cần duyệt`, `xung đột` (conflict), `báo lỗi` (error report), `đã ẩn` (hidden) and `trùng` (duplicate).
  - The editor shows the page crop and source page image on the left, and on the right:
    - instruction and display label inputs;
    - per Part: prompt, hint and solution steps as text areas;
    - the answer as a structured editor for the keyed/list types, or a JSON textarea for the other types;
    - a JSON textarea to replace the whole Part.
  - It has Lưu (save), Duyệt, Ẩn/Hiện and "Bỏ sửa" (revert an override). Errors from 422 are shown inline.
  - The Khái niệm tab lists proposals by Grade with counts and the Nhận (accept), Gộp vào… (merge into) and Đổi tên (rename) actions.

**Never:**
- No Kiểm tra ngẫu nhiên spot-check (Story 1.9). No creating Error Reports from the UI (Story 4.4). No audio regeneration yet; `speech_key`s arrive in Story 2.2.
- The builder never writes `content_review_*` (AD-2). Publish must not delete overrides or status.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Edit answer | PUT answer for part a | stored with base_hash; effective doc uses it; the problem is visible only after approval if needs_review | N/A |
| Invalid edit | answer missing a slot | 422 with messages; nothing stored | N/A |
| Edit equal to extracted | value == extracted | override removed | N/A |
| Re-extract, same field unchanged | extracted value unchanged | no conflict; override still applied | N/A |
| Re-extract, field changed | extracted value differs from base | conflict listed; override still wins; problem in queue; not visible | N/A |
| Part removed by re-extract | override's part_key gone | conflict; override skipped | N/A |
| Approve | needs_review problem | approved_hash = effective hash; visible | N/A |
| Edit after approve | new override changes the effective hash | needs approval again (hidden) | N/A |
| Hide | any problem | not visible; badge đã ẩn | N/A |
| Open parent report | report kind parent open | not visible until resolved | N/A |
| Child report | report kind child open | in queue; still visible | N/A |
| Accept proposal | "So sánh số" (grade 1, 3 problems) | concept g1.so-sanh-so; 3 links; effective concept_ids updated | slug collision → -2 |
| Merge | proposal into existing concept | links added; proposal status merged | N/A |
| Rename | concept name | name_vi changed; id unchanged | N/A |
| Pages auth | GET /assets-data/pages/... without cookie | 401 | N/A |
| Crops public | GET /assets-data/crops/... | 200 | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/content/review/{models,service}.py` -- proposals and problem↔proposal links exist (Story 1.7). Extend them here.
- `backend/hoctap/content/catalog/{models,service}.py` -- `content_catalog_problems` (`doc_json`, `content_hash`, `needs_review`, `verify_status`, `duplicate`, `retired_at`), units and lessons.
- `backend/hoctap/content/schema.py`, `views.py` -- ProblemDoc, `child_view`, `answer_map`.
- `backend/hoctap/api/parent.py`, `deps.py`, `build.py` -- the `require_parent` pattern. Add `api/review.py` and mount it in `app.py`.
- `backend/hoctap/api/spa.py` / `app.py` -- add the `/assets-data` serving before the SPA fallback.
- `frontend/src/pages/ParentHome.tsx`, `App.tsx`, `api/client.ts`, `api/queries.ts` -- the parent pages pattern. Add `pages/review/*`. Run `npm run gen:api` after the backend changes.
- Migrations: the latest is `0006_catalog_problems`. Add `0007_review_tables`.

## Tasks & Acceptance

**Execution:**
- [x] `content/review/models.py` + `0007_review_tables.py` -- the overrides, status, error_reports, concepts and problem_concepts tables, plus the proposal status/target columns.
- [x] `content/review/service.py` -- overrides (save, delete, validate), approve/hide, resolve report, concepts accept/merge/rename, queue.
- [x] `content/effective.py` -- `effective_problem`, `content_hash`, conflicts, and `visible_to_child`.
- [x] `api/review.py`, `app.py` assets mounts -- the endpoints above.
- [x] `backend/tests/test_review.py` -- every matrix row.
- [x] `frontend/src/pages/review/{ReviewPage,ProblemList,ProblemEditor,ConceptsTab}.tsx` + routes + a link from ParentHome -- the UI, with Vitest tests for listing, a save error shown inline, approve and hide, and accept proposal.

**Acceptance Criteria:**
- Given published pilot problems, when Anh opens Duyệt nội dung, edits an answer, saves and approves it, then the effective doc reflects the edit, the problem becomes visible to the child, and a re-publish does not lose the edit.

## Implementation Notes

- **Effective hash excludes `concept_ids`.** The effective `content_hash` is the sha256 of the canonical effective doc without `concept_ids`. Otherwise accepting or merging a Concept would change the hash and withdraw approvals.
- **`concept_ids` = curated links only.** The effective `concept_ids` is always the sorted list of the Problem's curated links; the extracted `concept_ids` are replaced even when there are no links.
- **Duyệt.** The client sends the `content_hash` it displayed; a different current hash gives 409 `STALE`. Approving moves the `base_hash` of each `base_changed` override to the current extracted value. A `part_missing` conflict stays until "Bỏ sửa". Approving or hiding a retired Problem gives 409 `PROBLEM_RETIRED`.
- **Invalid merges after re-extraction.** If re-extraction makes a merge invalid, `effective_problem()` raises `InvalidEffectiveDoc`. The listing, queue and `visible_to_child()` treat that Problem as in conflict and not visible, and `problems/{id}` returns `effective: null` with `effective_error` messages. A revert is refused only when it would turn a valid doc invalid. `DELETE problems/{id}/overrides` ("Bỏ tất cả sửa đổi") drops every override.
- **Queue and duplicates.** A duplicate leaves the queue once it is approved for the current hash or hidden. The queue is prefiltered in SQL (needs_review, duplicate, has overrides, open reports). `problems` filters and paginates in SQL and merges only the Problems on that page.
- **Errors.** `AppError` carries optional `details`, which is omitted when null. A 422 on save lists Vietnamese messages built from fixed templates per pydantic error `type`.
- **Extra endpoint.** `GET /parent/review/books` lists the Books with their active Units and Lessons, for the Tất cả filters.
- **Frontend.** `ProblemSummary.awaiting_approval` holds the badge flag. While there are unsaved edits, Duyệt, Ẩn/Hiện and Bỏ sửa are disabled, and leaving the page asks for confirmation. `renderAt` in the tests now uses a data router.
- **Vitest workers.** `VITEST_MAX_WORKERS` optionally caps Vitest workers (unset by default). On the WSL `/mnt/c` checkout, jsdom workers sometimes time out while starting.

- **2026-10-01 fixes (findings #18, #19):** `save_overrides()` now takes an optional `expected_hash` and refuses the save with 409 `STALE` when it differs from the current effective `content_hash`, closing the override-vs-override clobber race (two tabs / a dropped-response retry editing the same field no longer silently overwrite each other). `OverridesIn` gained `expected_hash`; `PUT .../overrides` passes it through; the frontend's `saveOverrides()` now sends `detail.content_hash` (the hash the editor had open) and the existing `onError` STALE handling (already used by `approve()`) refreshes the problem on a conflict with no further UI change needed. Separately, the first-time-insert branch of `save_overrides()` now catches `IntegrityError` (the losing side of a concurrent first-time insert against `uq_content_review_overrides`) and raises a 409 `OVERRIDE_CONFLICT` `AppError` instead of letting it fall through to a bare `INTERNAL_ERROR` 500.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Open parent reports can't be resolved from UI (problem stays hidden) | high | → patch (Đã xử lý button) |
| 2 | Duplicate flag never leaves the queue | medium | → patch (approve/hide dismisses) |
| 3 | Approve has no stale check; can approve unseen content | high | → patch (client sends content_hash; 409 STALE) |
| 4 | Approve possible with unsaved edits; form remount drops edits | medium | → patch |
| 5 | "Đã lưu." notice lost on remount | low | → patch |
| 6 | Invalid effective doc: form edits extracted, hides overrides; every revert refused | high | → patch (allow revert when already invalid; show overrides; revert-all) |
| 7 | diff() sends untouched solution/answer edits after trimming | medium | → patch (only when field changed) |
| 8 | Vietnamese error translation corrupts keys/values | medium | → patch (translate by pydantic error type) |
| 9 | Queue/list re-merge whole catalog per request | medium | scales poorly at 15k problems → patch (SQL prefilter + paginate) |
| 10 | ReviewError duplicates AppError; API imports domain | low | → patch |
| 11 | needs_review means two things | low | → patch (rename summary field) |
| 12 | AllTab filter/page lost on navigation; list blanks on paging; page beyond last; books error hidden | low | → patch |
| 13 | vitest maxWorkers hard-coded | low | → patch (env var) |
| 14 | Concept id suffix overflow → 500; empty name on accept | low | → patch |
| 15 | Approve/hide on retired Problem; orphan error reports | low | → patch |
| 16 | Test gaps: retired exclusion, accept keeps approval, invalid-effective path, delete refusal/404, GRADE_MISMATCH and other error codes, all mutating routes need parent, list/json/Part editors, unhide, pagination, concepts errors | medium | → patch |
| 17 | effective_problem not literally the only merge caller | low | reject (all go through merge(); documented) |
| 18 | (2026-10-01, Orchestrator's Independent Audit) Override-vs-override race: `save_overrides()` reads the current override row then does an `UPDATE ... WHERE id == o.id` with no optimistic-concurrency check (no `updated_at`/version compare, no re-read before write). Two near-simultaneous `PUT .../overrides` for the SAME field (two tabs, or a client retry after a dropped response) both validate independently against the same prior state; the second `UPDATE` silently clobbers the first's `value_json`/`base_hash` with no error and no UI indication an edit was lost. Distinct from the already-covered `base_changed`/`STALE` machinery, which only guards extraction-vs-override and approve-vs-content_hash races, not override-vs-override races | medium | confirmed by 1 reviewer via direct trace -> **patched (2026-10-01)**: `save_overrides()` takes `expected_hash` (the effective `content_hash` the editor had open), checked against the current state before any write and refused with 409 `STALE` on a mismatch -- the same mechanism `approve()` already uses, now reused for this race too. Client sends the `content_hash` it displayed when editing started |
| 19 | (2026-10-01, Orchestrator's Independent Audit) Concurrent first-time override creation on the same `(problem_id, part_key, field)` races against the table's own `UniqueConstraint` -- the insert has no `try/except`, so the losing request's `IntegrityError` isn't caught by any handler in `hoctap/api/errors.py` (only `AppError`/`StarletteHTTPException`/`RequestValidationError`/generic `Exception` are handled) and falls through to a bare `INTERNAL_ERROR` 500 instead of a usable conflict message | low | confirmed by 1 reviewer; data integrity is fine (clean rollback), only the error UX is degraded -> **patched (2026-10-01)**: the insert branch in `save_overrides()` now catches `IntegrityError` and raises `AppError(409, "OVERRIDE_CONFLICT", ...)` instead of letting it fall through to a generic 500 |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context). 3 parallel reviewers confirmed the prior HIGH/MEDIUM findings (#3 approve-with-no-staleness-check, #6 invalid-effective-doc-blocks-every-revert, #9 queue-re-merges-whole-catalog-in-Python) are genuinely fixed in current code. New findings #18 (medium) and #19 (low) above, both in the override-write path specifically.

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd frontend && npm run gen:api && npm run build && npm run test -- --run --pool=threads && npm run lint` -- expected: success
