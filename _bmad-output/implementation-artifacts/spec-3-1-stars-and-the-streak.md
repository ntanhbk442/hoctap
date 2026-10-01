---
title: 'Story 3.1: Stars and the Streak'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: '600ba9b51f18b9d0c100a84536d600651b6cda67'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing awards or stores a Star today. Story 2.8's "self_marked correct = a derived
Star" language and Story 2.10's `deferred-work.md` entries were explicit placeholders — "no
Star-reading endpoint or UI exists yet, by design." Story 2.10's Streak (`compute_streak()`) and
first-try-accuracy (`session_wrong_problem_ids()`) are already built and reactive/derived, but
Stars need something stronger: AD-6's literal rule is "materialised in the same transaction as the
event," which neither of those two functions does — they're computed on demand, not stored.

**Approach:** A new `progress_stars` table (one row per Problem-per-Session, written inside the
SAME transaction as the grading/self-mark event that resolves it — reusing the exact SAVEPOINT
structure `_grade_and_stage()`/`post_event()` already use) stores 3/2/1/0... **no — the AC is
literally 3/1/0** Stars per Problem: **3** if every Part of the Problem was first-try-correct within
this Session, **1** if a Hint (or a second try) was needed on any Part but no Part's Solution was
shown, OR the Problem is a `fallback` correctly self-marked "đúng", **0** if any Part's Solution was
shown (or a `fallback` marked "chưa đúng" — implementer's call whether "chưa đúng" is 0 or simply
never earns a row at all; document whichever is chosen). This is a genuinely NEW per-Problem
aggregation across Parts — Story 2.5's staged-help logic (`_count_prior_wrong()`) is per-Part, not
per-Problem, so this story adds the missing rollup. **Streak reuses `compute_streak()` unchanged**
(Story 2.10 already built exactly what this story's AC asks for) — this story's job for Streak is
purely surfacing it (Home display), not recomputing it. Total Stars is a new simple `SUM` over
`progress_stars` for the Profile.

**This story formally supersedes** Story 2.8's "Stars are derived reactively, no storage" language
and Story 2.10's "no Star-reading endpoint or UI exists yet" deferral — both `deferred-work.md`
entries should be marked resolved/superseded (not deleted — this codebase's convention is
append-only logs; add a closing note referencing this story). It does **not** touch or contradict
Story 2.10's first-try-accuracy metric (`session_wrong_problem_ids()`), which is a different,
narrower metric (only `attempt` events, used for the Session summary's "n/n correct" and "Luyện
lại bài sai") — Stars and first-try-accuracy are two separate, independently-computed things that
happen to share some of the same underlying `attempt`/`self_marked` events.

## Boundaries & Constraints

**Always:**
- **`progress_stars`** (new table, owned by `learning` per AD-2): `id` (UUIDv7), `session_id`,
  `profile_id`, `problem_id`, `stars` (0/1/3 — a `CHECK` constraint against exactly these 3 values,
  not an arbitrary int), `awarded_at`. One row per (session_id, problem_id) — written ONCE, when
  the Problem's outcome for that Session first becomes determinable (every Part has at least one
  attempt AND none is still "wrong-pending-a-later-attempt" — i.e., the same moment
  `_maybe_resolve_retry_item()`-style logic would consider the Problem "done" for this Session, OR
  a fallback Problem's `self_marked` event resolves it). New Alembic migration (next after whatever
  Story 2.11 lands with — check the actual head).
- **Per-Problem Star computation** (new function, e.g. `learning/scoring.py`'s
  `compute_problem_stars(conn, session_id, problem_id) -> int | None` — `None` if not yet
  determinable this Session): for a non-fallback Problem, inspect every Part's FIRST attempt within
  this Session (reuse the exact `session_id`-scoped, rowid-ordered pattern
  `session_wrong_problem_ids()` already established) — 3 if every Part's first attempt was correct;
  otherwise inspect whether any Part ever needed its Solution shown within this Session (0) vs. only
  ever needed a Hint/retry (1). For a `fallback` Problem, its single `self_marked` outcome maps
  directly: "đúng" → 1, "chưa đúng" → 0 or no row (implementer's call, document it).
- **Written inside the SAME transaction** as whichever event resolves the Problem — reuse
  `post_event()`'s existing SAVEPOINT (`conn.begin_nested()`), do not add a second commit boundary.
  Only `practice`, `retry`, and `concept` mode Sessions award Stars (per this story's own AC
  wording, matching AD-6's scoring-by-mode table from Story 2.10's research — `quiz` also scores
  per AD-6 but quiz Stars are Story 3.4's job, not this one; `replay` never awards Stars, matching
  the existing mode-gate pattern from Story 2.10).
- **Idempotency**: if a Problem's `progress_stars` row already exists for this Session (e.g. a
  resent event reaching the resolution point twice), do not insert a duplicate or overwrite a
  different value — same "already stored, no-op" posture as every other Story 2.5+ mutation.
- **`GET /sessions/{id}/summary`** (Story 2.10, extend it): add `stars_earned` (sum of this
  Session's `progress_stars` rows) alongside the existing `first_try_correct`/Streak fields.
- **A new Home-facing endpoint or extension** (implementer's call: extend `GET
  /library/home/{profile_id}` again, or a small new `GET /profiles/{id}/progress`-style endpoint)
  returning total Stars (all-time `SUM` for the Profile) and the current Streak (`compute_streak()`,
  unchanged, called from here).
- **Frontend**: Home shows a persistent Star total and Streak flame (a plain number is enough per
  Story 2.10's own deferred-work.md note — no calendar UI, no flame animation asset required, just
  a number with the 🔥/⭐ glyph and a phrase). The Session summary screen shows `stars_earned`
  (reusing `StarBurst`, already built and already used twice in `ProblemPlayer.tsx`'s correct-
  feedback path — wire a burst-to-Home-counter animation if cheap, but a static "Stars earned: n"
  on the summary screen satisfies the AC's literal wording even without the fly-animation if time-
  constrained; document whichever is delivered).

**Never:**
- No badges — Story 3.2.
- No Retry Queue exit-condition changes — Story 3.3 (the "2 separate Sessions" rule is a LATER
  story's job; this story's Retry Queue interaction is unchanged from Story 2.5/2.10).
- No quiz-mode scoring — Story 3.4.
- No changes to `content.schema`/`content.effective`/`content.catalog`/`content.library`/
  `content.speech`, and no changes to Story 2.10's `session_wrong_problem_ids()`/`compute_streak()`
  logic itself (call them, don't modify them).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Problem, all Parts first-try correct | 2-Part Problem, both correct first try | 3 Stars | N/A |
| Problem, a Hint needed on one Part, no Solution shown | 1 wrong then correct on one Part | 1 Star | N/A |
| Problem, a Solution shown on any Part | 2 wrong attempts on one Part | 0 Stars | N/A |
| Fallback, self-marked đúng | self_marked(true) | 1 Star | N/A |
| Fallback, self-marked chưa đúng | self_marked(false) | 0 Stars (or no row — document choice) | N/A |
| Replay-mode Session | any attempt in a replay Session | 0 Stars awarded, no progress_stars row | N/A |
| Resent resolving event | idempotent resend | no duplicate/changed progress_stars row | N/A |
| Total Stars, Home load | multiple Sessions with Stars | correct SUM across all non-replay Sessions | N/A |
| Streak display, Home load | consecutive completed days | matches compute_streak()'s existing value | N/A |
| Session summary | a completed Session with mixed outcomes | stars_earned matches the sum of that Session's own progress_stars rows | N/A |

## Code Map

- `backend/hoctap/learning/models.py`: `progress_stars` table.
- `backend/hoctap/db/alembic/versions/00XX_progress_stars.py`: new migration (check actual head).
- `backend/hoctap/learning/scoring.py` (new, per ARCHITECTURE-SPINE's own directory note) or a
  function added to `learning/sessions.py`/`summary.py` (implementer's call on file placement,
  document it): `compute_problem_stars()`, the write-on-resolution hook wired into
  `post_event()`'s existing `attempt`/`self_marked` handling.
- `backend/hoctap/api/sessions.py`: `GET /sessions/{id}/summary` gains `stars_earned`.
- `backend/hoctap/api/library.py` or a new small endpoint: total Stars + Streak for Home.
- `backend/tests/test_sessions.py`, a new `test_scoring.py` if scoring gets its own module.
- `frontend/src/pages/Home.tsx`: Star total + Streak display.
- `frontend/src/pages/SessionPlayer.tsx`: `stars_earned` shown on the summary screen.
- `_bmad-output/implementation-artifacts/deferred-work.md`: closing notes on the two superseded
  entries (Story 2.8's "Stars derived reactively" and Story 2.10's "no Star endpoint yet").

## Tasks & Acceptance

- [x] `progress_stars` table + migration.
- [x] Per-Problem 3/1/0 Star computation (Parts-aggregated for graded Problems, self_marked-mapped
      for fallback), written inside the same transaction as the resolving event.
- [x] Mode-gated: only `practice`/`retry`/`concept` award Stars; `replay` never does.
- [x] Idempotent: a resolving event's resend never duplicates/changes a Star row.
- [x] `GET /sessions/{id}/summary` gains `stars_earned`.
- [x] A Home-facing total-Stars + Streak endpoint/extension.
- [x] Frontend: Home shows total Stars + Streak (plain number, no new animation assets required);
      Session summary shows Stars earned this Session.
- [x] `deferred-work.md` closing notes on the two superseded entries.
- [x] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

- (2026-09-29) **File placement**: `compute_problem_stars()`/`maybe_award_stars()`/
  `session_stars_earned()`/`total_stars()` all live in a new `backend/hoctap/learning/scoring.py`,
  per the Code Map's own preference. `post_event()` (`learning/sessions.py`) calls
  `maybe_award_stars()` right after inserting the resolving event, inside the SAME
  `conn.begin_nested()` SAVEPOINT — no second commit boundary.
- (2026-09-29) **Determinability**: a graded Problem's outcome becomes determinable once every
  non-fallback Part has at least one `attempt` THIS Session and that Part's LATEST attempt this
  Session is correct (mirrors `_maybe_resolve_retry_item()`'s own "every other Part currently
  correct" moment, but scoped to this Session's own attempts, not Profile-wide). "Solution shown"
  is read directly off each stored `attempt` event's own `payload["solution"]` (non-null exactly
  when `_grade_and_stage()` released one) — never re-derived via `_count_prior_wrong()`'s
  Profile-wide count, which could disagree with what actually happened in THIS Session for a Part
  that also has prior-Session wrong attempts.
- (2026-09-29) **Fallback "chưa đúng" choice**: implementer's call, documented — a `0`-Star row
  IS written (not skipped), so `SUM(stars)`/`stars_earned` stay simple without a reader needing to
  know about a hidden "no row" third state.
- (2026-09-29) **Frontend**: Home (`Home.tsx`) shows a `⭐ n Tổng số ngôi sao` / `🔥 n ngày liên
  tiếp` line above the cards, hidden entirely when both are 0 (a fresh Profile). The Session
  summary (`SessionPlayer.tsx`) shows a static `"Ngôi sao em nhận được: n ⭐"` line alongside the
  existing `StarBurst` (which continues to show the DIFFERENT `first_try_correct` metric,
  unchanged from Story 2.10) — no fly-to-Home-counter animation was built (time-boxed per the
  spec's own allowance for a static line).
- (2026-09-29) Fixed two pre-existing tests that hard-coded the previous migration head/table set
  and the previous `LibraryHomeOut` shape: `test_app.py::test_fresh_data_dir_created_with_wal_and_migrations`
  and `test_library.py::test_home_nothing_visible_yet_is_a_friendly_null_not_a_crash`.

### 2026-10-01: Review Triage Log findings #2, #3, #4 (orchestrator's independent audit)

- **#2 (medium) — undetermined Star outcome at `session_completed`, practice/retry/concept modes.**
  Added `learning.sessions._warn_undetermined_star_outcomes()`, called from `post_event()`'s
  `session_completed` branch (only on the FIRST `session_completed` for a Session, guarded by the
  same `session.completed_at is None` check the `completed_at`-write itself uses). For any
  `STAR_AWARDING_MODES` Session, it diffs the frozen `problem_ids_json` against
  `progress_stars` rows already written for this `session_id`; any Problem id missing a row is
  logged as a single `log.warning(...)` line (module logger, `hoctap.learning.sessions`) naming
  the Session, Profile, mode, and the missing Problem ids.
  **Judgment call: log, not reject.** A hard 422 (matching quiz mode's `QUIZ_NOT_SUBMITTED`) was
  the first instinct, but quiz mode's guard is checking something structurally different: quiz is
  one all-or-nothing submit action, and "not yet submitted" is unambiguous. A practice/retry/
  concept Session completing with one Problem never attempted at all is, by contrast, an
  *already-legitimate, already-tested, deliberately-supported* state in this codebase — Story
  2.10's own `wrong_problem_ids`/summary semantics count a never-attempted Problem as "wrong" by
  design, and several pre-existing `test_sessions.py` tests (e.g.
  `test_summary_wrong_problem_ids_preserve_session_order`) complete a Session with a Problem that
  was never attempted, on purpose, to exercise exactly that. The server has no way to tell "the
  child chose to skip this one" apart from "the event was actually lost" — both produce identical
  server-side state (zero events for that Problem, this Session) — so a reject-based guard would
  have broken the legitimate, already-shipped case, not just the lost-event case the finding
  describes. A warning log makes the anomaly detectable and alertable without breaking normal
  Sessions. Checked this reasoning against the actual test suite rather than just in the abstract:
  grepping `test_sessions.py`/`test_scoring.py`/`test_retry.py`/`test_library.py` for
  `_completed(` call sites shows roughly a dozen tests that post `session_completed` with at least
  one Problem never attempted at all (e.g. `test_summary_wrong_problem_ids_preserve_session_order`'s
  own comment: `"bai-2: never attempted at all"`) — confirming the never-attempted case is
  genuinely load-bearing, existing, intended behaviour, not an oversight a reject-based guard
  would be safe to break.
  New tests: `test_scoring.py::test_session_completed_logs_when_a_problem_has_no_determinable_star_outcome`
  (asserts 201, no Star row, and the warning is logged) and
  `test_scoring.py::test_session_completed_no_warning_when_every_problem_is_resolved` (negative
  case, no false positives).
- **#3 (low) — a Problem doc mixing `FallbackPart` with graded Parts.** Chose the schema-level
  validator over a defensive runtime check in `scoring.py`: added `ProblemDoc._check_fallback_not_mixed()`
  (`content/schema.py`), called from the existing `_cross_refs` `model_validator(mode="after")`,
  rejecting (`ValueError`, surfaces as a Pydantic `ValidationError`) any Problem whose `parts` mix
  a `FallbackPart` with any non-`FallbackPart` Part. Chosen over a `scoring.py`-side defensive
  check/log because every path that can ever produce a `ProblemDoc` (content pipeline ingestion,
  hand-authored fixtures, a future content editor UI) already goes through this same Pydantic
  validation — rejecting it here means the ambiguous shape can never exist in stored content at
  all, rather than merely being caught (or silently logged) every time it's scored. New test:
  `test_problemdoc.py::test_problem_cannot_mix_fallback_and_graded_parts`.
- **#4 (low) — a corrected `self_marked` re-post on a fallback Problem was silently discarded for
  Star purposes.** `_fallback_stars()`'s docstring already stated (and still states) that it reads
  the LATEST `self_marked` event's verdict — the actual bug was that `maybe_award_stars()` only
  ever checked row EXISTENCE for idempotency, so the FIRST verdict froze permanently once any row
  existed, contradicting the docstring's own stated intent. **Judgment call: made the code match
  the docstring (re-evaluate and UPDATE), not the other way around.** Freezing the first verdict
  was considered as the "intentional, update the docstring instead" alternative, but rejected:
  nothing in this story's frozen Intent/Boundaries ever asked for a frozen-first-verdict anti-
  gaming rule, the docstring's claim was clearly the ORIGINAL intent (not a later edit that simply
  forgot to update the code), and "a genuine correction silently doesn't take effect, with zero
  user-visible signal" is a worse failure mode for a children's learning app than "a Star total can
  move by ±1/±3 if a self-mark is corrected soon after." Implementation:
  `maybe_award_stars()` now re-reads the existing row's `stars` alongside its `id` and, when the
  freshly computed value differs, `UPDATE`s that row (`stars`, `awarded_at`) instead of returning
  early; a matching value is still a no-op (no redundant write). This is intentionally not
  special-cased to fallback Problems — a graded Problem's computed value is stable once
  determinable within a Session (the facts "was any Part's Solution shown" / "was every Part
  first-try-correct" don't un-happen), so the UPDATE branch is a no-op for graded Problems in
  practice, keeping one idempotency rule instead of two. New test:
  `test_scoring.py::test_corrected_self_mark_updates_existing_star_row` (same row id before/after,
  `stars` changes from 0 to 1).

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

### Orchestrator's independent audit (2026-10-01)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 2 | `session_completed` only guards quiz-mode Sessions against an unresolved Problem (422 `QUIZ_NOT_SUBMITTED`) -- for `practice`/`retry`/`concept` Sessions there is no analogous check. If an `attempt`/`self_marked` event for one Problem is lost (dropped offline-outbox event, a client bug, a race) while the rest of the chunk completes normally, `session_completed` still succeeds silently, and that Problem's `compute_problem_stars()` returns `None` forever (its resolution is scoped to that Session's own attempts -- a later Session can't retroactively fix this Session's row). Stars/badge thresholds end up silently short with no error, no log, and no way to detect it after the fact | medium | confirmed by 1 reviewer; real but lower-frequency than #1 (requires an actual lost/dropped event, not a normal-path bug) -> patch: add the same kind of guard quiz mode already has -- before accepting `session_completed` for practice/retry/concept modes, check every Problem in the frozen `problem_ids_json` has a determinable Star outcome (at least one `attempt` or the Problem is fallback-type with a `self_marked`); if not, either reject with a clear error (matching quiz's pattern) or log a warning server-side so a missing-Problem-outcome is at least detectable. Implementer's call on reject-vs-log, document whichever is chosen |
| 3 | A Problem doc mixing a `FallbackPart` with graded Parts (nothing in `content/schema.py` prevents this -- `Problem.parts` is just `list[Part]` with `min_length=1`, `Part` a bare union including `FallbackPart`) causes `scoring.py`'s `any(isinstance(p, FallbackPart) for p in parts)` check to route the WHOLE Problem through fallback-only scoring, silently discarding any graded Parts' `attempt` events -- Stars would be driven entirely by the fallback tap, ignoring whether graded Parts were answered correctly | low | confirmed by 1 reviewer; currently likely unreachable given how content is authored today, but nothing structurally prevents it -> patch: either add a schema-level validator rejecting a Problem that mixes `FallbackPart` with any other Part type (the cleanest fix, prevents the ambiguous case from ever existing), or explicitly document in `scoring.py`'s docstring that this is an assumed invariant enforced elsewhere and add a defensive check/log if violated. Implementer's call, but the silent-discard behavior should not ship undocumented |
| 4 | A corrected `self_marked` re-post on a fallback Problem (e.g. "chưa đúng" tapped by mistake, corrected to "đúng" moments later) is silently discarded for Star purposes -- `maybe_award_stars()` only checks ROW EXISTENCE for idempotency, so once any Star row exists for (session_id, problem_id) the first verdict's Star value is permanently frozen, even though `_fallback_stars()`'s own docstring says it computes from the LATEST self_marked event (anticipating exactly this correction case) | low | confirmed by 1 reviewer; lower likelihood (needs an offline-retry or race to trigger in the current UI, which has no re-mark affordance in the same view) but a real, silent data-correctness gap with no user-visible signal that the correction didn't take effect | -> patch: either make `maybe_award_stars()` re-evaluate and UPDATE the existing Star row when a later `self_marked` for the same (session_id, problem_id) changes the verdict (matching `_fallback_stars()`'s own stated intent), or if freezing the first verdict is judged intentional (e.g. to prevent gaming), update `_fallback_stars()`'s docstring to stop claiming latest-event semantics and document the freeze explicitly. Implementer's call, but the code and the docstring must agree |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

### 2026-09-29: independent re-verification

- Backend: `uv run ruff check .` — all checks passed. `uv run pytest tests/test_scoring.py
  tests/test_sessions.py tests/test_library.py tests/test_app.py -q` — **168 passed, 0
  failed** (7:59). Confirms all 10 I/O-matrix rows in `test_scoring.py` (3/1/0 computation,
  fallback đúng/chưa đúng, replay-mode no-award, idempotent resend, session-summary
  `stars_earned`, Home total/streak) actually ran and passed.
- Frontend: `npx tsc -b` — clean. `npx eslint .` — clean. `npx vitest run
  src/pages/Home.test.tsx --pool=vmThreads` — 20 passed (the default `forks` pool hit the
  same shared-machine worker-startup timeout documented in Story 2.11's Verification;
  `vmThreads` reliably avoids it). `npx vitest run src/pages/SessionPlayer.test.tsx
  --pool=vmThreads` — 12 passed, 0 failed; 11 "unhandled rejection" noise entries
  (`speechKey`'s `crypto.subtle.digest` rejecting in jsdom, from a fire-and-forget `speak()`
  call unrelated to this story) — confirmed **pre-existing**: reproduced identically
  (same count, same test names) on a `git stash`-ed pre-3.1 tree, so not a regression from
  this story's changes.
- Tasks & Acceptance: all 9 checked. Matrix: all 10 rows covered by a passing test in
  `test_scoring.py`.

</frozen-after-approval>
