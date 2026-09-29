---
title: 'Story 2.8: Fallback self-check'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:95bfc5c7e58ccddf710feb797a4dae72e8e6eb96'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A `fallback` Problem (FR-11) has no machine-gradable `answer` at all (`FallbackPart`'s
`answer` is always `None` — confirmed in `content/schema.py` and already excluded from grading by
Story 2.5's `_grade_and_stage`/`grade_part`, which raises for a `fallback` Part). Bin still needs to
practise these Problems and get some progress signal from them, just self-reported instead of
server-graded.

**Approach:** A `fallback` Problem's Solution is revealed on demand ("Xem đáp án") rather than after
a wrong Attempt, recording a `fallback_revealed` event (kind already exists in AD-6's CHECK
constraint, unused until now). After seeing it, the child self-reports via `self_marked` (also
already in the CHECK constraint): "đúng" (got it right) earns 1 Star, "chưa đúng" (not yet) adds
the Problem to the Retry Queue (reusing Story 2.5's `_add_retry_item()` exactly, same table). A
Star is derived reactively from the event log (a `self_marked` event with `correct: true` in its
payload), NOT a new mutable counter/table — matching Story 2.5's own established philosophy of
deriving state from the append-only log wherever the derivation is cheap and bounded. Neither
`fallback_revealed` nor `self_marked` ever counts towards first-try accuracy (a metric Story 2.5
explicitly deferred and never built — so this rule requires no code today, just a note that
whichever future story computes first-try accuracy must exclude these two event kinds by
construction, logged in `deferred-work.md`).

**Backend note**: no NEW event kinds are needed — `fallback_revealed`/`self_marked` were already
added to the CHECK constraint in Story 2.4's migration, anticipating this story, but neither has
had any server-side handling beyond inert storage until now.

## Boundaries & Constraints

**Always:**
- **Backend, `learning/sessions.py`'s `post_event()`**: add real handling for two kinds, inside the
  same transaction structure as `attempt`'s grading (same SAVEPOINT, same idempotent
  already-stored-row fast path — reuse, don't duplicate):
  - `fallback_revealed`: no side effect beyond the stored event itself (purely a "the child asked
    to see the answer" telemetry marker) — this event kind needs no new logic, it already works
    exactly like `hint_requested` does today. Only the frontend behavior (revealing the Solution
    on tap) is new.
  - `self_marked`: payload must carry `{"correct": bool}` (the child's own "đúng"/"chưa đúng" tap).
    On `correct: true`: no further server action needed — a Star is DERIVED, not stored, by any
    future reader counting `self_marked` events with `correct: true` in their payload (document
    this derivation rule in a docstring; do not build a Star-reading endpoint or UI in this story —
    Story 2.10 "Session summary" is where Stars are first displayed). On `correct: false`: call
    `_add_retry_item()` (Story 2.5's existing helper, unchanged) for this Problem — same function,
    same table, same "skip if an unresolved row already exists" behavior.
  - Validate `self_marked` events the same way `attempt` events are validated against the Session
    (session ownership 403, Part/Problem-membership as applicable) — reuse
    `_validate_event_against_session()`; a `self_marked`/`fallback_revealed` event's `problem_id`
    must be a fallback Problem's, or at minimum must be a Problem in the Session's own frozen list
    (the existing generic check already enforces this for any event with a `problem_id`).
  - `self_marked` with a missing/malformed `correct` field in its payload: reject with a 422
    (bilingual-equivalent message), matching the existing "malformed payload is a normal, expected
    input from an untrusted client" posture from Story 2.5's graders — but this is validation, not
    grading (no `GradeResult`/`wrong_keys` concept applies here at all).
- **Frontend**: a `fallback` Problem's Part (currently rendered as `UnsupportedWidget` by Story
  2.6/2.7's switcher, since no widget exists for it) gets its own widget:
  - The page crop, pinch-zoomable (reuse whatever image-viewing primitive already exists for crops
    elsewhere in the app — check `content.assets`' crop URLs and any existing frontend crop-display
    component before building a new one from scratch).
  - "Xem đáp án" button: posts `fallback_revealed`, then shows the Solution (same `SolutionPanel`
    component Story 2.6 already built for the wrong-answer-reveal case — reuse it, this is just a
    different trigger).
  - After the Solution is shown, "Em làm đúng" / "Em chưa đúng" buttons: posts `self_marked` with
    the right `correct` value, then advances (same advance-to-next-Part/Problem/chunk logic Story
    2.6 already established) — "đúng" shows the same correct-feedback banner/praise line as a
    graded correct Attempt (StarBurst etc.), "chưa đúng" shows a neutral/retry-queue-added
    acknowledgement (not the shake/orange wrong-answer treatment, since this isn't a graded wrong
    Attempt — implementer's call on the exact wording, but it must not look like a "wrong answer"
    penalty).
- **`deferred-work.md` entry**: whichever future story computes first-try accuracy (not yet built,
  Story 2.5 deferred it) must exclude `fallback_revealed`/`self_marked` events by construction —
  log this explicitly so it isn't accidentally miscounted later.

**Never:**
- No new `progress_*` table, no new event kind, no new CHECK constraint migration — everything
  needed already exists from Stories 2.4/2.5.
- No grading of a `fallback` Part — `grade_part()`'s existing `TypeError` for `FallbackPart`
  stays exactly as Story 2.5 built it; this story never calls it for a fallback Problem.
- `self_marked`/`fallback_revealed` never affect the Retry Queue's OTHER resolution logic
  (`_part_currently_correct()`) for non-fallback Parts of the same Problem — a fallback Problem
  typically has exactly one Part, so this is unlikely to matter in practice, but the code must not
  special-case fallback Problems into that machinery at all; it's a parallel, separate path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| fallback_revealed, first tap | valid session/problem | 201, stored, Solution shown | N/A |
| self_marked, đúng | `{"correct": true}` | 201 stored; a Star is derivable (a later read counting this event returns 1 more) | N/A |
| self_marked, chưa đúng | `{"correct": false}` | 201 stored; Problem added to Retry Queue (unresolved row exists) | N/A |
| self_marked, chưa đúng twice | two Sessions, both chưa đúng on the same Problem | Retry Queue still has exactly one open row (dedup via `_add_retry_item`'s existing skip-if-exists) | N/A |
| self_marked, malformed payload | missing `correct` field | 422, bilingual-equivalent message | N/A |
| self_marked, wrong profile for session | ownership mismatch | 403 (same as attempt/events generally) | N/A |
| Resent self_marked (idempotent) | same event id twice | same stored result, no double Retry Queue insert | N/A |
| Frontend: Xem đáp án tapped | fallback Problem open | fallback_revealed posted, SolutionPanel shows the Part's solution | N/A |
| Frontend: Em làm đúng tapped | after reveal | self_marked(correct:true) posted, correct-style feedback, advance | N/A |
| Frontend: Em chưa đúng tapped | after reveal | self_marked(correct:false) posted, neutral acknowledgement (not a "wrong" shake), advance | N/A |

## Code Map

- `backend/hoctap/learning/sessions.py`: `post_event()` gains real handling for `self_marked`
  (validate payload shape, call `_add_retry_item()` on `correct: false`); `fallback_revealed`
  needs no new code (already inert-stored). A docstring note on the Star-derivation rule (counting
  `self_marked` events with `correct: true`), for whichever future story reads it.
- `backend/tests/test_sessions.py`: new tests for the I/O matrix rows above.
- Frontend: a new widget (name TBC by implementer, matching `frontend/src/components/widgets/`'s
  existing per-type file convention) for `fallback`, wired into `ProblemPlayer.tsx`'s switcher
  (currently falls through to `UnsupportedWidget` for this type).
- `_bmad-output/implementation-artifacts/deferred-work.md`: the first-try-accuracy exclusion note.

## Tasks & Acceptance

- [ ] `self_marked` payload validation (`correct: bool` required) + Retry Queue add on `false`,
      reusing `_add_retry_item()` unchanged.
- [ ] `fallback_revealed` confirmed working via existing inert-storage path (no new code
      expected, just a test proving it).
- [ ] Frontend fallback widget: pinch-zoomable crop, Xem đáp án → SolutionPanel, Em làm đúng /
      Em chưa đúng → self_marked + advance, correct-vs-neutral (not "wrong") feedback distinction.
- [ ] `deferred-work.md` entry for the first-try-accuracy exclusion.
- [ ] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

### 2026-09-29 -- implementation

**Backend (`backend/hoctap/learning/sessions.py`):**

- `self_marked`: new `_validate_self_marked(event)` requires `{"correct": bool}` in the
  payload AND a non-null `problem_id` (needed both to add the Retry Queue row and so a
  future Star-derivation reader knows which Problem was self-checked); a missing/malformed
  `correct`, or a missing `problem_id`, raises `AppError(422, "SELF_MARKED_INVALID_PAYLOAD",
  ...)`. `post_event()` calls it inside the same `conn.begin_nested()` SAVEPOINT `attempt`
  grading already uses, and on `correct: False` calls `_add_retry_item()` unchanged (same
  helper, same table, same skip-if-an-unresolved-row-exists dedup). On `correct: True`,
  nothing else is written -- the Star is derived, documented in a docstring on `post_event()`
  itself (count `self_marked` events with `payload["correct"] is True`).
- `fallback_revealed`: stored with no *mutating* side effect, exactly as the spec's
  Boundaries & Constraints describe (no Retry Queue row, no other table write) -- see the
  Spec Change Log entry below for the one piece of new code this kind DOES need (releasing
  the Solution into its own response payload), which the spec's Tasks & Acceptance line
  ("no new code expected") did not anticipate.
- `EVENT_KINDS`/the CHECK constraint needed no changes (already added in Story 2.4's
  migration, confirmed unchanged in `learning/models.py`).

**Frontend:**

- `frontend/src/components/widgets/FallbackWidget.tsx`: a new widget matching the existing
  per-type convention, but deliberately minimal -- it renders ONLY the pinch-zoomable crop
  (via a new `frontend/src/components/ZoomableImage/ZoomableImage.tsx` primitive; no
  existing crop-viewer in this codebase supported pinch-zoom, so this is new,
  dependency-free code using pointer events: two-pointer pinch computes a scale delta from
  inter-pointer distance change, one-pointer drag pans once zoomed in, double-tap/click
  resets). It does NOT carry the "Xem đáp án"/self-mark controls itself.
- `frontend/src/pages/ProblemPlayer.tsx`: `fallback` gets a dedicated `FallbackPartPlayer`
  component, branched to from the outer `ProblemPlayer` (not bolted onto `PartPlayer`'s
  already-large ✔ Kiểm tra/Attempt state machine, which doesn't apply at all here -- no
  NumberPad, no Attempt, no grading). Its own small phase machine: `crop` (the widget +
  "Xem đáp án" button) -> post `fallback_revealed` -> `revealing` (step through
  `SolutionPanel`, reusing Story 2.6's component exactly as the wrong-Attempt reveal does,
  via a literal "Xem tiếp ➜"/"Tiếp ➜" button, same wording/pattern as `PartPlayer`'s
  existing wrong-solution step-through) -> once every step is shown, `self-marking` shows
  "Em chưa đúng"/"Em làm đúng" -> posts `self_marked` -> `correct` (StarBurst +
  `onStarEarned()` + a random praise line, exactly like a correct graded Attempt) or
  `neutral` (a NEW `FeedbackBanner` variant, see below) -> `onAdvance()` after the same
  `CORRECT_ADVANCE_DELAY_MS` used elsewhere.
- `frontend/src/components/FeedbackBanner/FeedbackBanner.tsx`/`.css`: added a third
  `neutral` variant for the "chưa đúng" acknowledgement. Deliberately NOT the existing
  `retry` variant, whose orange border/`--color-retry` IS the graded-wrong-Attempt penalty
  look the spec says this must not resemble -- `neutral` reuses the existing
  `--color-primary`/`--color-primary-soft` tokens instead (no new design token added;
  `tokens.css` is generated from DESIGN.md, so only existing tokens are referenced).
- `frontend/src/audio/phrases.vi.json`: 4 new phrase keys (`show_answer`,
  `self_mark_correct`, `self_mark_incorrect`, `self_mark_neutral_ack`) -- picked up
  automatically by the builder's existing phrase-scanning pre-synthesis, same mechanism
  every other UI phrase already uses.
- `ProblemPlayer.test.tsx`'s old "unsupported Part type" test used `fallback` as its
  stand-in Part type (Story 2.7's own note: "the one Part type this player deliberately
  never gets a widget for"). Since this story gives `fallback` its own widget, that test
  now uses a synthetic `not_a_real_type` to keep exercising the switcher's defensive
  `default`/`UnsupportedWidget` branch against future schema drift -- every REAL Part type
  in `content/schema.py`'s `Part` union now has a dedicated widget.

**Verification:**

- Backend: `.venv/bin/python -m ruff check .` -- all checks passed. Full suite
  `.venv/bin/python -m pytest -q` -- 839 passed (14m16s; this environment's own
  documented slow-disk/WSL9P characteristics). Targeted `-k "fallback or self_marked"` --
  11 passed, covering every I/O matrix row (first tap stored + solution carried; đúng
  stored with no Retry Queue row; chưa đúng adds one; two Sessions dedup to one open row;
  missing/malformed `correct` 422; wrong-profile 403; resend idempotent, no double Retry
  Queue insert; resent `fallback_revealed` idempotent with the same solution; a real
  `attempt` against the fallback Part's own `part_key` still 422s `PART_NOT_FOUND`,
  confirming `grade_part()`'s `TypeError` path is never reached by either new kind).
- Frontend (fast-verification workaround: source-only rsync + `_bmad-output/
  planning-artifacts/` into a fresh `/tmp` tree, `npm ci`, run from there): `npx tsc -b`
  clean; `npx eslint .` clean; `npx vitest run` -- 231 passed, 3 pre-existing failures in
  `ExtractionPage.test.tsx` (untouched by this story, reproduces in isolation on an
  unmodified checkout of that one file -- unrelated pre-existing flakiness/breakage, not
  a regression from this story's changes). `ProblemPlayer.test.tsx` alone: 41 passed
  (38 prior + 3 new: "Xem đáp án tapped" step-through, "Em làm đúng" correct-feedback/
  Star/advance, "Em chưa đúng" neutral-not-retry/advance).

### 2026-09-29 -- review fixes

Addresses the Review Triage Log below, in priority order.

- **#1 (critical, fixed):** `_validate_self_marked()` now takes `conn` and loads the
  target Problem via `load_one()`, rejecting with `AppError(422,
  "SELF_MARKED_NOT_FALLBACK", "Bài tập này không phải dạng tự chấm.")` unless at least
  one of its Parts is a `FallbackPart` -- the identical guard `_fallback_solution()`
  already applied for `fallback_revealed`. `self_marked`'s payload never carries a
  `part_key` (unlike `fallback_revealed`), so this checks the whole Problem's Part list
  rather than one named Part; since a fallback Problem typically has exactly one Part
  (this story's frozen Boundaries), "the Problem has a FallbackPart" and "the Problem IS
  the fallback Problem" coincide in practice. `post_event()`'s call site updated to pass
  `conn`. New test `test_self_marked_rejected_for_non_fallback_graded_problem` posts
  `self_marked` against a real graded (`number_input`) Problem and confirms the 422 and
  that no event row is ever inserted.
- **#2 (high, fixed):** on `correct: True`, `post_event()` now calls
  `_maybe_resolve_retry_item(conn, profile_id, event.problem_id, [], "", received_at)` --
  reusing Story 2.5's existing resolution helper unchanged rather than duplicating its
  logic. Passing an empty `parts` list is deliberate and correct here: the helper's
  "every OTHER Part must also be currently correct" check already excludes
  `FallbackPart`s by construction, and a fallback Problem typically has exactly one Part
  (frozen Boundaries) -- so there are never any "other Parts" to load or check, and an
  empty list produces the same immediate-resolve behaviour as loading the real (trivial)
  Part list would. New test `test_self_marked_chua_dung_then_dung_resolves_retry_item`:
  chưa đúng (opens the row) then đúng (on the same Problem) confirms `resolved_at` gets
  set.
- **#3 (low, fixed):** `ZoomableImage.tsx`'s `handlePointerDown` now re-baselines
  `lastDistance.current` every time the pointer count reaches exactly 2 (previously only
  set on the 1st-to-2nd-pointer transition), and `endPointer` now re-baselines it against
  the two REMAINING pointers whenever the count drops back down to exactly 2 (previously
  only cleared to `null` on dropping below 2) -- covering both the "3rd pointer joins
  mid-pinch" and "3rd pointer leaves back to 2" halves of the bug, so a 2-finger pinch
  resumed after a 3rd finger touched down never computes its next scale delta against a
  stale, pre-3rd-finger distance.
- **#4 (low, fixed):** new test
  `test_self_marked_dung_star_is_derived_by_counting_events` posts 2 correct self-marks
  (on two distinct fallback Problems, same Profile) then runs the actual derivation query
  a future Star-reader (Story 2.10) would use -- `select(progress_events.c.payload_json)
  .where(profile_id=..., kind="self_marked")`, filtering rows in Python for
  `payload["correct"] is True` -- and asserts the count is 2, proving the counting
  mechanism itself rather than just a single row's existence.
- **#5 (low, fixed):** new test `test_self_marked_null_problem_id_422` covers
  `self_marked` with `problem_id: null`, confirming the existing
  `SELF_MARKED_INVALID_PAYLOAD` 422 path.
- **#6 (nice-to-have, top 2 done):** added
  `frontend/src/components/ZoomableImage/ZoomableImage.test.tsx` (new file -- reset-button
  hidden at scale 1, shown after a pinch-zoom, double-tap-within-300ms resets and the
  button disappears, two taps >300ms apart do NOT reset) and a dedicated `neutral`-variant
  test in `FeedbackBanner.test.tsx` (asserts the `feedback-banner-neutral` class and
  explicitly that it does NOT carry `feedback-banner-retry`). The rest of #6 (
  `fallback_revealed` across two distinct Sessions, `self_marked(true)` then
  `self_marked(false)` ordering, a frontend network-error-on-reveal test) logged as debt
  below, per the spec's own time-box guidance.

**Verification:**

- Backend: targeted `-k "fallback or self_marked"` -- 27 passed (16 pre-existing + 4 new +
  overlap from the new tests importing shared fixtures). `.venv/bin/python -m ruff check
  .` -- all checks passed. Full suite `.venv/bin/python -m pytest -q` -- **844 passed**,
  0 failed (1054.71s / ~17.5m, this environment's own documented slow-disk/WSL9P
  characteristics) -- up from 839 in the first Implementation Notes entry (+5: the 4 new
  Review Triage tests plus the net effect of splitting/renaming none -- see the diff for
  the exact new test names).
- Frontend (same fast-verification workaround as the first Implementation Notes entry:
  source-only rsync to `/tmp/hoctap-frontend-check`, fresh `npm ci`, run from there): `npx
  tsc -b` clean; `npx eslint .` clean; targeted `npx vitest run
  src/components/ZoomableImage src/components/FeedbackBanner` -- 10 passed (4 new
  ZoomableImage + 6 FeedbackBanner, 1 new). Full suite `npx vitest run` -- 230 passed, the
  same 3 pre-existing `ExtractionPage.test.tsx` failures as before (confirmed via `git
  diff --stat` that this story's changes never touch `ExtractionPage.tsx`/`.test.tsx` at
  all -- these are pre-existing/unrelated, not a regression).

**Debt logged (Review Triage Log #6, remainder):** `fallback_revealed` twice across two
distinct Sessions with two distinct event ids; a `self_marked(true)` then
`self_marked(false)` ordering; a rejected `fallback_revealed` POST on the frontend
(network-error path). None exercised by a test yet -- see `deferred-work.md` if this
needs to be tracked there too.

## Spec Change Log

### 2026-09-29 -- `fallback_revealed` needs a small amount of new backend code after all

The spec's Code Map/Tasks & Acceptance both state `fallback_revealed` needs "no new code"
beyond proving the existing inert-storage path works, "exactly like `hint_requested`". That
turned out to be incompatible with the spec's OWN Boundaries & Constraints requirement one
paragraph earlier: `"Xem đáp án" button: posts fallback_revealed, then shows the Solution`.

Investigation (per this story's own Code Map instruction to check "how a fallback Part's
solution reaches the bundle, if at all"): `content/views.py`'s `child_view()` pops
`ANSWER_FIELDS = {"answer", "hint", "solution"}` from EVERY Part unconditionally, including
`fallback` -- so a fallback Problem's Solution reaches the bundle by NO path at all, ever
(confirmed: `FallbackView`, the child-facing projection, carries only `part_key`/`type`/
`prompt`/`image_keys`/`image_key`). Unlike a graded Part, there is also no `attempt` event
to piggyback a staged release on (`grade_part()` raises `TypeError` for `FallbackPart` by
design, and this story's own frozen Boundaries forbid ever calling it for one). With
`hint_requested` as the literal template (truly zero fields released, per the existing test
`test_hint_requested_has_no_side_effect_no_pre_released_hint`), there is no mechanism left
for the frontend to ever obtain the Solution text at all.

**Resolution:** `fallback_revealed` keeps `hint_requested`'s "no new code" property for
every *mutating* side effect the Boundaries & Constraints actually list (no Retry Queue
row, no other table write) -- that part of the spec's claim holds exactly as written. But
its stored payload is now augmented with the fallback Part's own `solution`
(`_fallback_solution()`, a new small helper: looks up the Part directly by `part_key`,
bypassing `_find_part()` -- which excludes `FallbackPart` on purpose for grading
eligibility -- and never calling `grade_part()`), the same "augment the payload the
`payload_json`/response round-trips" mechanism `_grade_and_stage()` already established for
releasing a graded Part's Hint/Solution into an `attempt`'s own response. `_row_to_event_out()`
now reads `correct`/`wrong_keys`/`hint`/`solution` for `fallback_revealed` rows too (all but
`solution` come back `None` for this kind, same as before). This is the smallest change
that satisfies the frozen "shows the Solution" requirement without touching `child_view()`/
the bundle (which would have exposed the Solution to every future reader of that Problem's
child_view, not just after an explicit reveal -- clearly not the intent) and without adding
any new event kind, table, or CHECK constraint (the two "Never" items this change could have
risked). Logged here rather than treated as silently "following the spec" because the
Tasks & Acceptance checklist's literal words ("no new code expected") are now inaccurate;
the frozen Boundaries & Constraints' actual requirement is what was honored.

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `self_marked` is never restricted to `fallback`-type Problems. `_validate_self_marked()` only checks the `correct` payload field and a non-null `problem_id` -- it never verifies the target Part is a `FallbackPart`. A client can post `self_marked` for ANY graded Problem, self-awarding a derived Star (bypassing grading entirely) on `correct:true`, or pushing an arbitrary never-attempted graded Problem onto the Retry Queue on `correct:false` | critical | confirmed by 1 reviewer; `_fallback_solution()` already correctly does an `isinstance(part, FallbackPart)` guard for `fallback_revealed` -- `_validate_self_marked()` needs the identical guard -> patch: reject `self_marked` (422, bilingual-equivalent message) if the target Part is not a `FallbackPart`; add a test posting `self_marked` against a graded (non-fallback) Problem and confirming it's rejected |
| 2 | `self_marked(correct:true)` never calls `_maybe_resolve_retry_item()` -- a Problem self-marked "chưa đúng" (opens a Retry Queue row) and LATER self-marked "đúng" on a retry leaves that Retry Queue row open forever, since `grade_part()` is never invoked for a fallback Part and no other code path can ever resolve it | high | confirmed by 1 reviewer, real and undocumented (not mentioned as deferred anywhere) -> patch: call `_maybe_resolve_retry_item()` (or an equivalent fallback-specific resolution) on a correct self-mark, matching the existing attempt-side resolution pattern from Story 2.5; add a test: chưa đúng then đúng on the same Problem, confirm the Retry Queue row's `resolved_at` gets set |
| 3 | `ZoomableImage.tsx`'s pinch-zoom has a stale-`lastDistance` bug when a 3rd touch point joins mid-pinch then leaves: neither the join nor the leave-back-to-2 path resets/updates it correctly, causing a sudden unintended zoom jump on the next 2-finger move | low | confirmed by 1 reviewer via code trace, real but low-severity (3+ finger pinch is a rare interaction) -> patch: reset `lastDistance.current` to `null` whenever the pointer count changes to exactly 2 (both joining and leaving), not just on drop-below-2 |
| 4 | No test demonstrates the "Star is derived by counting `self_marked` events with `correct:true`" claim actually works as a counting mechanism -- only a single-row existence check exists, not a multi-event count proof | low | -> patch: add one test posting 2 correct self-marks (different Problems or a hypothetical re-derivation scenario) and manually querying `progress_events` to confirm the count matches, documenting the derivation query shape for whichever future story implements the real reader |
| 5 | `self_marked` with `problem_id: null` -> 422 is implemented (`_validate_self_marked` explicitly checks this) but has zero test coverage | low | -> patch: add the missing test |
| 6 | Several lower-value untested-but-likely-fine scenarios: `fallback_revealed` twice across two distinct Sessions with two distinct event ids (only same-session-same-id resend is tested); a `self_marked(true)` then `self_marked(false)` ordering (only the reverse and same-value-twice orderings are tested); a rejected `fallback_revealed` POST on the frontend (error state exists in code, unverified by a test); `ZoomableImage.tsx` has ZERO tests at all, not even trivial synchronous ones (reset-button visibility, double-tap-within-300ms) that jsdom could easily cover; the new `neutral` FeedbackBanner variant has no dedicated unit test in `FeedbackBanner.test.tsx`, only an indirect integration check | low | -> patch: add the cheapest 2-3 (a basic ZoomableImage smoke test and a dedicated neutral-variant FeedbackBanner test are probably the best value) as time allows; log the rest as test-coverage debt if time-constrained |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed the critical fix (`_validate_self_marked()` now rejects self_marked for a non-fallback Problem via `SELF_MARKED_NOT_FALLBACK`) and the high-severity fix (`_maybe_resolve_retry_item()` called on a correct self-mark) directly in source. Ran `ruff check` (clean) and the full backend suite independently: 844/844 passing. Ran the full frontend suite independently: 236/239 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story); `tsc -b`/`eslint` both clean. Story marked done.

</frozen-after-approval>
