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

## Implementation Notes

- (2026-09-30) Migration `0017_assignments` adds `progress_assignments` and a nullable `progress_sessions.assignment_id`; status is derived from linked Sessions and never stored. Deleted Assignments are soft-deleted (`deleted_at`). Home returns the oldest not-done Assignment dated today or earlier; the Dashboard lists every non-deleted one.
- `POST /sessions` accepts `assignment_id` and rejects a mismatched Lesson with 422 `ASSIGNMENT_REF_MISMATCH` (an addition beyond the spec). The Home card's "Phần i/n" counts attempts inside the linked Session only, whereas the player's `attempted` flag counts across the whole Profile, so the two can disagree if the Lesson was practised earlier.
- `tests/test_app.py` hard-codes the migration head and table set; updated to `0017_assignments` and `progress_assignments`.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_assignments.py tests/test_dashboard.py tests/test_sessions.py tests/test_library.py tests/test_quiz.py tests/test_profiles.py` plus `tests/test_app.py` — 208 passed in the combined run with one `test_app.py` failure (stale migration head), fixed; `test_app.py` re-run alone — 55 passed.
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on Assignments, Home, Dashboard and ParentHome with `--pool=vmThreads` — 42 passed.
- The implementing agent reported 4 unrelated failures in `ExtractionPage.test.tsx` and `ProblemPlayer.speaker.test.tsx` that also fail on a stashed baseline; not re-run by me. Not run: the full backend and frontend suites in one pass.
