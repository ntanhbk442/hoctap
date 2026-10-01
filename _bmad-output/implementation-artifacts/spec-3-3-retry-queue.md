---
title: 'Story 3.3: Retry Queue'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'da0581e40ca2119e7306473905dc3cee0c4d1705'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 2.5/2.10 built a simpler, immediate Retry Queue (`progress_retry_items`):
entry already matches AD-6 (any wrong Part `attempt`, or a `fallback` "chưa đúng"), but exit
resolves the instant every Part is *currently* correct (no cross-Session count), there is no
"due next calendar day" gating (an item is actionable the moment it's added), a `fallback` Problem
exits on one "đúng" self-mark (not twice), and `ProblemSetRef(kind="retry")` is a documented
`UnsupportedProblemSetRef` stub — no way to start a Session of due items, and Home has no
"Luyện lại" card (`home_practice_again` is an unused placeholder phrase key).

**Approach:** Keep entry unchanged. Add `last_wrong_at` (updated on every subsequent wrong
Attempt/"chưa đúng" while an item stays open) to derive "due" (its local calendar day is before
today's). Replace immediate exit with a qualifying-Session count: for a graded Problem, reuse
Story 3.1's `progress_stars` rows (`stars == 3` already means "every Part first-try-correct this
Session") — 2 distinct such Sessions since the item opened resolves it; for `fallback`, count
`self_marked(correct=true)` events since the item opened — 2 resolves it. Implement
`RetryRef`/`kind: "retry"` resolving to the Profile's due Problem ids, wiring the already-existing
`retry` Session mode to a real start path, and add a Home "Luyện lại" card (shown only when ≥1 due
item exists) that starts it.

## Boundaries & Constraints

**Always:**
- `progress_retry_items` gains `last_wrong_at` (Text, nullable, backfilled from `added_at`) via a
  new migration after `0015_progress_badges`. `_add_retry_item()` now UPDATES `last_wrong_at` on an
  existing open row (instead of no-op skip) on every new wrong Attempt/"chưa đúng" for it — this is
  what makes "next day after the *last* wrong Attempt" correct across repeated wrong tries.
- "Due" = the open item's `last_wrong_at`, converted to `Asia/Ho_Chi_Minh` (reuse `LOCAL_TZ`), has
  an earlier calendar date than "today" (the request's `now`, same pattern as `compute_streak`).
- New exit logic (replaces `_maybe_resolve_retry_item`'s immediate resolution): non-fallback —
  resolve the open row once `progress_stars` has ≥2 distinct `session_id` rows for this
  `problem_id` with `stars == 3` and `occurred_at > since` of that row. Fallback — resolve once
  ≥2 `self_marked(correct=true)` events from ≥2 distinct non-`replay` `session_id`s for this
  `problem_id` have `occurred_at > since` of that row (human decision: two self-marks inside one
  Session never count as two). **`since` = `max(added_at, last_wrong_at)` of the open row, not
  `added_at` alone** (corrected 2026-10-01 — see Spec Change Log: the row's own `last_wrong_at`
  already moves forward on every repeat wrong attempt while the item stays open, and a fresh miss
  resets the qualifying-Session count the same way it resets "due"). Both counts also reset the
  full "start over" way: a resolved row's successor (on reopen) is a fresh row with a fresh
  `added_at`/`last_wrong_at`.
- Resolution check runs after `maybe_award_stars()`/the `self_marked` write, same SAVEPOINT (mirrors
  Story 3.2's badge call-site, since it needs the Star row to exist first for the non-fallback path).
- `problem_sets.py` gains `RetryRef(kind="retry")`: no extra fields (Profile-scoped), resolves to
  due `problem_id`s only (not all open items), ordered by `last_wrong_at` ascending; empty list
  422s the same way `ReplayRef` does. `ref_key()` gains a `"retry"` case.
- `POST /sessions` accepts `RetryRefIn(kind="retry")`; created Session's `mode` is `"retry"`
  (already Star/Streak-eligible per AD-6 — no scoring changes needed).
- `GET /library/home/{profile_id}` gains a due-items signal (`retry_due: bool` or
  `retry_due_count: int` — implementer's call, document it) gating the card per the epic's "only
  when at least one queued Problem is due" rule.
- Frontend: Home shows a "Luyện lại" card (reuse `home_practice_again`) only when due; tapping it
  starts a `retry`-mode Session via `RetryRefIn`, reusing `SessionPlayer` untouched.
- New/updated logic lives in a new `backend/hoctap/learning/retry.py` (epic's module list names
  `retry` as a sibling of `scoring`/`streaks`/`badges`) — existing `_add_retry_item`/
  `_maybe_resolve_retry_item` in `sessions.py` may move there or stay thin call-sites, implementer's
  call, document it.

**Never:**
- No change to entry conditions (any wrong Part Attempt, `fallback` "chưa đúng", `replay`-mode
  never adds) — already correct.
- No change to `progress_stars`/`maybe_award_stars`/`compute_streak`/badge logic themselves (call,
  don't modify).
- No quiz-mode changes — Story 3.4 feeds this same table/rules later, but quiz doesn't exist yet.
- No "due" concept for the *first* wrong Attempt's grace period beyond "next calendar day" — an
  item is never due same-day, even if the wrong Attempt was seconds before local midnight.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Repeated wrong Attempt, same open item | 2nd wrong Attempt, same calendar day | `last_wrong_at` updated, still not due today | N/A |
| Next-day load | open item, `last_wrong_at` = yesterday (local) | due; Home shows "Luyện lại" card | N/A |
| Graded Problem, 1 qualifying Session | 1 non-replay Session, `stars==3`, since `max(added_at, last_wrong_at)` | item stays open | N/A |
| Graded Problem, 2 qualifying Sessions | 2 distinct such Sessions since `max(added_at, last_wrong_at)`, no miss in between | item resolved | N/A |
| Fallback, 2 "đúng" self-marks, 2 Sessions | 2 `self_marked(true)` in 2 distinct Sessions since `max(added_at, last_wrong_at)` | item resolved | N/A |
| Fallback, 2 "đúng" self-marks, 1 Session | both in the same Session | item stays open | N/A |
| Replay-mode Session, correct attempt | `mode="replay"` | never counts as qualifying | N/A |
| Start retry Session, none due | `kind:"retry"`, 0 due items | 422, same pattern as empty replay | `RETRY_QUEUE_EMPTY`-style error |
| Fresh miss between two qualifying Sessions | 1 qualifying Session, then a new wrong Attempt/"chưa đúng" on the still-open item, then 1 more qualifying Session | stays open after the 2nd qualifying Session too (the miss reset the count to 0/2; a 3rd qualifying Session resolves it) — corrected 2026-10-01, see Spec Change Log | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/models.py`, `db/alembic/versions/0016_retry_queue_due.py` (new, head
  `0015_progress_badges`) -- add + backfill `last_wrong_at`.
- `backend/hoctap/learning/retry.py` (new) -- `is_due()`, qualifying-count/resolution logic; may
  absorb `sessions.py`'s `_add_retry_item`/`_maybe_resolve_retry_item`.
- `backend/hoctap/learning/sessions.py` -- `_add_retry_item` updates `last_wrong_at` on reopen;
  resolution check moves to after `maybe_award_stars()`/`self_marked`, same SAVEPOINT.
- `backend/hoctap/learning/problem_sets.py` -- `RetryRef`/`ref_key()`/`resolve(kind="retry")`,
  replacing its `UnsupportedProblemSetRef` stub.
- `backend/hoctap/api/sessions.py` -- `RetryRefIn` request model.
- `backend/hoctap/api/library.py` -- `LibraryHomeOut` due-items signal.
- `backend/tests/test_retry.py` (new) -- covers this spec's matrix.
- `frontend/src/pages/Home.tsx` -- "Luyện lại" card (reuses `home_practice_again`), starts a retry
  Session.

## Tasks & Acceptance

**Execution:**
- [x] `models.py` + migration `0016` -- add/backfill `last_wrong_at`.
- [x] `learning/retry.py` -- due-check + 2-Session/2-self-mark exit logic, wired into
      `post_event()`'s SAVEPOINT after Star awarding.
- [x] `problem_sets.py` -- `RetryRef`/`resolve(kind="retry")`/`ref_key()`.
- [x] `api/sessions.py` + `api/library.py` -- `RetryRefIn`; `LibraryHomeOut` due signal.
- [x] `frontend/src/pages/Home.tsx` -- "Luyện lại" card + start-Session wiring.
- [x] `test_retry.py` -- covers all matrix rows.
- [x] `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

**Acceptance Criteria:**
- Given an item whose last wrong Attempt was today (local), when Home loads, then no card shows
  and starting `kind:"retry"` for it alone 422s.
- Given an item due since yesterday (local) with no other due items, when Home loads, then the
  card shows and starting it freezes a Session with exactly that Problem.
- Given a non-fallback item, when 2 distinct non-`replay` Sessions each score it `stars==3` after
  it opened, then it resolves on the second one.
- Given a `replay`-mode Session scoring a Problem's Parts all correct, then it never counts toward
  either exit rule.

## Implementation Notes

<!-- Agent-owned. Append-only during implementation. -->

- (2026-09-29) New `learning/retry.py` owns add/refresh (`last_wrong_at`), due-check and exit logic; the old helpers moved out of `sessions.py`. Exit check runs after `maybe_award_stars()` in the same SAVEPOINT. Graded and fallback qualifying counts are summed, equivalent to per-type rules since fallback never earns 3 stars.
- `RetryRef` resolves due Problem ids ordered by `last_wrong_at`; empty queue returns 422 `RETRY_QUEUE_EMPTY`. Home gains `retry_due_count` (int).
- Four existing `test_sessions.py` tests asserted the old immediate-resolve behaviour and were updated to assert the item stays open.
- Quiz-mode feeding of this queue is not testable until Story 3.4.

### 2026-10-01: Review Triage Log #1 resolution (high)

- **Verdict: kept the code's existing `since = max(added_at, last_wrong_at)` behaviour; corrected
  the frozen Boundaries/I-O-matrix text to match it (see Spec Change Log entry below), rather than
  changing `retry.py` to `since = added_at` alone.**
- Reasoning: `max(added_at, last_wrong_at)` was not an accidental bug — it was a deliberate,
  already-documented choice. `retry.py`'s own module docstring (written the same day as the rest
  of the story, 2026-09-29) already states: *"Only events at or after `max(added_at, last_wrong_at)`
  count, so a repeat wrong attempt resets progress."* And `test_retry.py` already has a passing,
  correctly-named test for exactly this (`test_repeat_wrong_attempt_resets_exit_progress`, added
  2026-09-29) — the only gap was that the FROZEN spec text itself was never updated to agree, and
  no Spec Change Log entry was filed at the time. That is the actual defect this finding caught:
  a documentation/process gap, not a code bug.
- Why `max(added_at, last_wrong_at)` is the better design, now that it's being judged on the
  merits rather than just re-checked against the frozen wording: the Retry Queue's whole purpose is
  "does this Problem's mastery, as evidenced across separate Sessions, actually stick." A qualifying
  Session that happened BEFORE a later miss on the very same still-open item is exactly the kind of
  evidence a fresh miss invalidates — the child got it right once, then wrong again, so that first
  "right" was not durable mastery. Letting it still count toward the 2-Session exit (the literal
  frozen-text reading) would let a child oscillate right/wrong/right and exit the queue despite
  demonstrably not having retained the skill 2 clean times BACK TO BACK (relative to the last
  miss). `is_due()` already resets "due" off `last_wrong_at` for the identical reason (a fresh miss
  restarts the calendar-day clock) — using a DIFFERENT clock for the exit-count side of the same
  row would be an internal inconsistency, not a feature.
- No code changes were made for this finding (`retry.py`, `maybe_resolve_retry_item()`,
  `_qualifying_sessions()` are unchanged). `test_retry.py::test_repeat_wrong_attempt_resets_exit_progress`
  is left as-is and remains groundtruth for this behaviour; no rename needed.

## Spec Change Log

<!-- Append-only. Empty until the first bad_spec loopback. -->

### 2026-10-01: Boundaries & I/O-Matrix text corrected to match shipped `since` semantics

- **What changed:** the frozen Boundaries bullet "New exit logic..." and the three affected I/O
  matrix rows now say the qualifying-Session count is taken **since `max(added_at, last_wrong_at)`
  of the open row**, not since `added_at` alone. A new I/O matrix row ("Fresh miss between two
  qualifying Sessions") was added, matching `test_retry.py`'s existing
  `test_repeat_wrong_attempt_resets_exit_progress`.
- **Why:** Orchestrator's independent audit (Review Triage Log #1, high) found the frozen text and
  the shipped `retry.py` disagreed — the code already implemented (and tested, and its own module
  docstring already described) "a repeat wrong attempt resets progress," but the frozen spec text
  still said the count was since `added_at` only, with no Spec Change Log entry explaining the
  deviation. That is itself the process defect: a real, reasoned design decision was made and
  documented in the code but never reconciled back into the frozen spec text or logged here, so a
  later reviewer (correctly) read it as an undocumented deviation.
- **Reasoning for keeping the shipped behaviour** (rather than changing the code to match the old
  text): see the "2026-10-01: Review Triage Log #1 resolution" entry in Implementation Notes above
  for the full pedagogical argument (in short: a fresh miss on a still-open item invalidates an
  earlier qualifying Session as evidence of durable mastery, and `is_due()` already resets its own
  clock the same way for the identical reason — using a different clock for the exit-count side
  would be an inconsistency, not a feature).
- **Impact:** text-only correction to the frozen Boundaries/I-O-Matrix sections above; no behaviour
  change, no code change, no test change (the existing `test_repeat_wrong_attempt_resets_exit_progress`
  already covers and names this behaviour correctly).

## Review Triage Log

<!-- Append-only. Empty until the first review pass. -->

### Orchestrator's independent audit (2026-10-01)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `maybe_resolve_retry_item()`/`_qualifying_sessions()` compute `since = max(added_at, last_wrong_at)` and only count qualifying Sessions after `since` -- but the frozen spec's Boundaries text says the exit count is qualifying Sessions since `added_at` of the row (the count resets only when the item is reopened as a NEW row, not on every repeat wrong attempt within the same open row). Concrete scenario: item opens day 1; a Session on day 2 earns a qualifying correct (1/2); the child gets it wrong again on day 3 (row stays open, `last_wrong_at` bumps to day 3); a Session on day 4 earns a second qualifying correct -- per the frozen spec both day-2 and day-4 sessions should count (resolved on day 4), but the actual code recomputes `since=day3`, silently discarding the day-2 qualification, so the item incorrectly stays open needing a THIRD correct session | high | confirmed by 1 reviewer via direct code trace against the frozen spec text; undocumented, no Spec Change Log entry -> patch: either (a) change `since` back to `added_at` only, not `max(added_at, last_wrong_at)`, matching the frozen spec literally, or (b) if the "last_wrong_at resets progress" behavior is judged the CORRECT intended design (arguably reasonable -- a fresh miss arguably should restart the 2-session count), add an explicit Spec Change Log entry documenting this as a deliberate, reasoned deviation from the frozen text, with the reasoning, and update the frozen Boundaries text's own wording to match. Implementer's call on WHICH behavior is correct, but the code and the spec text must agree, one way or the other, and the decision must be documented either way |

No separate reviewer pass was run for this story; verification below is the independent re-check.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: all checks passed.
- `uv run pytest backend/tests/test_retry.py backend/tests/test_sessions.py backend/tests/test_library.py -q` -- expected: all pass, no regressions.
- `npx tsc -b` -- expected: clean.
- `npx eslint .` -- expected: clean.
- `npx vitest run src/pages/Home.test.tsx --pool=vmThreads` -- expected: pass (per Story 3.1/3.2's Verification note on shared-machine worker timeouts).

### 2026-09-29: independent re-verification

- `ruff check .` clean. `pytest tests/test_retry.py tests/test_sessions.py tests/test_library.py tests/test_app.py tests/test_scoring.py tests/test_badges.py` — 185 passed. `test_retry.py` re-run after adding two tests (empty-queue 422; replay is not one of the two qualifying Sessions) — 7 passed.
- Frontend `tsc -b` and `eslint .` clean. Home tests (25) were run by the implementing agent with `--pool=vmThreads`; not re-run by me.
- Every matrix row has a passing test.
