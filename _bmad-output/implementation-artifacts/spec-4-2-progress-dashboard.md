---
title: 'Story 4.2: Progress dashboard'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'a2c950d28359eba29ae8f15eed124cdea7c33d3a'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Anh cannot see how Bin is doing. The Parent Area (ParentHome) links only to Settings, Review and Extraction. Stars, Streak, badges, Retry items and per-Session first-try results exist, but nothing aggregates them per child, per day/week, per Book/Unit or per Concept.

**Approach:** Add a PIN-guarded, read-only `GET /parent/dashboard/{profile_id}` backed by one new `learning/metrics.py` (the single owner of dashboard metric definitions, reusing `session_wrong_problem_ids`, `compute_streak`, `total_stars`, `due_problem_ids`, `profile_badges`), plus a `/parent/dashboard` page with a child selector, linked first in ParentHome. Charts are plain HTML/CSS bars; no chart library.

## Boundaries & Constraints

**Always:**
- Read only `progress_*` and `content` views; no new table, no migration (head stays `0016_retry_queue_due`), no writes.
- Exclude `replay` Sessions from every figure (AD-6). Count only Sessions with `completed_at`.
- First-try accuracy = first-try-correct Problems / Problems in completed Sessions, from `session_wrong_problem_ids`. `fallback` Problems are listed as "tự kiểm tra" beside it, never in the ratio.
- Calendar days via `LOCAL_TZ` (Asia/Ho_Chi_Minh) from event `occurred_at` / Session `completed_at`, never `received_at`.
- Time per Session = sum of gaps between consecutive event `occurred_at`, each gap capped at 5 min (idle left open must not inflate it).
- Weak Concepts: a Problem-in-a-Session outcome is one Attempt, attributed to every effective Concept of the Problem (`content.effective`, curated links). Only Concepts with >= 5 Attempts are ranked, lowest first-try accuracy first, max 5 shown; others are omitted, not shown as zero.
- Recent mistakes: last 10 first-try-wrong Problems (non-replay), each with the child's submitted `value` (from the stored `attempt` payload) beside the Answer Key from the effective Problem. Parent-only view, so the answer key may appear.
- Progress per Book/Unit = attempted-visible / visible Problems, reusing `learning.progress.attempted_lesson_counts` and the Library's visible counts.
- Time window (human decision): the main figures cover the current calendar week, Monday to Sunday in Asia/Ho_Chi_Minh, with days after today shown as empty future days. No rolling window and no toggle.
- Weak-Concept accuracy (human decision) covers the last 4 calendar weeks ending today, not all-time.
- Quiz-mode Sessions (human decision) count in Sessions, time and accuracy like practice Sessions; there is no separate quiz section.
- Vietnamese copy; empty states are friendly ("Bin chưa làm bài nào").

**Never:** Recomputing Stars, grading or Streak; a chart dependency; Assignment status and the 🚩 "Báo lỗi" action (Stories 4.3/4.4; leave the mistakes list ready for it); child-facing exposure (route sits behind `require_parent`); UI redesign of the Parent Area menu.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | Cookie, child with completed Sessions | Stars, Streak, badges, Retry size, Mon-Sun daily rows (Sessions, minutes, accuracy; future days empty), week totals, Book/Unit progress, weak Concepts, mistakes | N/A |
| New child | No Sessions | All zeros, empty lists | N/A |
| Concept < 5 Attempts | Concept with 4 Attempts | Not listed | N/A |
| Monday morning | Nothing done yet this week | Seven rows with zeros for the week; prior weeks not shown | N/A |
| Old mistakes | Concept attempts older than 4 weeks | Excluded from weak-Concept ranking | N/A |
| Quiz Session | Completed `quiz` Session | Counted in Sessions, time and accuracy | N/A |
| Replay Session | Completed `replay` Session | Absent from every figure | N/A |
| Late sync | Attempt 23:55, received 00:10 | Counted on the 23:55 local day | N/A |
| Unknown child | Bad `profile_id` | Rejected | 404 `PROFILE_NOT_FOUND` |
| No cookie | Any request | Rejected | 401 |
| Retired/hidden Problem | Attempted, now invisible | Omitted from Concept ranking and mistakes | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/summary.py` -- `session_wrong_problem_ids`, `compute_streak`, `LOCAL_TZ`, `_local_date`.
- `backend/hoctap/learning/scoring.py`, `retry.py`, `badges.py`, `progress.py` -- `total_stars`, `due_problem_ids`, `profile_badges`, `attempted_lesson_counts`.
- `backend/hoctap/learning/models.py` -- `progress_sessions` (started/completed, mode), `progress_events` (payload `value`, `correct`, `occurred_at`).
- `backend/hoctap/content/effective.py`, `content/library.py` -- Concept links, Answer Key, visible counts, Book/Unit/Lesson tree.
- `backend/hoctap/api/parent.py`, `app.py` -- guarded router registration.
- `frontend/src/pages/ParentHome.tsx`, `App.tsx`, `api/queries.ts`, `schema.d.ts` -- nav link, route, query, regenerated types.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/learning/metrics.py` -- day/week Sessions+time, accuracy, weak Concepts, recent mistakes, Book/Unit rollup -- one owner of metric definitions
- [x] `backend/hoctap/api/dashboard.py`, `app.py` -- guarded `GET /parent/dashboard/{profile_id}`, typed response -- FR-19
- [x] `frontend/src/pages/Dashboard.tsx` (+ css), `App.tsx`, `ParentHome.tsx`, `queries.ts` -- child selector, two-column on PC, CSS bars, empty states
- [x] `backend/tests/test_dashboard.py`, `frontend/src/pages/Dashboard.test.tsx` -- every I/O row

