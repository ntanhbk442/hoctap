---
title: 'Story 1.7: Crop, Concept tagging and publish'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'tree:5273c069081d16548feb8cdcf3017f3fc892f1df'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Validated and verified drafts sit in `build_page_results`. The app needs them as published content: stable Problems grouped into Units and Lessons, with cropped images and Concept proposals, so that review (Story 1.8) and play (Epic 2) can use them (FR-2, FR-4, AD-2, AD-3).

**Approach:**
- A `crop` stage cuts every ProblemDoc image, plus one whole-Problem crop, from the page JPEGs.
- A `publish` stage upserts Units, Lessons and Problems into new `content_catalog_*` tables, only through `content.catalog` functions. It retires Problems that vanished from re-extracted Lessons.
- Concept proposals are recorded through a new `content.review` service into `content_review_concept_proposals`.

## Boundaries & Constraints

**Always:**
- **Crops:**
  - Each file is `data/assets/crops/{book_id}/{problem_id}/{image_key}.jpg`, plus `_problem.jpg` for the Problem's first source-page bbox. A Problem spanning pages gets `_problem_p{n}.jpg` per page.
  - Crops are JPEG quality 90, with a 2% bbox padding clamped to the page.
  - The crop `input_hash` = page image hash + bbox + padding version. Crop jobs are skipped when done and the file exists.
- **Tables:**
  - `content_catalog_units`: `book_id`, `unit_key`, `label`, `title`, `position`.
  - `content_catalog_lessons`: `book_id`, `unit_key`, `lesson_key`, `label`, `title`, `position`, `is_quiz_sheet` (true when `lesson_key` = `phieu`).
  - `content_catalog_problems`:
    - identity and placement: `problem_id` (PK), `book_id`, `unit_key`, `lesson_key`, `position` (page, then draft order);
    - content: `doc_json` (the extracted ProblemDoc), `content_hash` (sha256 of the canonical doc JSON);
    - review flags: `needs_review` (0/1, copied from verify), `verify_status`, `duplicate`;
    - lifecycle: `source_page_first`, `retired_at`, `created_at`, `updated_at`.
- **Publish:**
  - It publishes every `valid` row of the requested pages. `needs_review` and duplicate rows are published too, but flagged; hiding is Story 1.8's visibility gate.
  - Invalid drafts are never published; they are counted and reported.
  - Upsert is by `problem_id`. An unchanged `content_hash` leaves the row untouched. A changed hash updates `doc_json`, `content_hash`, `needs_review` and `verify_status`, and clears `retired_at`.
- **Retirement (AD-3):** only for Lessons touched by this publish. A Problem in such a Lesson, previously published and absent now, gets `retired_at` = now. Nothing is ever deleted.
- **Ownership (AD-2):** `builder` never writes the `content_*` tables directly. It calls `content.catalog.publish_problems(...)` and `content.review.record_concept_proposals(...)`.
- **Concept proposals:**
  - Each ProblemDoc's `concept_proposals` strings are NFC-normalised, trimmed and case-folded into a `proposal_key`.
  - They are stored per Grade (from the book) in `content_review_concept_proposals` (`proposal_key`, `grade`, `text`, `problem_count`, `first_seen`, `status` = `proposed`), linked in `content_review_problem_proposals` (`problem_id`, `proposal_key`, `grade`).
  - Re-publishing is idempotent. Links for a Problem are replaced on each publish.
- **Command:** `hoctap build publish --book --pages` (no Claude calls, so no `--yes-spend`). `build pilot` runs crop and publish after verify unless `--no-publish`.

