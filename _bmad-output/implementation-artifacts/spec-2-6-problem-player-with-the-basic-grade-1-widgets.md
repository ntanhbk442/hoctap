---
title: 'Story 2.6: Problem player with the basic grade-1 widgets'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:7c08c93dcfcef390d3f63871ec6fba6f51df068f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `SessionPlayer.tsx` (Story 2.4) only lists a chunk's Problems read-only. Bin can't
actually answer anything yet, even though Story 2.1 already built every presentational piece
(`AnswerSlot`, `NumberPad`, `ChoiceChip`, `FeedbackBanner`, `HintBubble`, `SolutionPanel`,
`StarBurst`) and Story 2.5 (dependency — must land first, see Boundaries) makes `POST
/sessions/{id}/events` grade an `attempt` and return the verdict plus staged Hint/Solution text.

**Approach:** Turn `SessionPlayer.tsx` into a real, one-Problem-at-a-time player for the 5 "basic"
Problem Types (`number_input`, `compare`, `multiple_choice`, `number_tree`, `count_image`): a
per-type widget renders the Part's `ChildProblemView` data (never contains `hint`/`solution` —
`content.effective.child_view()` strips them, so this player can ONLY ever see them via a graded
`attempt` response), tracks the child's in-progress selection locally (nothing is sent to the
server until ✔ Kiểm tra), submits an `attempt` event on Check, and reacts to the graded result:
green+chime and a rotating praise line on correct, orange-shake+boop then (after a 400ms gap) the
Hint bubble on a first wrong attempt, the Solution panel (steps revealed one at a time) on a second
wrong attempt.

## Boundaries & Constraints

**Always:**
- **Hard dependency on Story 2.5**: this story cannot be built (or even meaningfully spec'd in
  final form) until Story 2.5's exact `EventOut` grading-response shape (correct, wrong_keys, hint
  text, solution) is committed and stable. This spec's shapes below are the ORCHESTRATOR'S OWN
  design for Story 2.5 and are expected to match, but the implementer must re-read the actual
  landed `learning/sessions.py`/`api/sessions.py` response shape before writing any frontend call
  site, and flag in Implementation Notes if it differs from what's assumed here.