**Acceptance Criteria:**
- Given the PIN session, when I open the Dashboard for a child, then it shows all FR-19 sections from `learning` data and none of it is recomputed in the page.
- Given two children, when I switch child, then figures belong only to the chosen one.

## Verification

**Commands:**
- `cd backend && ruff check . && pytest tests/test_dashboard.py tests/test_sessions.py tests/test_scoring.py` -- expected: pass
- `cd frontend && npm run gen:api && npx tsc -b && npx eslint . && npx vitest run --pool=vmThreads src/pages` -- expected: pass

## Orchestrator's Independent Audit (2026-10-01)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `_book_progress()` scopes the Dashboard's "Tiến độ theo sách" (progress by Book) section to the Profile's CURRENT grade only. If a parent edits a child's grade after real progress exists on books of the OLD grade, that progress silently disappears from this one Dashboard section (nothing else -- Stars/Streak/accuracy/weak-concepts/recent-mistakes are not grade-filtered and keep counting it correctly) | low | confirmed by 1 reviewer, cosmetic/display-only (no data loss), real but low-severity -> patch: implementer's call -- either show Book progress across every grade the Profile has ever had Sessions in (not just the current one), or explicitly document this as an accepted limitation of a grade change. Low priority, fix only if time allows |
| 2 | No upgrade-path migration test exists for `0017_assignments.py` (the established pattern from prior stories stages a DB at the PRIOR head, upgrades, and inspects the result -- only a fresh-DB-from-scratch test exists here, which wouldn't catch a migration that fails against a pre-existing database) | low | confirmed by 1 reviewer, same class of gap already seen and fixed once before (Story 2.9's `0013_auto_play` backfill test) -> patch: add a `test_migration_0017_up_and_down`-style test matching the established precedent |

## Implementation Notes

- (2026-09-29) `learning/metrics.py` owns every dashboard definition; days are bucketed by a Session's `completed_at` in Asia/Ho_Chi_Minh (the same convention `compute_streak` uses), while time per Session sums `occurred_at` gaps capped at 5 minutes. The week is Monday to Sunday with days after today marked future; weak Concepts use the last 28 days ending today.
- Mistakes are one row per Problem listing each Part whose first attempt was wrong, carrying `problem_id` for Story 4.4's report action. A Problem counts as fallback only when every Part is `fallback`. Retry size is shown as due-today and total-open.
- The repo has no Prettier config; new frontend files were formatted with Prettier defaults by the implementing agent, so their style may differ slightly from older files (eslint is clean).

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_dashboard.py tests/test_sessions.py tests/test_scoring.py tests/test_retry.py tests/test_badges.py tests/test_app.py tests/test_profiles.py` — 191 passed.
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on Dashboard, ParentHome and Settings with `--pool=vmThreads` — 19 passed.
- The implementing agent reported 4 failures in `ExtractionPage.test.tsx` and `ProblemPlayer.speaker.test.tsx` it did not check against a clean tree; earlier stories showed the same failures on unmodified code, but I did not re-run them here. Not run: the full backend and frontend suites in one pass.

### 2026-10-01: fixes from the Orchestrator's Independent Audit

- **Finding #2 (low, done).** Added `backend/tests/test_app.py::test_migration_0017_up_and_down`, matching the established `test_migration_0013_backfills_auto_play_true_for_existing_profiles` precedent: stages a DB at the prior head (`0016_retry_queue_due`) with a pre-existing `progress_sessions` row, upgrades to `0017_assignments`, confirms `progress_assignments` exists and the pre-existing row survives with `assignment_id IS NULL`, downgrades back to `0016_retry_queue_due` and confirms both are gone, then re-upgrades to `head`. (Filed under spec-4-2 since that's where the gap was found, even though `0017_assignments` itself belongs to spec-4-3; the test lives in `test_app.py` alongside the other migration tests, not duplicated into `test_assignments.py`.)
- **Finding #1 (low, deferred).** Not fixed in this pass -- recorded in `deferred-work.md` as agreed (lowest priority, skip if time-constrained). `_book_progress()` still scopes "Tiến độ theo sách" to the Profile's current grade only.
- Verification: `ruff check .` and the targeted/full backend suite runs are the same ones reported in spec-4-3's Implementation Notes (this change only touches `test_app.py`).