**Never:**
- No Claude calls. No curated Concepts or accept/merge UI (Story 1.8). No `content_review_status` rows (Story 1.8).
- Don't publish from `build_page_results` rows whose validate job is stale (reuse Story 1.5's current-hash rule).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First publish | 3 pages, 5 valid, 1 invalid draft | 5 problems, their units/lessons, crops written; report: 5 published, 1 invalid | N/A |
| Re-publish unchanged | same data | 0 rows changed, 0 crops re-cut | N/A |
| Content changed | one doc's answer changed | that row updated (`content_hash`), others untouched | N/A |
| Problem vanished | a lesson re-extracted without bai3 | bai3 gets `retired_at`; nothing deleted | N/A |
| Returns | bai3 appears again later | `retired_at` cleared | N/A |
| Untouched lesson | a lesson not in this publish | its problems keep their state | N/A |
| needs_review | verify disagree | published with needs_review 1 | N/A |
| Multi-page problem | source_pages p5+p6 | `_problem_p5.jpg`, `_problem_p6.jpg` | N/A |
| Bbox at page edge | bbox touching 1.0 | padding clamped; valid crop | N/A |
| Missing page image | page JPEG deleted | that page's crops fail with a clear report; publish of other pages proceeds; the affected problems are not published | exit 1 |
| Proposals | two problems propose "So sánh số" and "so sánh  số" | one proposal key, count 2 | N/A |
| Quiz lesson | lesson_key `phieu` | lesson `is_quiz_sheet` = 1 | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/stages/validate.py` -- writes `build_page_results` (`status`, `problem_id`, `duplicate`, `doc_json`, `input_hash`), and has the current-hash rule helpers.
- `backend/hoctap/builder/stages/verify.py` -- `needs_review` and `verify_status` on those rows.
- `backend/hoctap/builder/stages/render.py` -- the page JPEG paths and hash helper.
- `backend/hoctap/builder/pilot.py` + `cli.py` -- add crop and publish to the pilot flow, and a `build publish` command.
- `backend/hoctap/content/catalog/` -- `books.py`/`models.py`/`service.py` exist. Add the models and service functions for units, lessons and problems.
- `backend/hoctap/content/review/` -- new package: `models.py` and `service.py` (`record_concept_proposals`).
- Migrations: the latest is `0005_verify_columns`. Add `0006_catalog_problems`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/builder/stages/crop.py` -- the crop stage and its job records.
- [x] `backend/hoctap/content/catalog/{models,service}.py` -- the units/lessons/problems tables and `publish_problems` (upsert, retire, report).
- [x] `backend/hoctap/content/review/{__init__,models,service}.py` -- the proposals tables and `record_concept_proposals`.
- [x] `backend/hoctap/builder/stages/publish.py` -- selects current valid rows and calls the content services.
- [x] `backend/hoctap/db/alembic/versions/0006_catalog_problems.py`.
- [x] `cli.py build publish` + the pilot integration (`--no-publish`).
- [x] `backend/tests/test_publish.py` -- every matrix row.

**Acceptance Criteria:**
- Given pilot data from the fake client, when `hoctap build pilot ... --yes-spend` completes, then the problems are in `content_catalog_problems` with crops on disk, and a second run changes nothing.

## Implementation Notes

- **Current-hash rule:** `validate.page_input_hash()` is shared by validate and publish. A row is published only when its `input_hash` equals the hash the current `done` extractions give its page and that page's `validate` job is `done`; otherwise the page is reported stale. A page whose image is missing (so its current extract hash cannot be computed) falls back to its latest `done` extraction, so the missing image fails only the crops that need it (matrix row "Missing page image") instead of making its neighbours stale.
- **Unchanged rows:** a row is left untouched when its content hash, `needs_review`, `verify_status`, `duplicate` and position are unchanged and it is not retired. A later verify verdict on unchanged content therefore does update `needs_review`/`verify_status` (otherwise a Problem published unverified could never be cleared). A returning Problem with the same hash has `retired_at` cleared.
- **Retirement safety:** only Problems whose first page is currently extracted and validated can be retired, and Problems still present in `build_page_results` (any page, including stale rows or failed crops) are never retired. A failed re-extraction therefore retires nothing. Lessons touched = Lessons of the current rows of the requested pages plus Lessons of active Problems first found on those pages.
- **Crops:** `_problem.jpg` is always written (first source page); a multi-page Problem also gets `_problem_p{n}.jpg` per page. Padding is 0.02 normalised page units per side. Cut with PyMuPDF (no Pillow dependency). Crop jobs: `page_ref` = `{book_id}#p{page:03d}/{problem_id}/{name}`.
- **Units/lessons:** label/title come from the extraction headings (`validate.book_structure()`, same carry-forward rule); defaults `u00`/`l00` get empty label/title. Position = first page × 100 + order of first appearance on that page. `is_quiz_sheet` is also true for numbered `phieu2`… keys.
- **Proposal key** also collapses inner whitespace (needed for "so sánh  số"). Counts are recounted from the links; a proposal whose count drops to 0 is kept.
- `build publish` and `build pilot` exit 1 when any Problem fails to crop; stale pages are a warning (exit 0). `build pilot --no-verify` still publishes (rows flagged `needs_review`).

