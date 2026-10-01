---
title: 'Story 4.4: Error reports from the parent and the child'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: 'd2a6498f17b5b5c46287c361f168c81327f5d821'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Content Review already stores, lists and resolves Error Reports (Story 1.8), but nothing in the UI can create one. Anh cannot flag a wrong Problem from the dashboard, and Bin has no 🚩.

**Approach:** Add the two entry points on top of the existing `content.review` service: a parent "Báo lỗi" action, offered on the Dashboard mistakes list, in the Problem editor and on a new read-only parent Problem preview page (hides the Problem until resolved) and a child 🚩 with a "Có" confirm (Problem stays visible, Bin sees "Đã báo cho bố mẹ"). No new table, no new migration, no change to visibility or queue rules.

## Boundaries & Constraints

**Always:** Reports are written only through `content.review.service.add_error_report`. Parent reports use the existing `parent` kind, so `effective.py` already hides the Problem and queues it; child reports use `child`, so it stays visible and is queued. Parent routes sit behind `require_parent`; the child route takes `profile_id`, needs no PIN and validates the Profile. Copy for Bin is positive (no red, no "Sai!"); new spoken text goes in `phrases.vi.json`. The API client stays generated from OpenAPI.

**Also (human decisions):** a read-only parent Problem preview page at `/parent/problems/:problemId`, behind the PIN gate, reusing the existing Review data endpoint for a Problem (no new content endpoint if one exists): it shows the Problem as the parent sees it (label, crop, answer key, Concepts, existing reports) with the "Báo lỗi" button and an optional note, and the Dashboard mistakes rows link to it. After a child reports, the child sees only "Đã báo cho bố mẹ" and play continues; the Problem is not marked in the child's view.

**Never:** New tables or migrations (head stays `0017_assignments`). Changing how `resolve_report`, `Problem` visibility or the queue work. Any way for the child to hide a Problem, read reports, or resolve one. A browsable or searchable Parent Library across Books (only the single-Problem preview page). Adding a note field to the child flag.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parent reports | Problem id, optional note (max 500 chars, trimmed) | Open `parent` report; Problem leaves child selectors; appears in Cần duyệt | Unknown Problem: 404 `PROBLEM_NOT_FOUND` |
| Parent, already open | Open parent report exists | Returns the existing report, no duplicate | N/A |
| Child confirms 🚩 | `profile_id`, Bin taps "Có" | Open `child` report, note empty; Problem stays visible; Bin sees "Đã báo cho bố mẹ" | Unknown Profile: 404 `PROFILE_NOT_FOUND` |
| Child cancels | Bin taps "Không" | Nothing stored, dialog closes | N/A |
| Child flags twice | Open child report exists | Same friendly message, no duplicate row | N/A |
| Reported mid-Session | Parent reports a Problem in a frozen Session | Session stays frozen (AD-9): the Problem is still served in that Session; new Sessions and the Library exclude it (human decision, code review 2026-09-30) | N/A |
| Parent opens preview | Dashboard mistake row linked to `/parent/problems/:id` | Read-only Problem view with answer key, Concepts, existing reports and "Báo lỗi" | Unknown id: not-found state; no cookie: PIN gate |
| Offline child | Flag call fails | Bin sees a neutral "Chưa gửi được, thử lại nhé"; nothing queued | Retry manually |
| Resolved | Report resolved in Review | Problem visible again; dashboard row shows no reported state | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/content/review/service.py` -- `add_error_report`, `resolve_report`, `list_reports` exist; add dedupe of open reports of the same kind and a note length cap.
- `backend/hoctap/content/effective.py` -- already hides on open `parent` reports and queues any open report; no change.
- `backend/hoctap/api/review.py` -- has `POST /reports/{id}/resolve` only; add `POST /parent/review/problems/{problem_id}/reports`.
- `backend/hoctap/api/` (new `flags.py`, registered like `library.py`) -- child `POST /problems/{problem_id}/flag` with `profile_id`.
- `backend/hoctap/learning/metrics.py`, `backend/hoctap/api/dashboard.py` -- `RecentMistake.problem_id` exists; add `reported: bool` (open parent report) read from review state.
- `frontend/src/pages/Dashboard.tsx` -- mistakes list `<li>` gets the "Báo lỗi" action and note input.
- `frontend/src/pages/review/ProblemEditor.tsx` -- already lists reports and resolves them; add the parent report button.
- `frontend/src/pages/ProblemPreview.tsx` (new) + `App.tsx` route `/parent/problems/:problemId` -- read-only preview; reuse the data hook `ProblemEditor` already uses.
- `frontend/src/pages/SessionPlayer.tsx`, `frontend/src/pages/ProblemPlayer.tsx` -- top bar for the 🚩 and "Có/Không" confirm.
- `frontend/src/audio/phrases.vi.json`, `frontend/src/api/client.ts`, `schema.d.ts` -- new phrases; regenerated client and types.
- `backend/tests/test_review.py`, `test_dashboard.py`, `test_app.py` -- existing patterns for reports, dashboard and route tests.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/content/review/service.py` -- dedupe and note cap in `add_error_report` -- one open report per kind per Problem
- [x] `backend/hoctap/api/review.py` -- parent create-report route -- Dashboard and editor entry point
- [x] `backend/hoctap/api/flags.py` (+ router registration) -- child flag route validating the Profile -- no PIN path
- [x] `backend/hoctap/api/dashboard.py`, `learning/metrics.py` -- `reported` on recent mistakes -- show state after reporting
- [x] `frontend/src/pages/ProblemPreview.tsx`, `App.tsx`, `Dashboard.tsx` -- preview page and links from mistakes rows -- the AC's preview surface
- [x] `frontend/src` -- regenerate client; Dashboard report action; ProblemEditor button; player 🚩 with confirm and success/failure message; phrases -- the three UI surfaces
- [x] Backend and frontend tests -- cover every I/O Matrix row, plus the 401 gate on the parent route and no PIN on the child route

