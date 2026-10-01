---
title: 'Story 4.3: Assignments'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: '20cc654d1eb09415f75cbcfa0cbcac31169b5a05'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing named Assignment exists in code (no table, endpoint or UI; grep finds only unrelated words). Anh cannot pick tomorrow's Lesson, Home never shows "Bài hôm nay", and the Dashboard (Story 4.2) has no Assignment status. FR-20.

**Approach:** Add `progress_assignments` (one Lesson `ProblemSetRef` frozen per row, a local date, one Profile), created and read by a new `learning/assignments.py`. A Session started from the Home card is linked to it; status is derived from that Session. Home shows the card first, a Parent page assigns, and the Dashboard lists statuses.

## Boundaries & Constraints

**Always:** The ref is stored as the same fields `LessonRef` uses and resolved only via `learning.problem_sets.resolve`; the Session still freezes its own list at start (AD-9), so hiding a Problem later never reopens or moves chunks. `progress_sessions` gains nullable `assignment_id`. One Session covers a whole Lesson (chunks of 10 are slices of it), so "all Sessions complete" means the linked Session has `completed_at`. Status is derived, never stored: Chưa làm (no linked Session), Đang làm (linked, unfinished; "Phần i/n" where i is the chunk of the first Problem with no attempt), Đã xong. Carried over = date before today and not done, shown "Hôm qua" with no guilt copy. Done means only the Session linked by `assignment_id` completes (human decision): the same Lesson practised through the Library or "Học tiếp" leaves the Assignment open. Home shows one "Bài hôm nay" card at a time (human decision): the oldest not-done Assignment dated today or earlier first, the rest queue behind it and appear as each is done or deleted. Days use `LOCAL_TZ`; `assigned_date` is a local `YYYY-MM-DD`. Parent endpoints sit behind `require_parent`. New spoken copy ("Bài hôm nay", "Hôm qua") gets entries in `phrases.vi.json`.

**Never:** Concept practice sets (no `ConceptRef` until Epic 5; extend the same table then); a full Parent Library (assign lives on its own Parent page); recomputing grading, Stars or accuracy; pushing notifications or red/negative child copy; editing an Assignment (delete and recreate).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Assign | Lesson, today or later, Profile | 201, status Chưa làm | Past date 422; empty Lesson 422 `EMPTY_PROBLEM_SET`; unknown Profile 404 |
| Home today | Assignment dated today | "Bài hôm nay" card before "Học tiếp"; tap starts linked Session | None due: "Học tiếp" unchanged |
| Resume | Linked Session unfinished | Card shows "Phần i/n"; tap resumes that Session | N/A |
| Carry over | Dated yesterday, not done | Same card with "Hôm qua" ribbon | N/A |
| Complete | Linked Session gets `session_completed` | Đã xong; card gone from Home | Re-post is a no-op |
| Lesson done outside the card | Same Lesson practised via Library, no linked Session | Assignment stays Chưa làm / open | N/A |
| Several due | Yesterday's and today's both not done | One card, yesterday's first; today's shows after it is done | N/A |
| Delete | Anh removes a not-done Assignment | Gone from Home and Dashboard | Done ones are refused 409 |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/problem_sets.py` -- `LessonRef`, `resolve`, `ref_key`; reuse, no change
- `backend/hoctap/learning/sessions.py` -- `start_session` (add optional `assignment_id`), `find_unfinished_session`
- `backend/hoctap/learning/models.py`, `backend/hoctap/db/alembic/versions/0016_retry_queue_due.py` -- tables; head is 0016, new migration follows it
- `backend/hoctap/learning/metrics.py`, `backend/hoctap/api/dashboard.py` -- add assignments list, read-only
- `backend/hoctap/api/library.py` (`get_home`), `backend/hoctap/api/sessions.py` (`StartSessionIn`) -- Home payload, start link
- `frontend/src/pages/Home.tsx`, `Dashboard.tsx`, `ParentHome.tsx`, `App.tsx` -- card, section, menu link, route
- `frontend/src/audio/phrases.vi.json` -- new phrases; `GET /library/grades/{grade}/books` feeds the picker

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/db/alembic/versions/0017_assignments.py` + `learning/models.py` -- `progress_assignments` (id, profile_id, ref_kind, ref_key, book_id, unit_key, lesson_key, assigned_date, created_at, deleted_at) and `progress_sessions.assignment_id`
- [x] `backend/hoctap/learning/assignments.py` -- create/delete/list, `status(conn, a)`, `home_assignment(conn, profile, today)`
- [x] `backend/hoctap/api/assignments.py` (+ `app.py`) -- POST/GET/DELETE `/parent/assignments`; Session start accepts `assignment_id`, must match Profile and be undone
- [x] `learning/metrics.py`, `api/dashboard.py`, `api/library.py` -- statuses and Home field
- [x] Frontend -- `/parent/assignments` page (child, Grade→Book→Unit→Lesson, date defaulting to tomorrow, list with delete), Home card, Dashboard section; run `gen:api`
- [x] `backend/tests/test_assignments.py` plus Home, Dashboard and frontend tests -- cover the I/O matrix