- **2026-10-01 fixes (findings #22, #23):** added `EffectiveProblem.no_concepts` (`content/effective.py`), a `no_concepts` filter on `content.review.service.list_problems()` and the `GET /parent/review/problems` route, a "chưa gắn khái niệm" badge in `ProblemList.tsx`, and a checkbox filter in `ReviewPage.tsx`'s Tất cả tab -- so a parent can find and tag Problems that published with zero curated Concept links. `rename_concept()` now checks `name_vi` uniqueness within the Concept's Grade before renaming, returning 409 `CONCEPT_NAME_CONFLICT` on a collision.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | invalid stored doc → KeyError in first_page lookup rolls back the whole publish | high | confirmed by 3 reviewers → patch + test |
| 2 | invalid re-extracted draft retires the live published Problem (present only from valid rows) | high | → patch (present = every row with a problem_id) |
| 3 | crop failure of an already-published Problem must not retire it — untested | medium | → patch (test) |
| 4 | missing-image fallback page set differs from validate's, making neighbours look stale | medium | → patch (same page set as run_validate) |
| 5 | image_key used as filename unchecked; `_problem*` keys could collide | low | schema KEY_PATTERN forbids `/`, `..` and a leading `_`? → patch (assert/reject in crop_specs regardless) |
| 6 | old crop files never removed after key/page changes | low | → patch (remove files in the Problem folder not in crop_specs) |
| 7 | two lesson headings on one page get the same text | medium | → patch (take text from the event) + test |
| 8 | retired/renamed Problems keep concept proposal links; counts too high | medium | → patch (retired ids passed with [] through review service; recount) |
| 9 | missing structure → blank label/title/position 0, overwriting existing rows | medium | → patch (skip upsert when row exists; report missing keys) |
| 10 | position encodings (page*100 vs page*1000) can collide | low | → patch (one scale; assert bounds) |
| 11 | reversed --pages range exits 0 with nothing | low | → patch |
| 12 | exit code: publish exits 0 when everything is stale | low | → patch (exit 1 with message when nothing could be published because all pages are stale) |
| 13 | one DB round trip per crop; pixmaps cached for whole run | low | → patch (load done jobs once; keep only current page pixmap) |
| 14 | crops written before publish txn fails — recovery untested | low | → patch (test re-run recovers) |
| 15 | migration test doesn't assert tables/indexes | low | → patch |
| 16 | source_pages min() vs [0] inconsistency | low | → patch (min by page everywhere) |
| 17 | pymupdf error classes not caught in crop | low | → patch |
| 18 | bbox change / deleted crop re-cut untested | medium | → patch (tests) |
| 19 | PilotReport.publish shadows module; `compared` built in two steps | low | → patch (rename, tidy) |
| 20 | pilot exits 1 on publish failure untested | low | defer (same helper tested via build publish) |
| 21 | "second run changes nothing" while build_jobs updated_at changes | low | false — claim concerns content tables; job bookkeeping is expected |
| 22 | (2026-10-01, Orchestrator's Independent Audit) Zero-concept Problems can ship to children forever untagged with no review-queue signal -- `effective.py`'s `visible`/`in_queue` checks never key off empty `concept_ids`/`concept_proposals`, and `record_concept_proposals` only writes rows for non-blank proposed texts, so a page where extraction simply omits `concept_proposals` for one problem produces zero signal anywhere: it publishes cleanly, verify agrees so `needs_review=0`, and it's indistinguishable in "Tất cả" from a problem deliberately left untagged | medium | confirmed by 2 independent reviewers -> **patched (2026-10-01)**: `EffectiveProblem.no_concepts` (true when the effective `concept_ids` is empty) is now returned on `ProblemSummary`, shown as a "chưa gắn khái niệm" badge in both Cần duyệt and Tất cả, and `GET .../problems` takes a `no_concepts` filter (SQL-side, via a `NOT IN` against `content_review_problem_concepts`) so a parent can list exactly the untagged Problems |
| 23 | (2026-10-01, Orchestrator's Independent Audit) `rename_concept()` only verifies the target concept exists -- never checks `name_vi` uniqueness within a Grade, so two different `concept_id`s can end up with identical Vietnamese display names in the Khái niệm tab, indistinguishable to the parent except by the opaque `concept_id` | low | confirmed by 1 reviewer -> **patched (2026-10-01)**: `rename_concept()` now rejects (409 `CONCEPT_NAME_CONFLICT`) a rename whose cleaned `name_vi` collides with another Concept's `name_vi` in the same Grade; the frontend already shows any mutation error inline, so no UI change was needed |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context). 3 parallel reviewers confirmed all 5 prior HIGH/MEDIUM findings (#1/#2/#5/#6/#10/#12 -- invalid-doc rollback, wrongly-retiring live problems on an invalid re-extract, image-key path-traversal, orphan crop cleanup, position-encoding collision, exit-code-on-all-stale) are genuinely fixed in current code with accompanying regression tests, not just claimed. New findings #22 (medium -- the most substantive new gap in this batch) and #23 (low) above.

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