**Acceptance Criteria:**
- Given a parent report, when Bin next loads a Session or Library, then that Problem is absent, and it is back after "Đã xử lý" in Review.
- Given a child report, when Bin continues, then the Problem still appears for him and Anh sees it under Cần duyệt marked `child`.
- Given the child UI, when the flag is used, then no red, ✗ or "Sai!" appears.

## Design Notes

Nothing needed from Story 1.8's schema: `kind IN ('parent','child')`, `status IN ('open','resolved')` and the index on `(problem_id, status)` already cover it.

## Verification

**Commands:**
- `cd backend && pytest tests/test_review.py tests/test_dashboard.py tests/test_app.py` -- expected: pass
- `cd frontend && npx vitest run src/pages && npx tsc --noEmit` -- expected: pass (note the known unrelated `ExtractionPage` and `ProblemPlayer.speaker` failures on a clean tree)

## Orchestrator's Independent Audit (2026-10-01)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Fixing a Problem's content via Content Review (Story 1.8's `save` mutation) never auto-resolves an open Error Report on that same Problem -- `resolve_report()` is only ever called by the explicit "Đã xử lý" action, a completely separate mutation in `ProblemEditor.tsx` with no link between the two. A parent who reports a Problem, opens the editor, fixes the wrong answer key, and saves -- but forgets to separately click "Đã xử lý" -- leaves the Problem hidden from the child and stuck in "Cần duyệt" indefinitely, with the content now actually correct | medium | confirmed by 1 reviewer, a real and easy-to-hit workflow trap | -> patch: implementer's call on the exact mechanism, but the two most reasonable options are (a) auto-resolve any open report on a Problem when its content is saved with a changed `content_hash` (the same hash the report's own `content_hash` dedup logic already tracks), or (b) at minimum, show a visible prompt/reminder in the editor's save-success state when an open report exists for this Problem, so the parent doesn't forget. Document whichever is chosen |

