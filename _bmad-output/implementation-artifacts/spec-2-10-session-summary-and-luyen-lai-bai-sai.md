---
title: 'Story 2.10: Session summary and "Luyện lại bài sai"'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:401640c63f32674341a65a84ee171898c6697da2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Session that reaches its last Problem currently just... stops (`SessionPlayer.tsx`'s
`chunkDone` fires between EVERY chunk, not just the true end, and there's no real summary screen).
Nothing computes first-try accuracy, and wrong Problems have no way to be practised again — the
`replay` `ProblemSetRef` kind is still an `UnsupportedProblemSetRef` stub from Story 2.4.

**Approach:** On a Session's true completion (the last Problem of the last chunk, not merely a
chunk boundary), post a `session_completed` event, set `progress_sessions.completed_at`, and show a
summary screen computing first-try accuracy by finding each attempted Problem's EARLIEST `attempt`
event (by insertion order, matching Story 2.5's own established tiebreak pattern) and checking
whether it was correct. Wrong Problems get a "Luyện lại bài sai" button that starts a NEW Session
with `ProblemSetRef{kind: "replay", source_session_id}` — a new `ReplayRef` variant resolving
directly to the recorded wrong-Problem ids (no `content.library` call needed, the list is already
known). Per AD-6's scoring-by-mode table, `replay` is the ONLY mode where Stars, Retry Queue
membership, and Streak are ALL switched off — `progress_sessions.mode` must become a real,
read/branched-on field for the first time (today nothing reads it; every session so far has been
"practice", and grading logic runs unconditionally regardless of mode).

**Streak** ("the number of days in a row with at least one completed Session", per the PRD, `Asia/
Ho_Chi_Minh` dates) is derived reactively from `session_completed` events' `occurred_at`, not a new
mutable counter — consistent with this codebase's established append-only-log-derivation
philosophy (Stories 2.5/2.8), and excluding `replay`-mode sessions per AD-6.

## Boundaries & Constraints

**Always:**
- **`learning/problem_sets.py`**: add `ReplayRef` (`{kind: "replay", source_session_id: str}`) to
  the `ProblemSetRef` union. `resolve()` for `kind: "replay"` loads the source Session's wrong
  Problem ids directly (computed the same way the summary does — see below) and returns them in
  their original order from the source Session; raises a clear 422 if the source Session has zero
  wrong Problems (nothing to replay) or doesn't belong to the same profile. `ref_key()` gets a
  matching branch (`f"replay:{source_session_id}"`).
- **`progress_sessions.mode` becomes real**: `POST /sessions` accepts an optional `mode` (default
  `"practice"`, matching today's only behavior) — starting a replay Session passes `mode:
  "replay"`. `learning/sessions.py`'s `post_event()` loads `session.mode` (already loads the
  session row) and gates, per AD-6's scoring table:
  - `_add_retry_item()` (on a wrong `attempt` or a `self_marked(false)`): skipped entirely when
    `mode == "replay"`.
  - Star-derivation (the existing `self_marked(correct:true)` derived-Star convention from Story
    2.8, PLUS this story's own first-try-accuracy-based Star for a graded `attempt` — see below):
    a `replay`-mode session's events are simply never counted by whatever reads them, achieved by
    the summary/Streak-reading logic itself excluding `mode == "replay"` sessions (not by refusing
    to store the events — they're still stored durably, just excluded from every derived metric).
  - `_maybe_resolve_retry_item()`: still fine to run for `replay` mode (resolving an existing open
    Retry Queue item when its Problem is finally answered correctly, even via a replay attempt, is
    a REASONABLE side effect — AD-6's exclusion is about replay attempts never ADDING to Stars/
    Retry/Streak, not about blocking a legitimate resolution of a pre-existing item). Document this
    reading explicitly if the implementer judges differently — either call is defensible, pick one
    and say why.
- **First-try accuracy** (`learning/sessions.py` or a new small module, e.g.
  `learning/summary.py`): for a completed Session, for each of its frozen `problem_ids`, find the
  EARLIEST stored `attempt` event for `(profile_id, problem_id)` **within that Session**
  (`session_id` filter, unlike Story 2.5's Profile-wide Retry-Queue counting — first-try accuracy
  is a per-Session metric) ordered by rowid (the same insertion-order tiebreak already established
  in `_part_currently_correct()`), and check its stored `correct` field. A Problem with multiple
  Parts: "correct on the first try" means every Part's own first attempt within the Session was
  correct (implementer's call on the exact aggregation if a Problem has multiple Parts attempted at
  different times — document whichever reasonable definition is chosen).
- **`session_completed` event**: posted by the frontend when the true end of a Session is reached
  (last Problem of the last chunk, not a chunk boundary — the frontend must distinguish these, see
  Code Map). Sets `progress_sessions.completed_at` (currently always `NULL` — this is the first
  story to ever set it). Idempotent via the same `progress_events` primary-key mechanism as every
  other event kind — a resent `session_completed` for an already-completed Session is a no-op, not
  an error.
- **`GET /sessions/{id}/summary`** (new endpoint, child-facing, no PIN, same trust level as every
  other Session endpoint): returns first-try-correct count / total Problems, the wrong Problem ids
  (for the "Luyện lại bài sai" button, only shown if non-empty), and a simple Streak count (days in
  a row with ≥1 non-replay `session_completed` event, ending today or yesterday — implementer's
  call on the exact "still alive" boundary, document it). Only meaningful after
  `completed_at` is set; 422 if called before completion (implementer's call on exact wording).
- **Frontend**: `SessionPlayer.tsx`/`ProblemPlayer.tsx` distinguish "chunk done, more chunks remain"
  (existing behavior — advance to next chunk) from "the LAST chunk is done" (new — post
  `session_completed`, then show the real summary screen: first-try-correct count with a fanfare/
  StarBurst, using the existing `session_summary`/`practice_wrong_again` phrases already present in
  `phrases.vi.json` from earlier stories). "Luyện lại bài sai" (shown only when there are wrong
  Problems) calls `POST /sessions` with `{kind: "replay", source_session_id}` and navigates to the
  new Session, reusing the exact same start-a-Session flow Home's "Học tiếp" already uses.

**Never:**
- No changes to `content.schema`/`content.effective`/`content.library`/`content.speech` — pure
  `learning`/frontend work, exactly like every prior Epic 2 backend story.
- No badges — out of scope for this story too (still deferred, log again in `deferred-work.md` if
  not already covered by an earlier entry).
- A `replay` Session's `problem_ids_json` is frozen exactly like any other Session's (AD-9) — it
  never re-resolves or re-filters mid-Session even if the source Session's Problems change state
  afterward.
- Do not build a Streak DISPLAY beyond what the summary endpoint returns as a number — no calendar
  UI, no flame animation asset — a simple count is enough for this story (the PRD's UJ-1 narrative
  mentions "the 4-day Streak flame growing" as flavor text, not a literal required asset).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Last Problem of last chunk answered | Session's final attempt | session_completed posted, completed_at set, summary shows correctly | N/A |
| Chunk done, more chunks remain | mid-Session chunk boundary | advances to next chunk as today (Story 2.6 behavior unchanged), no summary yet | N/A |
| First-try accuracy, all correct first try | every Problem's earliest attempt correct | summary shows n/n | N/A |
| First-try accuracy, some correct only on retry | a Problem's first attempt wrong, later attempt correct | that Problem does NOT count as first-try-correct | N/A |
| Luyện lại bài sai, wrong Problems exist | tap the button | new replay Session starts with exactly those Problem ids, in original order | N/A |
| Luyện lại bài sai, zero wrong Problems | button not shown / or attempted anyway | 422 if attempted via API with no wrong Problems; button hidden on the frontend when count is 0 | N/A |
| Replay session, wrong attempt | attempt graded wrong in a replay Session | Hint/Solution still staged normally (grading itself is unaffected); Retry Queue NOT added | N/A |
| Replay session, self_marked(false) on a fallback Problem | replay mode | Retry Queue NOT added | N/A |
| Streak, consecutive days | 3 consecutive days each with ≥1 completed non-replay Session | Streak reads 3 | N/A |
| Streak, a gap day | day 1 and day 3 completed, day 2 not | Streak reads however the "still alive" rule defines it (document the exact boundary chosen) | N/A |
| Streak excludes replay | a day's only completed Session was replay-mode | that day does not count towards the Streak | N/A |
| GET summary before completion | Session not yet completed_at | 422, clear message | N/A |
| Resent session_completed | same event id twice | idempotent no-op, completed_at unchanged after the first | N/A |

## Code Map

- `backend/hoctap/learning/problem_sets.py`: `ReplayRef`, `resolve()`/`ref_key()` branches.
- `backend/hoctap/learning/sessions.py`: `post_event()` gates Retry-Queue-add on `mode != "replay"`;
  `start_session()` accepts an optional `mode` param; a new summary-computation function (or a
  sibling `learning/summary.py`) for first-try accuracy + Streak.
- `backend/hoctap/api/sessions.py`: `GET /sessions/{id}/summary`; `POST /sessions` body gains
  optional `mode`/`source_session_id` handling for the replay path.
- `backend/tests/test_sessions.py`, `test_problem_sets.py`: new tests per the matrix.
- `frontend/src/pages/SessionPlayer.tsx`/`ProblemPlayer.tsx`: true-Session-end detection (distinct
  from chunk-done), `session_completed` posting, a new summary screen component.
- `frontend/src/api/queries.ts`: `useSessionSummary()`, a `useStartReplaySession()` or extended
  `useStartSession()`.
- `_bmad-output/implementation-artifacts/deferred-work.md`: badges, and a Streak-display UI beyond
  a plain number, if judged worth flagging.

## Tasks & Acceptance

- [ ] `ReplayRef` + `resolve()`/`ref_key()` for `kind: "replay"`.
- [ ] `progress_sessions.mode` read and branched on in `post_event()`: Retry-Queue-add skipped for
      `replay`; document the `_maybe_resolve_retry_item()` decision either way.
- [ ] First-try-accuracy computation (per-Session, per-Problem, earliest-attempt-by-rowid).
- [ ] `session_completed` event handling: sets `completed_at`, idempotent.
- [ ] `GET /sessions/{id}/summary`: first-try count, wrong Problem ids, Streak count; 422 before
      completion.
- [ ] Frontend: true-end detection distinct from chunk-done; summary screen with fanfare; "Luyện
      lại bài sai" button (hidden when no wrong Problems) starting a real replay Session.
- [ ] `deferred-work.md` entries (badges, Streak-display UI) as applicable.
- [ ] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-29: Backend + frontend implementation

**Files touched**
- `backend/hoctap/learning/problem_sets.py`: `ReplayRef` added to `ProblemSetRef` (now
  `LessonRef | ReplayRef`); `resolve()`/`ref_key()` branch on `kind: "replay"`.
- `backend/hoctap/learning/summary.py` (new): `session_wrong_problem_ids()`,
  `compute_streak()`, `compute_summary()`, `SessionSummary`.
- `backend/hoctap/learning/sessions.py`: `start_session()` takes `mode` (default
  `"practice"`); `_grade_and_stage()` takes `mode` and skips `_add_retry_item()` when
  `mode == "replay"`; `post_event()` loads `session.mode`, gates `self_marked`'s
  `_add_retry_item()` the same way, and handles `kind == "session_completed"` (sets
  `completed_at`); new `get_session_summary()` (403/404/422-before-completion, then
  `compute_summary()`).
- `backend/hoctap/api/sessions.py`: `StartSessionIn.ref` is now `LessonRefIn | ReplayRefIn`
  (Pydantic discriminated union on `kind`) plus an optional `mode`; new
  `GET /sessions/{id}/summary`.
- `backend/tests/test_sessions.py`: ~20 new tests (replay resolve/422s, mode-gated Retry
  Queue, `session_completed`/idempotency, summary first-try accuracy/streak, streak unit
  tests against `learning.summary.compute_streak()` directly).
- `frontend/src/pages/SessionPlayer.tsx`: true-end detection, `session_completed` posting,
  `SessionSummaryScreen` (fanfare, first-try count, Streak, "Luyện lại bài sai").
- `frontend/src/pages/SessionPlayer.test.tsx`: updated the old "done state" test for the
  new summary-screen flow; added a "Luyện lại bài sai starts a replay Session" test.
- `frontend/src/api/client.ts`/`queries.ts`: `ReplayRefIn`/`SummaryOut` types,
  `getSessionSummary()`, `useSessionSummary()`, `startSession()`/`useStartSession()` now
  take `mode` and a `StartSessionRefIn` union.
- `frontend/openapi.json`/`frontend/src/api/schema.d.ts`: regenerated via
  `uv run hoctap export-openapi` (offline; no server needed) + `npm run gen:api`.
- `_bmad-output/implementation-artifacts/deferred-work.md`: 3 new entries (fallback-Problem
  first-try-accuracy limitation, Streak-display UI, badges).

**First-try-accuracy aggregation rule (multi-Part Problems).** For each Problem in the
Session's frozen `problem_ids`, `learning.summary.session_wrong_problem_ids()` reads every
`attempt` event for that Session (ordered by SQLite rowid, the same insertion-order
tiebreak `_part_currently_correct()` established in Story 2.5), and for each distinct
`part_key` keeps only the FIRST-seen `correct` verdict. A Problem counts as
first-try-correct only if EVERY Part it has ANY attempt for was correct on that Part's own
first attempt. A Problem with NO `attempt` event at all within the Session (a `fallback`
Problem, which is only ever `self_marked`, or an unsupported Part type skipped straight
past) is treated as NOT first-try-correct — absence of evidence is not evidence of a
correct first try. **Deviation from a literal first read of the frozen spec's intent**:
this means a `fallback` Problem the child correctly self-marked "đúng" still shows up in
`wrong_problem_ids` and gets offered again via "Luyện lại bài sai" every time. I considered
having a fallback Problem's earliest `self_marked` event stand in for a verdict, but the
frozen spec text says explicitly "find the EARLIEST stored `attempt` event ... and check
its stored `correct` field" (attempt only), and Story 2.8's own `deferred-work.md` entry
already warns any future first-try-accuracy reader to exclude `self_marked`/
`fallback_revealed` "by construction". I followed that literal instruction rather than
silently reinterpreting it, and logged the resulting limitation as a new `deferred-work.md`
entry rather than deviating from the frozen text without saying so.

**Streak "still alive" boundary.** `compute_streak()` walks calendar dates (Asia/
Ho_Chi_Minh) backward from `today`, over completed (`completed_at` not null),
non-`replay`-mode Sessions. If `today` itself has no completed Session yet, the walk starts
from `today - 1 day` instead (so a Streak built up through yesterday still reads correctly
before today's own Session finishes); if NEITHER today nor yesterday has one, the Streak
reads 0 (a two-day-old gap is a real break, not "today isn't over yet"). Verified directly
against `learning.summary.compute_streak()` with hand-inserted `progress_sessions` rows
(3-consecutive-days = 3; day-1-and-day-3-with-a-gap, evaluated from day 3 = 1; a day whose
only completed Session is `mode="replay"` doesn't count).

**`_maybe_resolve_retry_item()` during replay: NOT gated on `mode`.** A correct `attempt` or
`self_marked(correct:true)` in a `replay`-mode Session still resolves a pre-existing OPEN
Retry Queue row for that Problem. Reasoning: AD-6's replay exclusion is specifically about
replay attempts never ADDING NEW Stars/Retry-Queue-rows/Streak-days (a replay session is
explicitly de-scored so it can't be gamed into farming rewards) — it says nothing about
blocking the legitimate, useful side effect of a replay attempt finally clearing an item
that's been open since a genuine practice Session. Leaving a stale, already-fixed Retry
Queue row open forever because the child happened to fix it via replay would be a worse
outcome than resolving it. Covered by
`test_replay_correct_attempt_still_resolves_existing_retry_item`.

**True-Session-end detection (frontend).** `SessionPlayer.tsx`: `chunkDone =
problemIndex >= problems.length` (unchanged from Story 2.6) and `hasNextChunk = chunk <
chunk_count` (unchanged). The NEW distinction is `trueEnd = chunkDone && !hasNextChunk`. A
mid-Session chunk boundary (`chunkDone && hasNextChunk`) renders the existing "Phần tiếp
theo" interim screen with no summary and no `session_completed` post (Story 2.6 behaviour,
unchanged — I removed the `session_summary` phrase text from this interim screen since it
was misleadingly saying "Em đã hoàn thành bài!" at a mid-Session boundary, which is no
longer accurate now that a distinct true-end screen exists). Only `trueEnd` triggers a
`session_completed` POST (guarded by a `useRef` flag so it fires at most once even across
re-renders while the mutation is in flight) and, once that lands, enables
`useSessionSummary()` to fetch the real summary and render `SessionSummaryScreen`
(fanfare via `StarBurst`, `first_try_correct/total`, the Streak count if > 0, and "Luyện
lại bài sai" only when `wrong_problem_ids.length > 0`).

**Other deviations/decisions:**
- `POST /sessions`'s `mode` field is independent of `ref.kind` (not derived from it) per the
  spec's literal wording ("an optional `mode`... starting a replay Session passes `mode:
  'replay'`"); the frontend always sends both together for a replay start.
- `ReplayRef.resolve()` returns a single `REPLAY_SOURCE_NOT_FOUND` 422 for BOTH "unknown
  source Session" and "source Session belongs to a different Profile" (matching this
  codebase's existing ownership-check posture elsewhere of not distinguishing "doesn't
  exist" from "not yours" to an untrusted client), and a separate `REPLAY_NO_WRONG_PROBLEMS`
  422 when the source has zero wrong Problems.

**Verification commands:**
- Backend, targeted: `.venv/bin/python -m pytest tests/test_sessions.py tests/test_problem_sets.py -q`
  → `82 passed` (includes every pre-existing Story 2.4/2.5/2.8 test, confirming no
  regression from the `mode`-gating change to shared grading code).
- Backend, full suite: `.venv/bin/python -m pytest -q` → `858 passed in 534.70s`.
- Backend lint: `.venv/bin/python -m ruff check hoctap/ tests/test_sessions.py
  tests/test_problem_sets.py` → all clean.
- Frontend types: `npx tsc -b` (from a fresh `npm ci` sync, per this repo's fast-verification
  workaround) → clean, no errors.
- Frontend lint: `npx eslint src/pages/SessionPlayer.tsx src/api/queries.ts src/api/client.ts`
  → clean.
- Frontend tests, full suite: `npx vitest run` → `255 passed | 3 failed (258)`. The 3
  failures are in `src/pages/ExtractionPage.test.tsx` (3 tests) and 1 unrelated file
  (`src/styles/tokens.test.ts`) — neither file was touched by this story, both reproduced in
  isolation on an unmodified checkout too, and are consistent with the pre-briefed "sporadic
  timeouts under shared-machine load" flakiness rather than a regression from this change.
  All `SessionPlayer.test.tsx`/`ProblemPlayer.test.tsx` tests pass (9/9 and pre-existing
  counts respectively).

### 2026-09-29: Review Triage Log fixes

**#1 (high, fixed).** `post_event()`'s `session_completed` handling in
`backend/hoctap/learning/sessions.py` guarded only against a literal resend of the SAME
event id; a second, DISTINCT `session_completed` event (different UUIDv7) would
unconditionally overwrite `completed_at`. Fixed by adding
`.where(progress_sessions.c.completed_at.is_(None))` to the UPDATE, so only the first
`session_completed` event to arrive (by whichever id gets there first) ever actually sets
`completed_at`; a second distinct event is still inserted into `progress_events` normally
(a valid event, just a no-op for `completed_at`) rather than rejected. New test:
`test_session_completed_second_distinct_event_does_not_overwrite_completed_at` (posts two
distinct `session_completed` events for the same Session, asserts `completed_at` reflects
only the first's timestamp and both events are durably stored).

**#2 (medium, fixed).** `ReplayRef.resolve()` in `backend/hoctap/learning/problem_sets.py`
never checked the source Session's `completed_at`, so a client could start "Luyện lại bài
sai" against a still-in-progress source Session (`session_wrong_problem_ids()`'s
absence-of-evidence rule treats "no attempt yet" the same as "wrong"). Fixed by adding a
`source.completed_at is None` check that raises a new `422 REPLAY_SOURCE_NOT_COMPLETED`
(bilingual message, matching this codebase's existing error style) before the wrong-ids
computation runs. New test: `test_replay_source_session_not_completed_422`.

**#3 (low, fixed).** Added `test_streak_crosses_utc_local_calendar_day_boundary`: a
completed Session stored with `completed_at="2026-09-28T18:00:00+00:00"` (UTC) is
`2026-09-29T01:00` in Asia/Ho_Chi_Minh (+07:00) -- the test asserts `compute_streak()`
attributes it to the LOCAL date (streak reads 1 from `today=2026-09-29`) and NOT the UTC
date (streak reads 0 from `today=2026-09-28`, since neither that day nor its "yesterday"
has a completed non-replay Session locally). This is the first streak test to actually
exercise `_local_date()`'s `.astimezone(LOCAL_TZ)` conversion at a real UTC/local
calendar-day boundary; every pre-existing streak test happened to use timestamps that fall
on the same calendar day in both zones.

**#4 (low, fixed -- top pick only, per "do the top 2" guidance).** Added
`test_summary_wrong_problem_ids_empty_when_all_correct_first_try`: a targeted assertion
that `GET /sessions/{id}/summary`'s `wrong_problem_ids` is `[]` (the signal the frontend's
"Luyện lại bài sai" button-hiding logic reads) when every Problem in the Session was
answered correctly on the first try, rather than relying on this being an incidental
byproduct of the existing `first_try_correct` assertion in a different test. The
frontend's `postingCompletedRef` re-render-guard test (the other half of this finding) is
left as documented debt (per the finding's own "log as debt if time-constrained" option)
since this pass was scoped to backend-only findings.

**#5 (low, resolved by documentation, no code change).** Replaying a replay (a
`kind: "replay"` ref whose `source_session_id` points at another `mode="replay"` Session)
is explicitly ALLOWED, not blocked. Documented directly in `resolve()`'s own docstring in
`backend/hoctap/learning/problem_sets.py`: a replay Session that still has wrong Problems
of its own is a legitimate thing to want to practise again, and an arbitrary
chained-replay-depth limit isn't something the frozen spec ever asked for. The only two
guards `resolve()` applies to a replay source remain "belongs to this profile" (#2,
pre-existing) and "already completed" (#2, this pass) -- nothing inspects the source's own
`mode`/`ref_kind`. Left untested by a dedicated test (the ambiguity itself is resolved by
documenting the decision, per the finding's own "either is acceptable, just resolve the
ambiguity" framing) since it is now simply the existing, exercised code path with no
special-case branch to test.

**Verification commands:**
- Backend, targeted: `.venv/bin/python -m pytest tests/test_sessions.py
  tests/test_problem_sets.py -q` → `86 passed` (82 pre-existing + 4 new: the
  distinct-`session_completed` guard test, the replay-not-completed 422 test, the
  UTC/local streak boundary test, and the wrong-problem-ids-empty targeted test).
- Backend lint: `.venv/bin/python -m ruff check hoctap/ tests/test_sessions.py
  tests/test_problem_sets.py` → all clean.
- Backend, full suite: `.venv/bin/python -m pytest -q` → `862 passed in 496.39s`
  (858 pre-existing + 4 new tests from this pass), confirming no regression to any
  earlier Story from the `session_completed`/`ReplayRef.resolve()` guard changes.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `session_completed`'s idempotency only guards a literal resend of the SAME event id (the early-return `already_stored` check); a second, DISTINCT `session_completed` event (e.g. two tabs open, or a client retry after a false-timeout that mints a fresh id) unconditionally overwrites `completed_at` to the later timestamp -- no `.where(completed_at.is_(None))` guard. This can shift a Session to the wrong calendar day for Streak purposes | high | confirmed independently by 2 reviewers from different angles -> patch: guard the UPDATE with `.where(progress_sessions.c.completed_at.is_(None))` so only the FIRST session_completed event (by whichever id arrives first) ever sets it; add a test posting two distinct session_completed events for the same Session and asserting completed_at reflects only the first |
| 2 | `ReplayRef.resolve()` never checks the source Session's `completed_at is not None` -- a client can start a replay against a source Session that's still in-progress (zero or few events so far), since `session_wrong_problem_ids()` treats "no attempt yet" the same as "wrong" (absence-of-evidence rule). This spawns a near-duplicate Session before the child finished the original, contrary to the feature's intent ("Luyện lại bài sai" after a completed Session) | medium | confirmed by 1 reviewer, not a security hole (same profile/content) but a real intent gap, untested by the existing matrix (all replay tests post completion first) -> patch: add a check that the source Session's `completed_at is not None`, reject (422, bilingual-equivalent message) otherwise; add a test for this exact case |
| 3 | Streak's `_local_date()` timezone conversion (`.astimezone(LOCAL_TZ)`) is independently confirmed CORRECT by the orchestrator and 2 reviewers via code reading, but every existing streak test uses timestamps that happen to fall on the same calendar day in both UTC and Asia/Ho_Chi_Minh (e.g. 03:00 UTC = 10:00 local) -- no test actually exercises a UTC/local calendar-day boundary crossing (e.g. 18:00 UTC = 01:00 local, next day) | low | confirmed by 2 reviewers as a real, unexercised risk (a regression dropping the `.astimezone()` call would pass every existing test) -> patch: add one test using a timestamp where the UTC and Vietnam calendar dates genuinely differ |
| 4 | Two related low-value gaps: "Luyện lại bài sai" button-hidden-at-zero-wrong is only exercised incidentally (as a byproduct of the all-correct-first-try test, not a targeted assertion of the hiding logic itself); the frontend's `postingCompletedRef` guard against a duplicate `session_completed` POST from a fast re-render/re-mount is unverified by any test (inferred correct from reading the code only) | low | -> patch: add the cheaper of the two (a targeted button-hidden assertion) if time allows; log the re-render-guard test as debt if time-constrained |
| 5 | Replaying a replay Session (`kind:"replay"` with `source_session_id` pointing at another replay-mode Session) is allowed by the code (no `ref_kind`/`mode` check on the source) and untested; whether this is intentional or should be blocked is undocumented either way | low | -> patch: implementer's judgment call -- either explicitly allow and document it (a one-line Implementation Notes addition), or block it with a clear error; either is acceptable, just resolve the ambiguity |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed both fixes directly in source (`completed_at` UPDATE now guarded with `.where(completed_at.is_(None))`; ReplayRef.resolve() now rejects an incomplete source Session with `REPLAY_SOURCE_NOT_COMPLETED`). Ran `ruff check` (clean) and the full backend suite independently: 862/862 passing. Ran the full frontend suite independently: 261/264 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story); `tsc -b`/`eslint` both clean. Story marked done.

</frozen-after-approval>