**Acceptance Criteria:**
- Given an Assignment for tomorrow, when the day is today in Asia/Ho_Chi_Minh, then Home lists it first; before that it does not appear on Home but shows Chưa làm on the Dashboard.
- Given a 12-Problem Lesson assigned, when Bin finishes chunk 1 only, then the card and Dashboard say "Phần 2/2" and Đang làm, and it stays open until `session_completed`.

## Design Notes

Deriving status from `progress_sessions` keeps one source of truth (AD-6) and lets Story 4.2's dashboard consume it with no new materialisation. Linking by `assignment_id` avoids inferring from `ref_key`, which the same Lesson shares with ordinary practice.

## Verification

**Commands:**
- `cd backend && ruff check . && pytest tests/test_assignments.py tests/test_dashboard.py tests/test_sessions.py tests/test_library.py` -- expected: pass
- `cd frontend && npm run gen:api && npx tsc -b && npx eslint . && npx vitest run --pool=vmThreads src/pages` -- expected: pass

## Orchestrator's Independent Audit (2026-10-01)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `home_assignment()`/`list_for_profile()` pick the oldest not-done Assignment purely from Session-linkage status, never checking whether the Assignment's Lesson still `resolve()`s to any visible Problem. If every Problem in an assigned Lesson becomes invisible AFTER the Assignment is created (parent hides/retires the last visible Problem, or a late Error Report hides it), the child taps "Bài hôm nay", `start_session()` raises `422 EMPTY_PROBLEM_SET`, no Session is ever created, and `home_assignment()` returns the SAME Assignment again on the next load -- the card is permanently stuck, all later Assignments stay queued behind it forever, a raw Vietnamese error string renders directly on the child-facing Home screen, and nothing in the Dashboard distinguishes this from "Bin just hasn't started yet" | high | confirmed by 1 reviewer with a concrete, reachable scenario -> patch: validate resolvability at `home_assignment()`/`list_for_profile()` time (skip or flag an Assignment whose `resolve()` is now empty, matching the honest-not-faked pattern this codebase already uses elsewhere), AND/OR have the frontend's `openAssignment` error handler specifically detect `EMPTY_PROBLEM_SET` and surface a distinct, non-raw message plus make the stuck state visible on the Dashboard so the parent can see it needs attention/deletion. Implementer's call on the exact mechanism, but a child must never see a raw error string, and the queue must never jam silently forever |
| 2 | No direct test posts a mid-Session parent "Báo lỗi" flag/content-hide and then re-fetches `GET /sessions/{id}/bundle` to assert the already-frozen Session still serves that Problem (AD-9) -- the behavior is correct by code reading (confirmed in review-epic-4.md's own "Decision needed" resolution) but has no direct regression test | low | -> patch: add one test exercising exactly this: start a Session, hide/report the Problem mid-Session, re-fetch the bundle, assert the Problem is still present |

## Implementation Notes

- (2026-09-30) Migration `0017_assignments` adds `progress_assignments` and a nullable `progress_sessions.assignment_id`; status is derived from linked Sessions and never stored. Deleted Assignments are soft-deleted (`deleted_at`). Home returns the oldest not-done Assignment dated today or earlier; the Dashboard lists every non-deleted one.
- `POST /sessions` accepts `assignment_id` and rejects a mismatched Lesson with 422 `ASSIGNMENT_REF_MISMATCH` (an addition beyond the spec). The Home card's "Phần i/n" counts attempts inside the linked Session only, whereas the player's `attempted` flag counts across the whole Profile, so the two can disagree if the Lesson was practised earlier.
- `tests/test_app.py` hard-codes the migration head and table set; updated to `0017_assignments` and `progress_assignments`.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_assignments.py tests/test_dashboard.py tests/test_sessions.py tests/test_library.py tests/test_quiz.py tests/test_profiles.py` plus `tests/test_app.py` — 208 passed in the combined run with one `test_app.py` failure (stale migration head), fixed; `test_app.py` re-run alone — 55 passed.
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on Assignments, Home, Dashboard and ParentHome with `--pool=vmThreads` — 42 passed.
- The implementing agent reported 4 unrelated failures in `ExtractionPage.test.tsx` and `ProblemPlayer.speaker.test.tsx` that also fail on a stashed baseline; not re-run by me. Not run: the full backend and frontend suites in one pass.

### 2026-10-01: fixes from the Orchestrator's Independent Audit

- **Finding #1 (high).** `AssignmentInfo`/`AssignmentOut` gain a `resolvable: bool` field (`hoctap/learning/assignments.py`'s new `_resolvable()`, called from `_info()`): the same `problem_sets.resolve()` a Session start is about to call, run against the Assignment's own Lesson ref. `home_assignment()` now skips (never returns) a not-done row with `resolvable=False` -- the queue moves on to whatever is next, instead of jamming forever on a dead Assignment and 422ing the child with `EMPTY_PROBLEM_SET`. `list_for_profile()` (the Dashboard's source) keeps listing it with `resolvable: false`, so Anh can see it needs attention (delete it, or unhide/fix the Lesson's content) instead of a silent "Chưa làm" that never budges. A DONE Assignment is never re-checked (nothing will ever try to start it again, and checking would just be wasted work on the common, already-finished case).
  - Frontend: `Dashboard.tsx`'s Assignment row shows a plain-language note (`assignmentUtils.ts`'s new `unavailableNote()`) when `resolvable: false` and not done. `Home.tsx` additionally hardens the assignment-card error path (`assignmentErrorMessage()`): even though the backend fix means `EMPTY_PROBLEM_SET` should no longer reach a live card, any `ApiError` with that code (or `ASSIGNMENT_REF_MISMATCH`/`ASSIGNMENT_NOT_FOUND`/`ASSIGNMENT_DONE`) now renders a friendly, non-alarming Vietnamese phrase (`home_assignment_unavailable`) instead of the raw backend message, as defense-in-depth against any remaining race (e.g. Home's cache being stale by a few seconds relative to a just-triggered hide).
  - Test: `backend/tests/test_assignments.py::test_home_skips_assignment_whose_lesson_has_no_visible_problems` -- assigns a Lesson with one Problem, hides that Problem via `content.review.service.set_hidden`, asserts Home no longer returns the Assignment, the Dashboard still lists it with `resolvable: false`, a direct start attempt still legitimately 422s (the dead-end is real, just never shown to the child), and unhiding the Problem makes it resolvable (and servable) again. `frontend/src/pages/Dashboard.test.tsx` gained a matching case for the Dashboard's note.
- **Finding #2 (low, should-fix, done).** `backend/tests/test_sessions.py::test_bundle_after_parent_report_still_shows_frozen_problem` -- the sibling of the existing `test_bundle_after_hide_still_shows_frozen_problem`, but via `content.review.service.add_error_report(..., "parent", ...)` (Story 4.4's actual "Báo lỗi" write path) rather than `set_hidden` directly, confirming AD-9 holds for both ways a Problem can be hidden mid-Session.
- Also added (spec-4-2 #2's ask, filed against this story's own migration): `backend/tests/test_app.py::test_migration_0017_up_and_down`, matching the `test_migration_0013_...` precedent -- stages a DB at `0016_retry_queue_due` with a pre-existing `progress_sessions` row, upgrades to `0017_assignments`, confirms `progress_assignments` exists and the pre-existing row survives with `assignment_id IS NULL`, then downgrades and re-upgrades to `head`.
- Verification: `ruff check .` clean. `pytest tests/test_assignments.py tests/test_review.py tests/test_sessions.py tests/test_app.py tests/test_dashboard.py` -- 305 passed across the two targeted runs. Full backend suite `pytest -q` -- **1147 passed** (0:30:28; this shared machine had several other full-suite runs contending for CPU/memory at the time, which is why it ran long and one earlier attempt was killed by the background time limit -- not a bug in the suite itself). Frontend `tsc -b` and `eslint .` clean (synced to `/tmp`, fresh `npm ci`, offline `openapi.json` regenerated via `hoctap export-openapi` and `npm run gen:api`); `vitest run --pool=vmThreads src/pages/Dashboard.test.tsx src/pages/Assignments.test.tsx src/pages/Home.test.tsx src/pages/review` -- 83 passed. The full `src/pages` run reproduces the same 4 pre-existing, unrelated failures in `ExtractionPage.test.tsx`/`ProblemPlayer.speaker.test.tsx` noted in the prior re-verification; not caused by this change. Full frontend suite in one pass not run (not required for this backend/dashboard-focused change set beyond the pages above).
