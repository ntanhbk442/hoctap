---
title: 'Story 3.4: Quiz mode for "Phiếu tự luyện cuối tuần"'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: '779dfae2800f78ce9ad180178563aa22005e2cac'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The weekly "Phiếu tự luyện cuối tuần" lesson plays like any practice lesson: Hints, right/wrong feedback and per-Part Stars. Bin cannot see what he knows without help, and the Library never marks the sheet as a quiz. The DB already accepts `mode='quiz'` and `quiz_submitted`, and `is_quiz_sheet` is stored per lesson, but nothing uses them.

**Approach:** A Lesson with `is_quiz_sheet` always starts as a `quiz` Session (server-decided). Attempts are stored ungraded-to-the-child ("Đã lưu"). Posting `quiz_submitted` grades the whole Session in one SAVEPOINT: 3 or 0 Stars per Problem, wrong ones enter the Retry Queue, and the response carries every ✔/↻ plus Solutions for the wrong ones.

## Boundaries & Constraints

**Always:**
- Server-authoritative: a quiz Session's verdicts, Stars and results come only from the `quiz_submitted` response; the client never grades.
- Quiz `attempt` responses expose nothing: `correct`, `wrong_keys`, `hint` and `solution` are null (stored payload keeps the verdict for later grading). The first attempt per Part is its verdict.
- Stars: a Problem with every graded Part right = 3, otherwise 0 (no 1-Star tier). Unanswered = wrong.
- Wrong Problems call `add_retry_item()` at submit (not per attempt); right ones then run `maybe_resolve_retry_item()`. Quiz counts toward Streak and badges (`session_completed` follows submit).
- Retakes (human decision): a Lesson's quiz may be started again, each start a new Session. Stars are awarded only when no earlier Session of that same Lesson has a stored `quiz_submitted`; a retake is still graded, shows ✔/↻ and Solutions, and feeds the Retry Queue, but awards 0 Stars and writes no `progress_stars` rows.
- Leaving partway (human decision): the quiz Session stays open and resumes through the existing Home "Tiếp tục" card (Story 2.11's unfinished-Session lookup); answered Problems are kept and nothing is graded until `quiz_submitted`.
- Grading is idempotent and runs once per Session; new UI copy goes in `frontend/src/audio/phrases.vi.json`; no red/✗/"Sai!".

**Never:** a 💡 button, Hint bubble, FeedbackBanner, StarBurst or correct/wrong dot state in quiz play; per-Part Stars in quiz mode; a client-supplied `quiz` mode field; new DB migration (mode and kind CHECKs already allow both).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start | `lesson` ref with `is_quiz_sheet=1` | Session `mode='quiz'` | N/A |
| Play | `attempt` in quiz | Stored; response has no verdict/hint/solution; UI "Đã lưu" then advances | N/A |
| Help event | `hint_requested`, `solution_shown`, `fallback_revealed` or `self_marked` in quiz | Rejected | 422 `NOT_ALLOWED_IN_QUIZ` |
| Submit | `quiz_submitted` after last Problem | Per-Problem ✔/↻ + Solutions for ↻, 3/0 Stars, wrong queued | N/A |
| Resend / second submit | Same or new id | Stored result returned; no double Stars or retry rows | N/A |
| Unanswered or `fallback` Problem | No graded attempt | ↻ with Solution, 0 Stars, not queued if `fallback` | N/A |
| Non-quiz Session | `quiz_submitted` | Rejected | 422 |
| Retake of a Lesson already quizzed | Earlier Session of the same Lesson has `quiz_submitted` | Graded and queued as usual, 0 Stars, no `progress_stars` rows | N/A |
| Leave mid-quiz, return | Open quiz Session, some Problems answered | Home "Tiếp tục" resumes it; no grading yet | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/sessions.py` -- `start_session`, `_row_to_event_out`, `_validate_event_against_session`, `post_event` (add `quiz_submitted` branch inside the SAVEPOINT); `_grade_and_stage` skips retry/hint/solution for `quiz`.
- `backend/hoctap/learning/scoring.py` -- `STAR_AWARDING_MODES` excludes quiz; add `compute_quiz_stars` and `award_quiz_stars`.
- `backend/hoctap/learning/retry.py` -- `add_retry_item`, `maybe_resolve_retry_item` reused at submit.
- `backend/hoctap/learning/summary.py` -- `compute_summary`/`session_wrong_problem_ids` already give first-try and Stars.
- `backend/hoctap/api/sessions.py` -- `start_session` router forces `quiz` for quiz lessons; event schema exposes `quiz_results`.
- `backend/hoctap/api/library.py`, `backend/hoctap/content/library.py` -- expose `is_quiz_sheet` on `LibraryLesson` (column already in `content_catalog_lessons`).
- `frontend/src/pages/ProblemPlayer.tsx` -- correct/wrong/hint branches in `handleCheck` and the FeedbackBanner/HintBubble/StarBurst render (about lines 470-620); needs a quiz branch.
- `frontend/src/pages/SessionPlayer.tsx` -- posts `session_completed` at true end and renders the summary; add quiz submit step and results screen.
- `frontend/src/components/ProgressDots/ProgressDots.tsx` -- exists but is unused; wire it in with `done`/`current`/`todo` only.
- `frontend/src/pages/Library.tsx`, `LessonDetail.tsx` -- 📝 "Kiểm tra" indicator; LessonDetail has no start button today, so add one for quiz lessons.
- `frontend/src/api/queries.ts`, `schema.d.ts` -- run `npm run gen:api`; add `quiz_submitted` payload/results types.
- `backend/tests/test_sessions.py`, `test_scoring.py`, `test_retry.py`, `test_library.py` -- extend.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/learning/sessions.py` -- quiz gating, scrubbed responses, `quiz_submitted` grading in one SAVEPOINT -- server-authoritative results
- [x] `backend/hoctap/learning/scoring.py` -- quiz 3/0 rule and idempotent award -- AD-6
- [x] `backend/hoctap/api/sessions.py`, `library.py`, `content/library.py` -- forced quiz mode, `is_quiz_sheet` field -- Library indicator
- [x] `frontend/src/pages/ProblemPlayer.tsx`, `SessionPlayer.tsx`, `ProgressDots`, `Library.tsx`, `LessonDetail.tsx`, `phrases.vi.json` -- quiz play, results screen, indicator, copy
- [x] Backend and frontend tests -- cover the I/O matrix and the AC below

**Acceptance Criteria:**
- Given a quiz Session, when Bin checks an answer, then only "Đã lưu" shows, dots fill, and no 💡, banner or Stars appear.
- Given a submitted quiz, when results show, then a Problem with every Part right earns 3 Stars, others 0, wrong ones are due in the Retry Queue from the next calendar day, and the summary Stars match the sum.
- Given a Lesson whose quiz was already submitted, when Bin submits a second quiz Session for it, then results show but no Stars are awarded.
- Given a Problem left the Retry Queue via 2 clean Sessions, when one is a quiz, then it counts (3-Star row exists).

## Design Notes

Mode is derived from the lesson, not sent by the client, mirroring `retry`. The page limit for a quiz Session follows normal 10-Problem chunking. `quiz_submitted` is posted once, after the last Problem of the last chunk and before `session_completed`. Its stored payload holds the results so a resend returns them.

## Verification

**Commands:**
- `cd backend && pytest tests/test_sessions.py tests/test_scoring.py tests/test_retry.py tests/test_library.py` -- expected: pass
- `cd frontend && npm run gen:api && npm test && npm run lint` -- expected: pass

## Implementation Notes

- (2026-09-29) Choices the frozen spec did not settle, made by the implementer:
  - `session_completed` on a quiz Session returns 422 `QUIZ_NOT_SUBMITTED` until `quiz_submitted` is stored, so an ungraded quiz cannot count toward the Streak.
  - Resume is Problem-level: a multi-Part Problem with only some Parts answered counts as attempted on resume, and the unanswered Part is graded wrong at submit.
  - Wrong quiz attempts still count in the Profile-wide prior-wrong tally, so in a later practice Session the first wrong attempt on that Part releases the Solution immediately. Not changed here; worth revisiting if it feels punitive.
  - A `fallback` Part in a quiz shows a plain "Tiep" button; no ProblemPlayer-level test covers it.
  - The bundle now returns `mode`; a quiz bundle's `attempted` counts only that Session's own answers. `quiz_stars_awarded` in the submit response tells the UI whether a retake earned Stars.
- Formatting hunks from running Prettier / `ruff format` on touched files are visible in the diff; unrelated files it touched were reverted.

### 2026-09-29: independent re-verification

- `ruff check .` clean. `pytest tests/test_quiz.py tests/test_library.py` — 38 passed. `pytest tests/test_sessions.py tests/test_scoring.py tests/test_retry.py tests/test_badges.py tests/test_app.py` — 166 passed.
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on SessionPlayer, LessonDetail, Library, Home and `src/offline` with `--pool=vmThreads` — 93 passed (9 files).
- Not run: the full backend and full frontend suites in one pass.