- **Widget-per-type switcher** in `SessionPlayer.tsx` (or a new sub-component it renders, e.g.
  `ProblemPlayer.tsx` — implementer's call on file split): given the current chunk's current
  Problem's `ChildProblemView`, pick the widget by its Part's `type`:
  - `number_input`/`number_tree`: render the Part's `template`/`nodes` with a tappable `AnswerSlot`
    per empty slot (UX-DR9: "tap a slot, then type on the number pad"); tapping a slot makes it
    active; the on-screen `NumberPad` writes into whichever slot is active.
  - `compare`: three `ChoiceChip`s (`<`, `=`, `>`) per row; tapping one fills that row's slot
    (UX-DR9).
  - `multiple_choice`: one `ChoiceChip` per option; tap selects (not submitted until ✔); respect
    `multi` (multi-select) vs single-select from the View.
  - `count_image`: the Part's image plus the `NumberPad`; tapping the image places a small dot
    (UX-DR9: "not graded" — purely a counting aid, never sent to the server, local-only UI state).
  - A Part type outside these 5 (e.g. `order`, `match`, the Story 2.7/2.8 types) is out of scope —
    if a Session's Problem contains one, show a clear "chưa hỗ trợ" (not yet supported) placeholder
    rather than crash; this is expected sequencing (Story 2.7 adds them), not a bug to silently
    paper over.
- **✔ Kiểm tra gating**: enabled only when every slot/selection of the CURRENT Part is filled (per
  its `answer`-shape's own slot/selection count — reuse the same "every key must be present" idea
  Story 2.5's graders use, but here it's just a client-side completeness check, not grading).
- **Submit flow**: on ✔, `POST /sessions/{id}/events` one `attempt` event (client UUIDv7,
  `problem_id`, `payload: {part_key, value}` in whatever shape Story 2.5's graders expect for that
  Part type — re-confirm the exact shape from the landed code, don't assume). Disable ✔ and the
  widget's inputs while the request is in flight (no double-submit).
- **Correct feedback**: `AnswerSlot`/`ChoiceChip` state → correct (green); `FeedbackBanner`
  variant correct, a phrase randomly chosen from `praise_1`..`praise_6`
  (`frontend/src/audio/phrases.vi.json`, already built) with its audio spoken (`speak()`, Story
  2.2); a brief `StarBurst`. Then advance to the next Part of the same Problem, or the next Problem
  in the chunk if that was the last Part, or the chunk's own "done" state if it was the last
  Problem — implementer's call on the exact advance target as long as it's reachable and doesn't
  strand the child on a completed Problem with no way forward.
- **Wrong feedback, first attempt** (0 prior wrong per Story 2.5's response): shake + orange
  (`AnswerSlot`/`ChoiceChip` wrong state) + "boop" sound; after a 400ms gap (UX-DR7's literal
  timing), show `HintBubble` with the returned hint text, its audio auto-playing once
  (UX-DR7: "auto-play... one clip at a time... replay is free"). The child can still retry the
  same Part (inputs re-enabled after the wrong feedback settles).
- **Wrong feedback, second attempt** (≥1 prior wrong, per Story 2.5's response — Solution
  released): open `SolutionPanel` with the returned steps, revealed one at a time (implementer's
  call on the exact reveal trigger — a tap-to-advance or a timed auto-advance; UX-DR7's "one clip
  at a time" suggests each step's audio must finish or be tappable before the next reveals), each
  step's text spoken via `speak()`; end with "Tiếp ➜" (the existing `next` phrase) to move on
  (same advance-target rule as the correct case).
- **Layout** (UX-DR12): tablet portrait — work area top, action bar (NumberPad + ✔) fixed at the
  bottom; tablet landscape — 60/40 split; PC — centered, max 1024px width. Reuse the existing CSS
  approach from Story 2.1's components (tokens.css custom properties, no new hardcoded pixel
  values where a token already exists).
- **Accessibility**: every widget keeps the ≥64px touch targets and no-color-only-state rules
  already enforced by the Story 2.1 components (`AnswerSlot`/`ChoiceChip` already carry these —
  reuse them, don't re-implement their internals). `useMotion()` (Story 2.1) gates any new
  animation (shake, StarBurst) exactly like existing components do.

**Never:**
- No changes to `content.schema`, `content.effective`, `learning.graders`, or the `POST
  /sessions/{id}/events` backend contract itself — this story is a pure frontend consumer of
  Story 2.5's API.
- No widgets for `order`, `match`, `image_select`, `grid_fill`, `dot_draw`, `connect_dots`,
  `spot_difference` — Story 2.7.
- No Fallback self-check UI — Story 2.8.
- No changes to the Story 2.1 components' own internal implementation beyond what's strictly
  needed to consume them (e.g. do not change `AnswerSlot`'s accessibility behavior; if a prop is
  missing for this story's needs, ADD a prop, don't rewrite the component).
- `count_image`'s tap-to-dot counting aid is never sent to the server and never affects grading —
  purely local UI state, reset per attempt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| number_input, all slots filled | tap slot, type digits | ✔ enabled | N/A |
| number_input, slots incomplete | one slot empty | ✔ disabled | N/A |
| compare, tap a chip | tap `<` | that row's slot fills with `<` | N/A |
| multiple_choice single-select | tap option B then option A | only A selected (single-select) | N/A |
| multiple_choice multi-select | `multi: true`, tap two options | both stay selected | N/A |
| count_image, tap image | tap 3 times | 3 dots shown locally, NumberPad unaffected, nothing sent | N/A |
| Correct attempt | server returns correct: true | green + chime + praise line + StarBurst, advances | N/A |
| First wrong attempt | server returns correct: false, hint text, 0 prior wrong | shake + orange + boop, then (400ms later) HintBubble with audio | N/A |
| Second wrong attempt | server returns correct: false, solution steps | SolutionPanel opens, steps reveal one at a time with audio, then Tiếp ➜ | N/A |
| Submit in flight | ✔ tapped, request pending | ✔ and inputs disabled, no double-submit | N/A |
| Unsupported Part type in the chunk | e.g. an `order` Problem mixed into a Lesson | "chưa hỗ trợ" placeholder, no crash | N/A |
| Last Part of last Problem answered correctly | end of chunk reached | a reachable "done" state (implementer's call on exact UI, e.g. link back to Library or the next chunk) | N/A |
| Network error on submit | POST /events fails | error message shown, ✔ re-enabled, no local state lost | N/A |

## Code Map

- `frontend/src/pages/SessionPlayer.tsx` — becomes the real player (or delegates most of its body
  to a new `ProblemPlayer.tsx`/similar, implementer's call).
- `frontend/src/components/widgets/` (new, or colocated under `pages/` — implementer's call): one
  small component per Part type (`NumberInputWidget`, `CompareWidget`, `MultipleChoiceWidget`,
  `NumberTreeWidget`, `CountImageWidget`), each composing the existing Story 2.1 components.
- `frontend/src/api/queries.ts` — a `usePostAttempt()`/similar mutation hook (extends the existing
  event-posting pattern from Story 2.4, if one isn't already generic enough to reuse as-is).
- `frontend/src/pages/SessionPlayer.test.tsx` (+ new widget test files) — cover the I/O matrix
  above.
- No backend files — this story is frontend-only.

## Tasks & Acceptance

- [ ] Re-confirm Story 2.5's exact landed `EventOut`/grading-response shape before writing any
      call site; note any deviation from this spec's assumptions in Implementation Notes.
- [ ] Widget-per-type switcher for the 5 basic types, each composing existing Story 2.1 components
      (no reimplementation of their internals).
- [ ] ✔ Kiểm tra gating (enabled only when the current Part is complete).
- [ ] Submit flow: one `attempt` event per Check, disabled state while in flight.
- [ ] Correct feedback: green/chime/rotating praise line/StarBurst, advance logic.
- [ ] First-wrong feedback: shake/orange/boop, 400ms-delayed HintBubble with audio.
- [ ] Second-wrong feedback: SolutionPanel step-through with audio, Tiếp ➜ to advance.
- [ ] Unsupported Part type placeholder (no crash).
- [ ] UX-DR12 responsive layout (portrait/landscape/PC).
- [ ] All new tests pass; `tsc -b`/`eslint`/full frontend suite clean (via the `/tmp` fast-sync
      workflow); no regression in Story 2.1/2.2/2.3/2.4's existing tests.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-29 — Implementation

**Story 2.5 API shape re-confirmed.** Read the actual landed `backend/hoctap/api/sessions.py`
and `backend/hoctap/learning/sessions.py`. `EventOut` has `correct: bool | None`,
`wrong_keys: list[str] | None`, `hint: str | None`, `solution: Solution | None` exactly as this
spec assumed, with one operationally important detail confirmed by reading
`_grade_and_stage()`: `hint` is set on EVERY wrong attempt (not only the first), and `solution`
is set only from the 2nd wrong attempt onward (`prior_wrong >= 1`) — so the frontend branches
on `result.solution` truthiness to pick Hint-bubble vs Solution-panel, not on a separate
attempt counter of its own. `Solution` is `{steps: string[], final: string}`.

**Frontend's generated `schema.d.ts` was stale and had to be regenerated first.** Story 2.5's
commit added `correct`/`wrong_keys`/`hint`/`solution` to the backend's `EventOut` but never
re-ran `npm run gen:api` — `frontend/src/api/schema.d.ts`'s `EventOut` still had only the
Story 2.4 fields. Regenerated it via `uv run hoctap export-openapi --out ../frontend/openapi.json`
(backend) + `npm run gen:api` (frontend) — both read-only introspection of the already-landed
backend, no backend source touched. This was necessary before writing any call site (the spec's
own Boundaries instruction), and both `frontend/openapi.json` and `frontend/src/api/schema.d.ts`
are included in this story's diff as a result.

**File split**: `SessionPlayer.tsx` stays the page-level orchestrator (bundle fetch, chunk
label, loading/error/session-gone states, and now "which Problem of the chunk is current" +
a running `stars` count). All per-Problem/per-Part player logic moved to a new
`frontend/src/pages/ProblemPlayer.tsx`, which internally splits into two components:
- `ProblemPlayer` (exported): owns only `partIndex` within one Problem.
- `PartPlayer` (module-private): owns everything about answering ONE Part -- values/selection,
  the widget switcher, ✔ gating, the `attempt` submit flow, and the
  correct/wrong-first/wrong-second feedback sequence.

`ProblemPlayer` renders `<PartPlayer key={part.part_key} .../>` -- remounting `PartPlayer` on
every Part change, rather than a `useEffect` that resets a dozen `useState`s on `partIndex`
change. This was not just a style choice: the `useEffect`-reset version tripped this repo's
`react-hooks/set-state-in-effect` lint rule (cascading-render warning), and React's own
guidance is that a `key` change is the intended tool for "reset all state when the identity of
what I'm showing changes." One followed consequence: `CountImageWidget`'s local dot state and
`AnswerSlot`'s per-Part values never need an explicit reset -- they die with the remount.

Five widgets under `frontend/src/components/widgets/` (`NumberInputWidget`, `CompareWidget`,
`MultipleChoiceWidget`, `NumberTreeWidget`, `CountImageWidget`), plus `UnsupportedWidget` for
any Part type outside the 5. Each is a controlled, presentation-only composition of Story 2.1's
components; all answer state lives in `PartPlayer` (`components/widgets/types.ts`'s
`WidgetProps<P>`).

**Advance logic (implementer's call, as invited by the spec):**
- Correct: `PartPlayer` shows the green/chime/praise/StarBurst feedback, then
  `window.setTimeout(onAdvance, 1200ms)` -- a fixed, generous-but-not-endless pause (no spec
  literal value given for this one, unlike the 400ms wrong-feedback gap).
- Next Part vs next Problem vs chunk "done": `ProblemPlayer.advance()` moves to the next
  Part index if one remains in the current Problem's `parts`, else calls `onDone()` up to
  `SessionPlayer`, which increments `problemIndex`. When `problemIndex` reaches the end of the
  chunk's `problems`, `SessionPlayer` shows a "done" state (`session_summary` phrase) with
  either a "Phần tiếp theo ➜" button (more chunks left) or nothing further (the page's own
  permanent "Về Sách" link already covers going back) -- never stranding the child on a
  completed Problem.
- Unsupported Part type: shown with a "chưa hỗ trợ" placeholder and its own plain "Tiếp ➜"
  button (no Check, nothing gradeable) that calls the SAME `onAdvance`/`onDone` path.

**Solution step-reveal trigger (implementer's call): tap-to-advance**, not timed. Each tap on
"Xem tiếp ➜" reveals the next step and speaks it; once every step is revealed, the same button
becomes "Tiếp ➜" (the existing `next` phrase) and advances instead. Chosen over a timed
auto-advance because UX-DR7's "one clip at a time" implies each step's audio should be allowed
to finish (or be interrupted deliberately) before the next one starts, and a young child's
reading/listening pace for a multi-step Solution is far less predictable than the fixed
400ms-gap or the 1200ms correct-pause -- both of which ARE literal/short enough for a timer.

**`usePostEvent()` reused as-is**, not a new `usePostAttempt()` hook: it already takes
`{profileId, events}` and is generic over `kind`, so `PartPlayer` just posts one `attempt`
event through it directly. No frontend generic-enough gap to fill.

**New `frontend/src/ids.ts` (`newEventId()`)**: a client-side UUIDv7 generator. The codebase
had no UUIDv7 generator on the frontend (only Python's `uuid.uuid7()` backend-side) and no
`uuid` npm package -- `crypto.randomUUID()` produces UUIDv4, which the backend's `_is_uuid7()`
(`uuid.UUID(value).version == 7`) rejects with a 422. Implemented per RFC 9562 §5.7: 48-bit
`unix_ts_ms`, version nibble `0111`, variant bits `10`, the rest from `crypto.getRandomValues`.

**New `frontend/src/audio/sfx.ts` (`playChime()`/`playBoop()`)**: short, fixed (non-TTS) sound
effects for the correct/wrong feedback, mirroring `speech.ts`'s `speak()` silent-no-op-on-
failure contract exactly (no `Audio` support, no file yet at the path, blocked playback -- all
inert, never a thrown/rejected error the caller must guard). **No `chime.mp3`/`boop.mp3` asset
files ship with this story** -- generating/curating actual sound effect assets is a
builder-pipeline concern this frontend-only story has no mandate to touch (the Boundaries list
forbids backend changes, and there is no existing SFX-asset concept in `content/assets.py` to
extend). Both calls are inert today, exactly like `speak()` before a phrase's TTS clip has been
synthesised -- this is a deliberate, documented gap, not a bug.

**`ChoiceChip` gained one new prop, `variant?: 'correct' | 'wrong'`** (Boundaries &
Constraints explicitly allows adding a prop rather than reimplementing internals). It reuses
`AnswerSlot`'s exact success/retry palette and its own `useMotion()`-gated shake, and is
additive/optional -- every existing call site and test is unchanged and still passes.

**Payload shapes sent on `attempt`** (matching `learning/graders.py`'s own documented
submitted-value shapes exactly, confirmed by reading that module rather than re-guessing):
- `number_input`/`number_tree`/`count_image` (all `NumericEntry`-keyed): `{part_key, value:
  [{key, value}, ...]}`, one entry per slot/empty-node.
- `compare`: same keyed-list shape, `value` one of `"<"`/`"="`/`">"`.
- `multiple_choice`: `{part_key, value: {selected: [...]}}`.

**`count_image`'s tap-to-dot counting aid** is `CountImageWidget`'s own local `useState`,
reset for free by the Part-level remount described above; it is never read by `PartPlayer`,
never part of `buildValue()`, and a test (`ProblemPlayer.test.tsx`) asserts the posted payload
never contains anything dot-related.

**Test file split**: `SessionPlayer.test.tsx` covers page-level orchestration only (chunk
label, loading/error/session-gone/empty-chunk states, and the chunk-done/"Phần tiếp theo"
transition) since that page-level behavior fundamentally changed from Story 2.4's read-only
browsable list to this story's real one-Problem-at-a-time flow -- the old "marks an attempted
Problem" and "Phần sau/trước switch chunks while browsing" tests no longer describe anything
the new UI does (browsing a chunk's Problems freely is gone; a chunk's Problems are now played
through in order) and were replaced rather than kept red. All of the I/O & Edge-Case Matrix's
per-widget/per-Part-type scenarios live in one consolidated `pages/ProblemPlayer.test.tsx`
(covering `number_input`, `compare`, `multiple_choice` single/multi-select, `count_image`,
correct/first-wrong/second-wrong/in-flight/network-error/unsupported-type) rather than one file
per widget component -- the widgets are thin enough that testing them through `ProblemPlayer`
exercises their real integration (slot state, active-slot routing, NumberPad wiring) more
usefully than isolated unit tests would.

**Deviations from this spec's literal text**: none of substance. Two bugs were caught during
implementation, not deviations: (1) the correct-feedback banner initially always showed
`praise_1`'s text regardless of which praise phrase was actually spoken by `speak()` --
fixed by storing the chosen praise key in state; (2) the bottom action bar's "no
Check/NumberPad" fallback branch (`Tiếp ➜`) was originally keyed on `!showNumberPad &&
!showCheck`, which is ALSO true during the Solution-panel phase (which already renders its own
"Xem tiếp ➜"/"Tiếp ➜" button inline) -- producing two "Tiếp ➜" buttons at once. Fixed by keying
the fallback strictly on `!supported` (an unsupported Part type) instead.

**Verification** (via the `/tmp` fast-sync workflow -- `rsync --exclude=node_modules
--exclude=dist --exclude=dev-dist` to `/tmp/hoctap-fe/frontend`, plus
`_bmad-output/planning-artifacts/` alongside it, then a fresh `npm ci`):
- `npx tsc -b` -- clean, 0 errors.
- `npx eslint .` -- clean, 0 errors/warnings.
- `npx vitest run` (full suite) -- 196 passed, 3 pre-existing failures in
  `src/pages/ExtractionPage.test.tsx` (unrelated: `ExtractionPage`/its run-progress polling,
  never touched by this story). Confirmed pre-existing by running the SAME test file, unmodified,
  from a clean `git worktree add --detach HEAD` checkout of this branch before any of this
  story's changes -- identical 3 failures there too.
- The new `pages/ProblemPlayer.test.tsx` (22 cases) and rewritten `pages/SessionPlayer.test.tsx`
  (7 cases) cover the full I/O & Edge-Case Matrix: ✔ gating (complete/incomplete), compare-chip
  tap, multiple-choice single/multi-select, count_image dots-are-local-only, the correct/first-
  wrong/second-wrong/in-flight/network-error attempt outcomes, the unsupported-Part-type
  placeholder, and the chunk-done/"Phần tiếp theo" transition.
- No real network or TTS calls in any test: `mockApi()` throughout;
  `speak()`/`playChime()`/`playBoop()` all hit jsdom's stubbed, no-op `HTMLMediaElement.play()`
  (logged as "Not implemented" by jsdom, not a failure).

### 2026-09-29 — Review fixes

Addressed all 3 high-severity findings, all 3 medium-severity findings, and the two
highest-value low-severity gaps from the Review Triage Log below. All changes are additive
to `frontend/` only; no backend files touched.

- **#1 (high) fixed**: `ProblemPlayer.tsx`'s `HintBubble` render condition was
  `phase === 'wrong-hint' || phase === 'wrong-solution'`, so on a second wrong attempt the
  stale first-attempt Hint rendered stacked above the `SolutionPanel`. Narrowed to
  `phase === 'wrong-hint'` only -- the `SolutionPanel` branch already renders on its own.

- **#2 (high) fixed**: `count_image`'s dot-placement aid only reset on a Part change (via
  the existing `key={part.part_key}` remount of `PartPlayer`), never on a same-Part retry
  after a wrong attempt. Added `PartPlayer`'s own `attemptSeq` counter, bumped inside
  `retryIfSettled()` (the same function that already flips `phase` back to `'answering'` on
  the first post-wrong interaction), and passed as `CountImageWidget`'s `key` in the widget
  switcher -- a retry now remounts just the counting-aid widget, clearing its dots, without
  disturbing any other Part-level state (`values`/`selected`/`activeSlot` are untouched, as
  they must survive a retry). Added a test in `ProblemPlayer.test.tsx`
  ("resets dots on a retry after a wrong attempt, on the SAME Part") that places 3 dots,
  submits wrong, confirms the dots are still visible while the Hint is showing (not
  eagerly cleared mid-feedback), then retries and confirms the dot count drops to 0 before
  new dots are placed.

- **#3 (high) fixed**: added a synchronous `useRef<boolean>` guard (`submittingRef`) in
  `PartPlayer`, checked-and-set at the very top of `handleCheck()` before any `setState`
  call, so a second tap in the same event-loop tick (before React re-renders the
  state-derived `disabled` prop) is a definite no-op. The ref is cleared again exactly where
  Check becomes retriable: the submit-error `catch` branch and `retryIfSettled()`. Added a
  test in `ProblemPlayer.test.tsx` ("a synchronous double-tap on ✔ posts exactly one
  `attempt` event") firing `fireEvent.click` on Check twice with no `await` in between, then
  asserting exactly one `/events` POST landed.

- **#4 (medium) fixed**: added an optional `disabled?: boolean` prop to `NumberPad`
  (defaults to `false`, every existing call site unchanged) that disables all 12 keys; wired
  from `ProblemPlayer` as `disabled={disabled}` (the same flag already gating the widgets and
  the Check button during `submitting`/`wrong-shake`/`wrong-solution`/`correct`).

- **#5 (medium) fixed**: `ChoiceChip.test.tsx` (already existed from Story 2.1, but had no
  coverage of the new `variant` prop) gained 4 cases: default/no-variant has neither graded
  class, `variant="correct"` applies `choice-chip-correct`, `variant="wrong"` applies both
  `choice-chip-wrong` and `choice-chip-shake`, and the shake is suppressed when
  `useMotion()` reports `reduced` (mocked the same way `StarBurst.test.tsx` already does).
  Also extended `ProblemPlayer.test.tsx` with 4 new cases -- one correct- and one
  wrong-attempt case each for `compare` and `multiple_choice` -- asserting the graded chip
  carries `choice-chip-correct`/`choice-chip-wrong` after the attempt resolves.

- **#6 (medium) fixed**: added a test ("pins the displayed praise-banner text to the
  actually-spoken phrase") that stubs `Math.random()` to force a specific praise key,
  spies on the mocked `speak()` (`vi.mock('../audio/speech', ...)`, matching the existing
  pattern in `Home.test.tsx`), and asserts the banner's rendered text equals both
  `phrase('praise_6')` and the exact string `speak()` was last called with -- pinning the
  banner-text-matches-spoken-phrase invariant the bug already fixed once during
  implementation (see the original Implementation Notes entry above).

- **#7 (low) -- did the top 2, as invited**: added "a multi-Part Problem advances from Part
  a to Part b, not to onDone, on a correct attempt" to `ProblemPlayer.test.tsx` (a 2-Part
  Problem, answers Part `a` correctly, asserts Part `b`'s own empty slot appears and `onDone`
  is NOT yet called, then answers Part `b` and confirms `onDone` fires once), and "advances
  from Problem 1 to Problem 2 within one chunk" to `SessionPlayer.test.tsx` (a 2-Problem
  chunk, answers Problem 1 correctly, asserts Problem 2's label appears and Problem 1's does
  not). The remaining low-severity items (multi-slot re-check after editing a filled slot,
  `multiple_choice multi:true` deselect-by-re-tap, a genuine fetch-rejection failure,
  `ids.test.ts`) are left as test-coverage debt -- not fixed, per the finding's own
  "log the rest ... if time-constrained" framing; none of them correspond to a known or
  suspected bug, unlike #1-#3.

- **#8 (low) fixed**: removed `NumberInputWidget.tsx`'s dead `SLOT_MARKER` re-export and its
  misleading comment (confirmed via `grep` that nothing else in `frontend/src` imported it).

**Verification** (same `/tmp` fast-sync workflow as the original implementation --
`rsync --exclude=node_modules --exclude=dist --exclude=dev-dist` to a fresh
`/tmp/hoctap-fe-review/frontend` plus `_bmad-output/planning-artifacts/`, then a fresh
`npm ci`):
- `npx tsc -b` -- clean, 0 errors.
- `npx eslint .` -- clean, 0 errors/warnings.
- `npx vitest run` (full suite) -- all passing except the same 3 pre-existing
  `ExtractionPage.test.tsx` failures already documented as unrelated/pre-existing in the
  original Implementation Notes entry (nothing this story or this fix pass touches).
- No real network or TTS calls added: every new/changed test uses `mockApi()` and either the
  existing jsdom-stubbed `HTMLMediaElement.play()` no-op or an explicit
  `vi.mock('../audio/speech', ...)`, matching the codebase's established pattern
  (`Home.test.tsx`).

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `ProblemPlayer.tsx`'s HintBubble render condition includes `phase === 'wrong-solution'`, so on a SECOND wrong attempt the HintBubble (with the stale first-attempt hint text) renders stacked above the SolutionPanel at the same time -- the frozen Intent only calls for the Solution panel at that point | high | confirmed by 1 reviewer via direct code read -> patch: HintBubble should render only when `phase === 'wrong-hint'`, never during `wrong-solution` |
| 2 | `count_image`'s tap-to-dot counting aid is not reset between attempts on the SAME Part -- only Part-level `key` remount clears it (on a Part change), never on a retry after a wrong attempt. The frozen Boundaries text explicitly requires "reset per attempt." A child who places dots, submits wrong, and retries the same Part sees stale dots accumulate | high | confirmed independently by 2 reviewers -> patch: reset `CountImageWidget`'s dot state whenever a new attempt cycle begins on the same Part (e.g. key it on an attempt-counter/phase transition back to answering, not just on Part change) |
| 3 | Rapid double-tap on the check button has no synchronous guard: `disabled` is derived from React state (`phase`), which can lag a render behind two back-to-back taps, allowing `handleCheck` to fire twice before the first `setPhase('submitting')` takes visible effect. Each tap calls `ids.ts` for a FRESH UUIDv7, so backend idempotency (same-id dedup) does NOT protect against this -- two distinct `attempt` events could be posted for one child action, double-counting into the Retry Queue or grading history | high | confirmed by 1 reviewer (no synchronous guard found), real because ids.ts generates a new id per call so backend dedup can't catch it -> patch: add a synchronous ref-based guard (e.g. a `useRef<boolean>` flag checked-and-set before the state update) so a second tap within the same event-loop tick before re-render is a definite no-op; add a test firing the check button twice back-to-back and asserting exactly one `attempt` event was posted |
| 4 | `NumberPad` has no `disabled` prop and is never disabled while a submit is in flight or feedback is settling -- digit/backspace handlers do check a disabled flag and no-op, so this isn't a double-submit vector, but the number keys remain visually tappable with no feedback that input is inert during `submitting`/`wrong-shake`/`correct` phases | medium | confirmed by 1 reviewer -> patch: add an optional `disabled` prop to `NumberPad` (additive, per the spec's own "add a prop, don't rewrite" rule) and pass it from `ProblemPlayer` during non-answering phases |
| 5 | `ChoiceChip`'s new `variant?: 'correct'\|'wrong'` prop has zero dedicated test coverage -- no `ChoiceChip.test.tsx` exists at all (Story 2.1 never added one), and `ProblemPlayer.test.tsx`'s `compare`/`multiple_choice` tests never assert the graded chip's visual class/state, only pre-grading tap behavior | medium | confirmed by 1 reviewer, more severe than initially scoped (not even indirectly tested) -> patch: add `frontend/src/components/ChoiceChip/ChoiceChip.test.tsx` covering the new `variant` prop, and extend at least one `ProblemPlayer.test.tsx` case to assert the graded chip's class/state after a correct/wrong compare or multiple_choice attempt |
| 6 | No regression test pins the displayed praise-banner text to the actually-spoken phrase (the exact class of bug already fixed once this story) -- existing correct-attempt tests never assert which praise line renders or that it matches the `speak()` call | medium | confirmed by 1 reviewer, a fix with no regression test can silently regress -> patch: add a test asserting the rendered banner text matches the `speak()`-invoked phrase key for at least one correct attempt |
| 7 | Several genuine coverage gaps, all confirmed low-risk by code inspection but unverified by any test: a multi-Part Problem's Part-to-Part advance (only single-Part Problems are tested); a multi-slot Part's completeness re-check after editing one already-filled slot; `multiple_choice multi:true` deselect-by-re-tapping the same option; a genuine network/fetch-rejection failure (only an HTTP 502 status is tested, not "no response at all"); 2+ Problems within one chunk (only single-Problem chunks are tested); `ids.ts`'s UUIDv7 generator has no dedicated focused test (only one incidental sample check inside an unrelated test) | low | -> patch: add the cheapest 3-4 as time allows (multi-Part advance and 2+-Problems-per-chunk are the highest-value of this group since they're core navigation correctness); log the rest as test-coverage debt in deferred-work.md if time-constrained |
| 8 | Dead/misleading `SLOT_MARKER` re-export from `NumberInputWidget.tsx` with a comment claiming `ProblemPlayer` reuses it for the completeness check -- it never does (`isComplete()` uses `part.slots` directly) | low | harmless but a stale comment -> patch: remove the unused re-export and its comment, or actually wire it up if there's a reason to prefer it -- implementer's call, this is cosmetic |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed all 3 high-severity fixes directly in source (HintBubble narrowed to `phase === 'wrong-hint'` only; count_image dots reset via an `attemptSeq`-keyed remount on retry; a synchronous `submittingRef` guard against double-tap). `tsc -b` and `eslint` both clean. Full vitest run showed severe timeout flakiness (8-18 unrelated files failing) traced to shared-machine memory pressure (1.2GB free at the time, unrelated concurrent sessions busy) -- confirmed via isolated reruns that every failure was pre-existing/unrelated-file flakiness, not a regression from this story. All of Story 2.6's own test files (ProblemPlayer, SessionPlayer, ChoiceChip, NumberPad, widgets/) pass cleanly in isolation: 39/40 on first targeted run (1 flaky timeout, confirmed passing on rerun), so effectively 40/40. Story marked done.

</frozen-after-approval>