## Implementation Notes

- (2026-09-30) `add_error_report` now trims/NFC-normalises the note, rejects over 500 characters (422 `NOTE_TOO_LONG`) and returns the existing open report for a repeat of the same kind. Parent route `POST /parent/review/problems/{id}/reports` sits behind the PIN gate; child route `POST /problems/{id}/flag` (new `api/flags.py`) takes `profile_id` and only ever writes an open `child` report.
- Behaviour change beyond the spec: the Dashboard mistakes list used to drop a Problem once it was hidden; a parent-reported Problem now keeps its row marked `reported` ("Đã báo lỗi") until the report is resolved. Hidden-for-other-reasons or conflicted Problems are still skipped.
- New `ProblemPreview.tsx` (route `/parent/problems/:problemId`) reuses the Review data hook; Concepts show as raw `concept_id` strings because that endpoint has no name lookup. `FlagButton` lives in `components/FlagButton/`, but its test sits in `src/pages/FlagButton.test.tsx` because vitest workers fail to start for tests under `src/components/` in this WSL setup.
- Not seen in a running browser: the preview page, the flag bar and the report form (which has no styling of its own).

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_review.py tests/test_dashboard.py tests/test_app.py tests/test_sessions.py tests/test_assignments.py tests/test_library.py` — 220 passed (the implementing agent also reported the full backend suite at 950 passed).
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on Dashboard, ProblemPreview, FlagButton, SessionPlayer and `src/pages/review` with `--pool=vmThreads` — 66 passed (8 files).
- Not run: the full frontend suite in one pass.

### 2026-10-01: fix from the Orchestrator's Independent Audit

- **Finding #1 (medium, done).** Chose option (a) -- auto-resolve, not a reminder banner. `content.review.service.save_overrides()` now calls the new `_auto_resolve_reports_on_content_change()` whenever the save actually added/changed/removed an override (`removed or changed` is non-empty): it recomputes the Problem's effective `content_hash` after the write and, if it differs from the hash captured at the start of the call (the same hash `approve()`'s own STALE check already treats as "what Anh is currently looking at"), resolves every OPEN report (both `parent` and `child` kind) on that Problem via the existing `resolve_report()`.
  - Reasoning: option (b) (a reminder prompt) still requires the parent to remember and take a SECOND action -- exactly the trap the finding describes, just with a nicer nudge. Auto-resolving on an actual content change removes the trap outright: there is no scenario left where "the content is now correct" and "the report is still open" can coexist after a save. The guard against a no-op save (reverting to the extracted value, which hits `save_overrides()`'s existing `value_hash(value) == value_hash(base)` early-continue and keeps `removed`/`changed` empty) means a report is never resolved by a save that didn't actually change anything -- it only fires when the effective hash genuinely moved. No new schema/column was needed: the comparison reuses `EffectiveProblem.content_hash`, computed fresh before and after the write within the same transaction, rather than storing a hash on the report row itself.
  - Test: `backend/tests/test_review.py::test_save_overrides_auto_resolves_open_report_on_content_change` -- opens a `parent` report, saves a no-op edit (same value as extracted) and asserts the report stays open and the Problem stays hidden, then saves a real content fix and asserts the SAME report id is now `resolved` with a `resolved_at`, and the Problem is visible again and off the review queue.
- Verification: `ruff check .` clean. `pytest tests/test_review.py tests/test_assignments.py tests/test_sessions.py` -- all passed (see spec-4-3's Implementation Notes for the combined run). Full backend suite run once at the end of this pass. Not touched: any frontend file for this finding (the fix is entirely in the write path; `ProblemEditor.tsx`'s existing "Đã xử lý" button and report list need no change -- the returned `ProblemDetail` after a save already carries the now-resolved report's status, exactly like any other `onDetail()` refresh).
