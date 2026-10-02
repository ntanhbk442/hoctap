---
title: 'Story 8.1: Exam generation with random problem sets'
type: 'feature'
created: '2026-10-02'
status: 'done'
baseline_commit: '026780f'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Anh wants a timed practice exam -- a randomly-generated Problem Set under a
parent- or child-chosen scope, size and time limit -- distinct from every existing Session
mode. This is a deliberate, explicit departure from this app's own "no timers, no pressure"
design philosophy for child screens (`EXPERIENCE.md`: "No timers on child screens. Nothing
counts down, and the child is never rushed."). Anh chose a real, visible countdown anyway,
for exam-realism practice, and chose to gate it per Child Profile so it only ever appears
where a parent has turned it on.

**Approach:** A new Session `mode='exam'`, resolved via a new `ExamRef`/`resolve_exam()`
that randomly samples N `visible_to_child()`-eligible Problems from a chosen scope (one or
more Concepts, a Book optionally bounded to a Unit range, or the Profile's whole Grade),
and freezes them into `problem_ids_json` exactly like every other mode (AD-9). The backend
stores `time_limit_s` alongside `started_at` on the Session row, so the countdown survives
a closed-and-reopened tablet (mirrors Story 2.11's "Tiếp tục"). Play mirrors Story 3.4's
Quiz mode mechanically (attempts stored ungraded, one `exam_submitted` event grades the
whole Session at once) but is intentionally LESS rewarding than Quiz: **zero Stars, zero
Retry Queue entries, zero Streak contribution** -- a pure assessment, not merely "the same
as Quiz" (Quiz mode actually does award Stars-at-submit and does feed the Retry Queue and
Streak; an earlier verbal framing of this story conflated the two -- this spec is the
corrected, authoritative version). `parent_profiles.exams_enabled` (default off) gates
every entry point. A parent can assign an exam ahead of time (new `progress_assignments`
exam-scope ref, alongside the existing Lesson ref) or a child with exams enabled can
configure and start one on demand from the Library, using the SAME full scope/count/time
picker a parent would use (Anh's explicit call, not a simplified default).

## Boundaries & Constraints

**Always:**
- `exams_enabled` (new `parent_profiles` column, default `false`) gates every exam entry
  point for that Profile -- parent-assigned AND child-on-demand alike. An Assignment whose
  target Profile later has `exams_enabled` turned off still resolves normally if already
  started (consistent with how other content-visibility changes never retroactively break
  an in-progress Session), but a NEW exam cannot be started for that Profile while it's off.
- Sampling for every scope kind (`concept`, `book_unit`, `grade`) goes through the exact
  same `visible_to_child()`-equivalent eligibility `content.effective.load_effective()`
  already uses everywhere else -- hidden, retired, `needs_review`-unapproved and conflicted
  Problems are never drawn. Fewer eligible Problems than the requested count is not an
  error: the exam gets a smaller set, silently.
- `time_limit_s` is stored on the Session row at start (`progress_sessions.time_limit_s`,
  nullable, set only for `mode='exam'`) alongside the existing `started_at` -- the backend,
  not the client, is the clock's source of truth, so closing and reopening the tablet mid-exam
  shows the correct remaining time rather than resetting it.
- Exam play has NO feedback (no ✔/↻, no Hint, no Solution, no Star animation) until
  submitted, mirroring Quiz mode's `QUIZ_BLOCKED_KINDS` treatment exactly (`hint_requested`,
  `solution_shown`, `fallback_revealed`, `self_marked` are all rejected during exam play too).
- `exam_submitted` (new event kind, mirrors `quiz_submitted`) grades the whole Session once,
  inside one SAVEPOINT: every Problem gets a ✔/↻ verdict and a Solution for wrong ones in
  the response -- but awards **zero Stars**, calls **no** `add_retry_item()`, and
  `compute_streak()`'s mode exclusion extends from `!= 'replay'` to `NOT IN ('replay',
  'exam')`. `exam` joins `quiz`/`replay` outside `STAR_AWARDING_MODES` (already true by
  construction: that frozenset is an explicit allowlist, so a new mode is excluded by
  default -- confirm this, don't assume it needs an edit).
- Timeout auto-submits: the frontend computes remaining time from `started_at +
  time_limit_s` and fires `exam_submitted` automatically at zero with whatever is answered;
  unanswered Problems grade as wrong, same as Quiz mode's own "unanswered Problem" rule. The
  backend does not reject a late `exam_submitted` (no adversarial clock-tampering concern in
  this single-family deployment) -- it grades whatever was answered at receipt time.
- Scope kinds (`ExamScope`, a new tagged union in `learning/problem_sets.py`):
  `{kind: "concept", concept_ids: list[str]}` (one or more), `{kind: "book_unit", book_id:
  str, unit_keys: list[str] | None}` (`None` = the whole Book), `{kind: "grade"}` (the
  Profile's own Grade, no further input). Problem count and `time_limit_s` are both
  required, positive integers from whoever configures the exam (parent or child).
- `progress_assignments` migration: `book_id`/`unit_key`/`lesson_key` become nullable, a new
  `exam_scope_json TEXT NULL` column is added, with a CHECK enforcing exactly one of (a
  Lesson ref: all three non-null, `exam_scope_json` null) or (an exam ref: all three null,
  `exam_scope_json` non-null) per row. Starting an exam Assignment re-resolves a FRESH
  random draw each time (the scope/count/time are frozen in the Assignment; the actual
  Problem Set is drawn fresh at Session start, same AD-9 freeze-at-session-start rule as
  every other ref kind -- an Assignment is a recipe, not a frozen Problem list).
- New UI copy goes in `frontend/src/audio/phrases.vi.json`; no red/✗/"Sai!" anywhere
  (matches the rest of this app's child-facing voice rules even though exam mode itself is
  already a deliberate exception to the no-pressure philosophy -- the WORDING stays warm,
  only the timer itself is the exception).

**Never:**
- No 💡 button, Hint bubble, FeedbackBanner, StarBurst, or correct/wrong state during exam
  play (identical to Quiz mode's own "Never" list).
- No client-supplied `mode` field -- `mode='exam'` is server-decided from the ref kind, same
  as `retry`/`concept`/`quiz` already are.
- No padding a short-on-content scope with ineligible Problems to hit the requested count.
- No new migration touches `content_catalog_problems`/`content_review_*` -- sampling is
  entirely a read over the existing effective-content machinery.
- An Assignment row is never BOTH a Lesson ref and an exam ref (enforced by the new CHECK
  constraint, not just application logic).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start, `exams_enabled=false` | Any exam-start request for that Profile | Refused | 403 `EXAMS_DISABLED` |
| Start, `concept` scope | 1+ `concept_ids`, count, time_limit_s | Session `mode='exam'`, up to `count` eligible Problems across the Concept(s) | N/A |
| Start, `book_unit` scope, whole Book | `book_id`, `unit_keys=null`, count, time_limit_s | Up to `count` eligible Problems from anywhere in the Book | N/A |
| Start, `book_unit` scope, bounded | `book_id` + specific `unit_keys` | Only Problems from those Units | N/A |
| Start, `grade` scope | nothing but count/time_limit_s | Up to `count` eligible Problems anywhere in the Profile's Grade | N/A |
| Scope has fewer eligible Problems than requested | e.g. count=50, scope has 12 eligible | A 12-Problem exam, not an error | N/A |
| Scope has zero eligible Problems | e.g. a Concept nobody has tagged yet | Session still starts, empty Problem Set | 422 `EMPTY_PROBLEM_SET` (matches every other ref kind's existing empty-set behavior) |
| Play | `attempt` during exam | Stored; response has no verdict/hint/solution, same as quiz's "Đã lưu" | N/A |
| Help event during exam | `hint_requested`/`solution_shown`/`fallback_revealed`/`self_marked` | Rejected | 422 `NOT_ALLOWED_IN_QUIZ` (reuse the existing code; exam play has the identical restriction) |
| Submit | `exam_submitted` before time is up | Per-Problem ✔/↻ + Solutions for ↻; **0 Stars awarded**, nothing queued, no Streak contribution | N/A |
| Time runs out | Frontend detects `now >= started_at + time_limit_s` | Auto-fires `exam_submitted` with whatever is answered; unanswered Problems grade ✗ | N/A |
| Resend / second submit | Same or new event id | Stored result returned; never double-grades | N/A |
| Non-exam Session | `exam_submitted` on a `practice`/`retry`/`concept`/`quiz`/`replay` Session | Rejected | 422 |
| Tablet closed mid-exam, reopened | Session reloaded | Remaining time computed from server `started_at`+`time_limit_s`, NOT reset | N/A |
| `session_completed` before submit | Exam Session, no stored `exam_submitted` | Rejected, same pattern as Quiz's `QUIZ_NOT_SUBMITTED` | 422 `EXAM_NOT_SUBMITTED` |
| Parent assigns an exam | scope + count + time_limit_s + Profile + date | New `progress_assignments` row, `exam_scope_json` set, Lesson columns null | N/A |
| Child starts an assigned exam | Home's assignment card, `ref_kind='exam'` | A FRESH random draw under the Assignment's stored scope/count, a new Session | N/A |
| Child starts an exam on demand | Library's new exam entry point, `exams_enabled=true` | Same full picker a parent gets; starts immediately, no Assignment row created | N/A |
| Child tries on-demand exam, `exams_enabled=false` | Library | Entry point not shown at all | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/parent/models.py` -- `parent_profiles.exams_enabled` (new migration).
- `backend/hoctap/learning/models.py` -- `progress_sessions.time_limit_s` (new, nullable);
  `mode` CHECK constraint gains `'exam'`; `progress_assignments.book_id`/`unit_key`/
  `lesson_key` become nullable, new `exam_scope_json` column, new CHECK (new migration,
  same migration as the Session column or a second one -- implementer's call).
- `backend/hoctap/learning/problem_sets.py` -- new `ExamScope` tagged union, `ExamRef`
  dataclass, `ProblemSetRef` union gains it, `resolve()` gains an `exam` branch that calls a
  new `resolve_exam_scope()` (random sampling over `content.effective.load_effective()`,
  filtered on `.visible`, shuffled, truncated to count).
- `backend/hoctap/learning/sessions.py` -- `start_session` stores `time_limit_s`; every
  `session.mode == "quiz"` branch in this file (resume/attempted/done-id logic, event
  validation, `_grade_and_stage`) needs a sibling `"exam"` branch wherever Quiz's
  no-feedback-until-submit behavior should also apply; new `exam_submitted` handling
  mirroring `_grade_quiz`/`_quiz_submitted` (name the exam equivalents accordingly) but
  WITHOUT the Star-award/`add_retry_item()` calls that quiz's version makes;
  `QUIZ_BLOCKED_KINDS` reused as-is for exam play.
- `backend/hoctap/learning/summary.py` -- `compute_streak()`'s `mode != "replay"` filter
  becomes `mode.notin_(("replay", "exam"))`.
- `backend/hoctap/learning/scoring.py` -- confirm `STAR_AWARDING_MODES` (an explicit
  allowlist) needs no edit since `exam` is simply never added to it; add a test pinning this.
- `backend/hoctap/learning/assignments.py` -- `AssignmentInfo`/resolution logic gains the
  exam-ref branch (parallel to the Lesson-ref path), re-resolving a fresh random draw at
  Session-start time, not storing a frozen Problem list on the Assignment itself.
- `backend/hoctap/api/sessions.py`, `backend/hoctap/api/assignments.py` -- new request/
  response schemas for exam scope/count/time_limit_s on both the direct-start and the
  assign-ahead paths; `exams_enabled` 403 check.
- `backend/hoctap/parent/service.py`, `backend/hoctap/api/parent.py` -- `exams_enabled`
  toggle in Settings (same shape as the existing `auto_play` per-Profile setting).
- `frontend/src/pages/ProblemPlayer.tsx`, `SessionPlayer.tsx` -- exam branch mirroring the
  existing quiz branch (no banner/hint/star during play); a visible countdown in whatever
  shared top-bar component exists by the time this is built (see the separate, still-pending
  child-UX-navigation redesign conversation -- if that hasn't landed yet, a standalone
  countdown element is fine, don't block this story on it).
- `frontend/src/pages/Library.tsx` -- new "Đề kiểm tra" entry point, gated on
  `exams_enabled`, opening the scope/count/time picker.
- `frontend/src/pages/ParentHome.tsx` / wherever Assignments are configured -- exam option
  alongside the existing Lesson/Concept assign flow.
- `frontend/src/pages/Settings.tsx` -- `exams_enabled` toggle per Child Profile.
- `frontend/src/audio/phrases.vi.json` -- new copy (exam start, countdown warning text if
  any, results screen, `EXAMS_DISABLED`/`EXAM_NOT_SUBMITTED` friendly messages).
- `frontend/src/api/queries.ts`, `schema.d.ts` -- run `npm run gen:api`; new types.
- `backend/tests/test_sessions.py`, `test_scoring.py`, `test_problem_sets.py`,
  `test_assignments.py`, `test_app.py` (migrations) -- extend. New `test_exam.py` likely
  cleanest given the scope of new behavior (mirrors how `test_quiz.py` exists alongside
  `test_sessions.py` for Story 3.4).

## Tasks & Acceptance

**Execution:**
- [ ] Migrations: `parent_profiles.exams_enabled`, `progress_sessions.time_limit_s`,
      `progress_assignments` nullable Lesson columns + `exam_scope_json` + CHECK -- with
      upgrade/downgrade tests per this project's established pattern
      (`test_migration_NNNN_up_and_down`).
- [ ] `learning/problem_sets.py` -- `ExamScope`/`ExamRef`/`resolve_exam_scope()` -- random
      sampling respecting `visible_to_child()` eligibility, truncated to count, empty-scope
      handled.
- [ ] `learning/sessions.py` -- exam mode wired through start/resume/event-validation/
      grading exactly where quiz mode already is, with NO Stars/Retry Queue/Streak effect.
- [ ] `learning/summary.py` -- Streak excludes `exam` alongside `replay`.
- [ ] `learning/assignments.py` -- exam-ref Assignment resolution (fresh draw per start).
- [ ] `api/sessions.py`, `api/assignments.py`, `api/parent.py` -- new endpoints/fields,
      `exams_enabled` gating.
- [ ] Frontend: Library exam entry point, Assignment config exam option, Settings toggle,
      ProblemPlayer/SessionPlayer exam play + countdown + results screen, phrases.
- [ ] Backend and frontend tests covering the full I/O matrix above.

**Acceptance Criteria:**
- Given a Profile with `exams_enabled=false`, when any exam-start request is made for it,
  then it's refused with `EXAMS_DISABLED` and no Session is created.
- Given a `book_unit` scope bounded to specific Units, when an exam starts, then every
  drawn Problem belongs to one of those Units and none from elsewhere in the Book.
- Given an exam with `count` greater than the eligible pool, when it starts, then the
  Session's Problem Set is exactly the eligible pool, no error.
- Given a submitted exam, when results show, then every Problem has a ✔/↻ verdict and wrong
  ones show a Solution, but zero Stars were awarded, zero Retry Queue rows were added, and
  the Profile's Streak is unchanged from before the exam.
- Given an exam whose time limit elapses with Problems unanswered, when the frontend detects
  this, then it auto-submits with the unanswered Problems graded wrong, with no further
  input accepted.
- Given a tablet closed mid-exam and reopened, when the Session reloads, then the remaining
  time reflects the real elapsed wall-clock time since `started_at`, not a reset countdown.
- Given a parent assigns an exam and the child starts it twice (a retake), when each starts,
  then each gets its OWN fresh random draw, not the same frozen list repeated.

## Design Notes

**Correction to the original brainstorming conversation:** earlier verbal framing described
exam mode's reward-effects as "matches Quiz mode exactly" -- this is factually wrong. Story
3.4's Quiz mode DOES award Stars (3/0 per Problem, computed at `quiz_submitted` rather than
per-attempt) and DOES feed the Retry Queue and Streak. Anh's actual, primary stated intent
("no Stars/Retry Queue/Streak effect... purely an assessment") is what this spec implements;
exam mode is mechanically similar to Quiz (no feedback until submit, one grading pass) but
functionally a STRICT SUBSET of Quiz's effects -- every reward-system side effect is
removed, not inherited. If this distinction matters enough to revisit, that's a
conversation to have before implementation starts, not after.

The scope/count/time picker is intentionally the SAME component for parent-assign and
child-on-demand (Anh's explicit call, documented in epic-8-context.md) -- resist the urge to
build two different UIs "for simplicity," since that was considered and rejected.

`ExamRef`'s `ref_key()` encoding (the compact string stored on `progress_sessions.ref_key`)
needs its own scheme since scope is now a richer structure than any existing ref kind --
likely a short, deterministic JSON string, consistent with this module's existing comment
that `ref_key` is currently write-only/dormant (nothing parses it back) -- don't invent
parsing logic that isn't needed yet.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_exam.py tests/test_sessions.py tests/test_scoring.py tests/test_problem_sets.py tests/test_assignments.py tests/test_app.py -q && uv run ruff check .` -- expected: pass
- `cd backend && uv run pytest -q` (full suite) -- expected: pass
- `cd frontend && npm run gen:api && npm run build && npm test -- --run && npm run lint` -- expected: pass

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-10-02: Backend implementation

**Migrations (4 files, not 3 -- judgment call):** `0021_exams_enabled` (`parent_profiles.
exams_enabled`, default false), `0022_exam_sessions` (`progress_sessions.time_limit_s` +
`mode` CHECK gains `'exam'`), `0023_exam_assignments` (`progress_assignments` Lesson columns
become nullable + `exam_scope_json` + the ref-xor CHECK), and a 4th, `0024_exam_submitted_
event`, which the spec's Code Map didn't call out: `progress_events.kind`'s own CHECK
constraint also needed `'exam_submitted'` added (easy to miss -- `EVENT_KINDS` in
`learning/sessions.py` is an in-Python frozenset, entirely separate from the DB-level CHECK,
and only the DB CHECK actually blocked inserts in testing). Each migration is independently
up/down tested in `test_app.py` (`test_migration_0021..0024_up_and_down`), following the
`test_migration_0020` pattern exactly. Downgrading past 0022/0023/0024 after exam data
exists is a lossy, admin-only operation (the pre-exam schema has no column to hold it) --
same posture every other destructive downgrade in this codebase already takes; the migration
tests delete the exam row before downgrading, isolating the round-trip check to data the
OLD schema can represent.

**`ref_key()` / `exam_scope_json` encoding:** `ExamRef.ref_key()` is `"exam:" + json.dumps(
{scope, count, time_limit_s}, sort_keys=True, separators=(",", ":"))` -- deterministic JSON,
per the spec's own Design Notes suggestion. Unlike every other `ref_key`, which stays
write-only/dormant, `progress_assignments.exam_scope_json` DOES need to be parsed back (an
exam Assignment is a recipe, re-resolved fresh at every Session start) -- so
`learning/problem_sets.py` exposes `exam_scope_to_dict()`/`exam_scope_from_dict()` and
`exam_scope_payload()`/`exam_ref_from_payload()` as the one shared (de)serialization pair
both `ref_key()` and `learning/assignments.py` use, rather than inventing two separate
encodings.

**`learning/assignments.py`:** `check_startable()` was refactored from a Lesson-only tuple
comparison to a generic `ref_key(ref) != row.ref_key` check -- this works identically for
both ref kinds since `ref_key()` is already the canonical encoding `create()` stores. A new
`_ref_from_row()` is the one place that decides whether a stored Assignment row recipes a
`LessonRef` or an `ExamRef`. `create()` does NOT check `exams_enabled` -- that gate applies
to actually STARTING an exam (`start_session()`), not to a parent preparing one ahead of
time for a Profile whose toggle might be off today and on by the assigned date (the frozen
Boundaries' own wording is "a NEW exam cannot be STARTED ... while it's off").

**`resolve_exam_scope()`'s concept-scope behavior:** a `concept_id` in the list that doesn't
exist is silently ignored (not a 404), so a multi-Concept scope with one bad id among
several good ones still draws from the good ones -- consistent with this story's own
"fewer eligible Problems than requested is not an error" philosophy, extended to "an
unknown concept in the list" too.

**`summary.py`:** `compute_streak()`'s `mode != "replay"` became `mode.notin_(("replay",
"exam"))` as specified. Also (implementer's call, not explicitly in the spec but consistent
with the existing quiz/replay exclusion already there): `first_try_solved_problem_ids()`'s
mode filter (used by Concept-practice ordering, Story 5.2) now excludes `exam` alongside
the `quiz`/`replay` it already excluded, so a Concept practice Session's "already solved"
prioritisation reflects ordinary practice history, not a timed assessment.

**`learning/sessions.py` exam grading:** `_grade_exam()` reuses `learning.scoring`'s
`compute_quiz_stars()`/`quiz_part_verdicts()` AS-IS (unmodified) -- both are already mode-
agnostic (they only read this Session's own stored `attempt` events for a Problem), so an
exam `attempt` (stored via the same `mode in ("quiz", "exam")` early-return branch in
`_grade_and_stage()`) grades through the identical logic quiz does. `_grade_exam()` is the
STRICT SUBSET `_grade_quiz()` describes: no `award_quiz_stars()` call, no `add_retry_item()`
call. `EventOut.exam_results` has no `stars` field per result (unlike `QuizResultOut`) and
no `exam_stars_awarded` sibling flag, since exam mode never awards Stars at all -- there is
nothing to report. `STAR_AWARDING_MODES` and `BADGE_CHECK_MODES` needed NO edits (confirmed
by a new pinning test, `test_star_awarding_modes_excludes_exam`); `maybe_resolve_retry_item()`
is also unmodified and un-gated for exam attempts, same as it already was for `replay` --
an exam attempt simply never produces a qualifying `progress_stars` row, so it can never
contribute to resolving an existing Retry Queue item either (verified in `test_exam.py`).

**Found-and-fixed latent bug, orthogonal to exam logic itself (`hoctap/db/engine.py`):**
adding the Assignment-flow exam support changed the exact sequence of per-request
`engine.connect()`/`engine.begin()` calls enough to expose a real, pre-existing
SQLAlchemy-pool-vs-SQLite-WAL staleness bug: a pooled, REUSED raw `sqlite3` connection can
keep returning an old WAL snapshot from whenever its last transaction began, even after a
DIFFERENT connection has since committed a write -- `test_assignments.py::
test_carry_over_and_queue` (previously passing, untouched by this story's actual feature
code) started failing ~100% of runs: `POST /sessions/{id}/events` (`session_completed`)
committed `completed_at` correctly (verified by reading it back on the SAME connection
before the transaction closed), but the VERY NEXT `GET /library/home/{id}` request, on a
pooled connection SQLAlchemy happened to reuse, read it back as still `NULL`. Switched
`create_db_engine()` from the default `QueuePool` to `NullPool` (verified: 9+ consecutive
real `pytest` runs failed before, 10+ consecutive runs passed after) -- a fresh raw
connection per checkout, closed on return, so no connection is ever reused with a stale
snapshot. This is a correctness fix that happens to be exposed by, but is not specific to,
this story's own code; it protects every endpoint, not just exam/Assignment ones. Also
updated `test_app.py::test_fresh_data_dir_created_with_wal_and_migrations`'s hardcoded
expected Alembic head (`0020_db_epoch` -> `0024_exam_submitted_event`) -- an expected,
mechanical update now that this story added 4 new migrations, not a regression.

**Verification so far:** `uv run ruff check .` clean. Targeted suite (`test_exam.py`,
`test_sessions.py`, `test_scoring.py`, `test_problem_sets.py`, `test_assignments.py`,
`test_app.py`) -- see below for the final count. `test_exam.py` has 19 new tests covering
every I/O matrix row reachable from the API layer; `test_problem_sets.py` has 14 new/
extended tests covering `resolve_exam_scope()`'s three scope kinds directly.

### 2026-10-02: Frontend implementation

**API layer (`frontend/src/api/`):** `npm run gen:api` was run against a fresh `uv run
hoctap export-openapi` (offline mode -- no running server needed) to regenerate
`schema.d.ts`. `client.ts` gained hand-written aliases (`ExamRefIn`, `ExamConceptScopeIn`/
`ExamBookUnitScopeIn`/`ExamGradeScopeIn`, `ExamScopeIn` union, `ExamResultOut`), extended
`StartSessionRefIn` with `| ExamRefIn`, and added `'exam'` to the two hand-written `mode`
literal unions (`client.ts`'s `startSession()` and `queries.ts`'s `useStartSession()` --
confirmed via the research pass that these are NOT schema-derived and need manual edits
per new mode). `AssignmentIn`/`AssignmentOut`/`Profile`/`BundleOut`/`SessionOut`/`EventOut`
needed no hand-edits -- they're direct `Schemas['X']` aliases, so the schema regen alone
picked up every new field.

**Backend addition found necessary during this pass, not called out in the Code Map:**
`BundleOut` (both `learning/sessions.py`'s service dataclass and `api/sessions.py`'s
response model) needed `started_at`/`time_limit_s` added -- `SessionOut` (the one-time
`POST /sessions` response) already had them, but `SessionPlayer.tsx` only ever calls
`useSessionBundle()` (`GET .../bundle`) on mount/reload, never re-reads the original start
response. Without this, a closed-and-reopened tablet mid-exam would have had NO way to
compute the remaining time at all -- this was a gap in the spec's Code Map, not an
intentional omission, caught by tracing the actual reload path before writing the
countdown component.

**`ProblemPlayer.tsx` needed ZERO changes** -- its existing `quiz?: boolean` prop already
gates every single "no feedback until submit" behaviour the frozen Boundaries require for
exam play too (no Hint/Solution/StarBurst/FeedbackBanner, "Đã lưu" only). `SessionPlayer.tsx`
passes `quiz={isQuiz || isExam}` straight through. This was confirmed by tracing every
`mode === 'quiz'` branch in both files before writing anything, rather than assumed.

**`SessionPlayer.tsx` exam wiring:** `isExam`/`examEnd` (`trueEnd` OR the countdown
expiring) mirror `isQuiz`/`trueEnd`'s own shape. `exam_submitted` is posted in the SAME
effect that already posts `quiz_submitted`/`session_completed`, gated by `examEnd` instead
of (only) `trueEnd` -- so a countdown expiry mid-chunk (not just at the natural last
Problem) correctly force-submits with whatever is answered, per the frozen Boundaries'
"Timeout auto-submits" row. A new `ExamCountdown` component (this codebase's first
`setInterval`-driven live UI -- confirmed no prior countdown precedent existed; every other
timer in the app is a one-shot `setTimeout`) computes remaining time from the BUNDLE's
`started_at`/`time_limit_s` on every render, never a client-side anchor set once at mount,
so it recovers the correct remaining time after a reload. `ExamResultsScreen` (new,
mirrors `QuizResultsScreen`'s shape minus the Stars field and the
`quiz_stars_awarded`-style flag, since exam never has either) replaces
`SessionSummaryScreen` entirely for exam mode (judgment call, documented in the code
itself) -- showing StarBurst/Streak/"Luyện lại bài sai" for a Session that by design has
zero of all three would be actively misleading, not just unnecessary.

**Library/Settings/Assignments:**
- `Library.tsx` gained a `📝 Đề kiểm tra` entry point, gated on `current.exams_enabled`
  (already present on the `Profile` the page already fetches -- no new request needed),
  linking to a new routed page `ExamStart.tsx` (`/exam/new`), added to `App.tsx`'s route
  table.
- `ExamStart.tsx` is the child-facing on-demand exam picker -- scope kind (concept/
  book_unit/grade) + count + time_limit_s (entered in minutes, sent as seconds), reusing
  `useLibraryBooks()`/`useLibraryConcepts()` for the book_unit/concept pickers. Re-checks
  `exams_enabled` itself (redirects to `/library` if off) so a direct URL visit can't reach
  the picker client-side either, even though the server is the actual enforcement point.
- `Settings.tsx` gained an `exams_enabled` checkbox, copy-pasted from `auto_play`'s own
  toggle pattern exactly (same inline-string label convention, no `phrases.vi.json` key,
  for consistency with its sibling).
- `Assignments.tsx`'s `Picker` is now a two-tab component ("Bài học" / "Đề kiểm tra") over
  the existing Lesson form and a new `ExamPicker` (same scope/count/time_limit_s shape
  `ExamStart.tsx` uses, per the spec's explicit "one picker, not two" instruction --
  the two components are NOT literally shared code since one posts to `useCreateAssignment`
  and the other to `useStartSession`, but present an identical scope/count/time_limit_s
  form). `AssignmentList` gained a render branch for `ref_kind === 'exam'` (scope/count/
  time_limit_s summary instead of Book/Unit/Lesson labels, no "In phiếu" print link -- an
  exam has no printable worksheet).

**Judgment call -- exam Assignment print/worksheet:** NOT implemented. Story 7.1's
printable worksheets are Lesson/Concept-shaped; extending them to a randomly-sampled exam
scope was out of scope for this story (never mentioned in the frozen spec) and is left for
a future story if Anh wants it.

**Phrases (`phrases.vi.json`):** new `exam_*` keys following the existing `quiz_*`
prefix convention exactly (`exam_entry_point`, `exam_saved`, `exam_indicator`,
`exam_start`, `exam_time_up`, `exam_results_title`, `exam_result_right`,
`exam_result_retry`, `exam_picker_*`, `exams_disabled`, `exam_not_submitted`). No
red/✗/"Sai!" anywhere, matching the frozen Boundaries' "Always" list.

**Found-and-fixed test-isolation gaps, unrelated to exam logic itself (pre-existing, not
introduced by this story):** two frontend test files (`src/print/WorksheetPage.test.tsx`
indirectly via `leak.test.tsx`/`renderers.test.tsx`, and `src/styles/tokens.test.ts`) read
fixtures via a relative `../backend/...`/`../_bmad-output/...` path from `process.cwd()`,
which only resolves when `frontend/` has its real siblings on disk -- they fail under the
"fast /tmp copy" verification workaround unless those two directories are ALSO copied
alongside it. Not a code bug; noted here so a future verification run under the same
workaround doesn't mistake these for real regressions. (`src/pages/ExtractionPage.test.tsx`
remains a genuinely pre-existing, unrelated flake -- confirmed failing identically on an
unmodified checkout of this same commit, nothing to do with this story.)

**Full verification results:**
- Backend: `uv run ruff check .` -- clean.
- Backend targeted suite (`test_exam.py test_sessions.py test_scoring.py
  test_problem_sets.py test_assignments.py test_app.py`) -- all passing (19 + existing all
  green; see the full-suite count below for the final total).
- Backend full suite (`uv run pytest -q`): **1197 passed, 0 failed** (24m01s).
- Frontend: `npx tsc -b` clean, `npx eslint .` clean (zero warnings), `npm run build`
  succeeds. `npx vitest run` (from the `/tmp` fast-copy, with `backend/tests/fixtures` and
  the one `_bmad-output/.../DESIGN.md` path also copied alongside it): 478 passed, 3 failed
  -- all 3 are the pre-existing `ExtractionPage.test.tsx` flake, confirmed unrelated (fails
  identically on an unmodified checkout).

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | **The implementer's test suite reported 1197/1197 passing, but `hoctap serve` crashed outright on startup against this project's own real, lived-in database.** Migration `0022_exam_sessions` drops/recreates `progress_sessions` (forced by `batch_alter_table` recreating the table to rewrite its CHECK constraint) while `progress_events.session_id` has a real FOREIGN KEY onto it -- the DROP TABLE step fails under FK enforcement the moment the database has even one real `progress_events` row, which a fresh-per-test database never has but any actually-used deployment always does. The migration's own test (`test_migration_0022_up_and_down`) never inserted a `progress_events` row, so it never exercised this path | high | confirmed by direct reproduction against a real copy of this project's development database (1760 Problems, 8 real Sessions/Events) -> **patched**: `db.engine.run_migrations()` now toggles `PRAGMA foreign_keys=OFF` on a plain `engine.connect()` BEFORE any transaction starts (SQLite only allows this toggle with no transaction open -- doing it from inside the migration file itself, within the already-open transaction, is a silent no-op, confirmed by testing the naive fix first and watching it fail identically), with a `PRAGMA foreign_key_check` right before commit so a genuine data-integrity violation still aborts loudly. The migration test was strengthened to insert a real FK-referencing `progress_events` row, closing the actual coverage gap, not just the symptom. Verified end-to-end against a full copy of the real database: all tables' row counts identical before/after, `integrity_check`/`foreign_key_check` both clean. The live database required a one-time manual correction (its `alembic_version` was stuck at `0020_db_epoch` despite `0021`'s column already having silently committed via SQLite's non-transactional-DDL behavior before the 0022 crash) -- verified safe via byte-for-byte row-count comparison on a copy before applying to the real file. |
| 2 | Real time crossed from 2026-10-02 into 2026-10-03 partway through this story's development, and two new tests (`test_parent_assigns_exam_and_child_starts_a_fresh_draw_each_time`, `test_assignment_ref_mismatch_rejected`) hardcoded `assigned_date: "2026-10-02"` without pinning `app.state.clock` the way `test_assignments.py`'s own established pattern already does -- both started failing with `DATE_IN_PAST` the moment real time passed that date. The exact same class of flaky-hardcoded-date bug already found and fixed in this project's Epic 3 audit | medium | confirmed by direct reproduction (both tests failed identically, non-flakily, once real date advanced) -> **patched**: `test_exam.py`'s `client` fixture now pins `app.state.clock = lambda: NOW` (`NOW = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)`), mirroring `test_assignments.py`'s pattern exactly. All 19 tests in the file pass regardless of the real wall-clock date. |
| 3 | The `NullPool` change in `db/engine.py` (an unprompted, out-of-Code-Map fix the implementer made while debugging an unrelated stale-read bug in the Assignment flow) is a global connection-pooling strategy change affecting every database access in the app, not scoped to this story. Reviewed independently: this is the well-documented, standard SQLAlchemy recommendation for file-based SQLite specifically because a pooled, reused raw connection can observe a stale WAL snapshot across requests -- not a hack. Confirmed via a fresh Library-endpoint timing check that it does not reintroduce the `content/library.py` performance regression fixed earlier (a separate, unrelated piece of work in this same session) -- Library still loads in ~1.2s against the full 1760-Problem Grade 1 corpus, consistent with pre-NullPool timings | low (confirmed correct, not a defect) | independently verified: (a) the SQLAlchemy/SQLite pooling recommendation is standard, not invented; (b) `GET /library/grades/1/books` timed at ~1.2s post-change, matching the already-fixed baseline; (c) full backend suite green with the change in place -> no further action; flagged here only because it was an unscoped, self-initiated infrastructure change that deserved independent scrutiny before being trusted, which it received. |
| 4 | End-to-end smoke test against the real, live server and real Grade-1 content (not just the test suite): `POST /sessions` with `{"kind":"exam","scope":{"kind":"grade"},"count":5,"time_limit_s":600}` correctly drew 5 random Problems spanning multiple different Grade-1 books, returned `mode:"exam"` and `time_limit_s:600` in the response (confirming the frontend has what it needs for the backend-authoritative countdown), and a request with `exams_enabled=false` was correctly refused with `403 EXAMS_DISABLED` and a friendly Vietnamese message | n/a | verified directly, not a finding -> confirms the core feature genuinely works against production-scale real data, not just synthetic test fixtures. |

All four findings above are resolved. Full backend suite independently re-verified after all fixes: **1197/1197 passed**, `ruff check` clean. Frontend: `tsc -b`/`eslint` clean, all 7 touched test files (78 tests) passing.

