---
title: 'Story 2.7: The other grade-1 widgets'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:43b1529e2bd8548ae1bb134581fd6081fd7ce6c0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.6 builds the player and its widget-per-type switcher for the 5 "basic" Part
types, but 7 more Part types (`order`, `grid_fill`, `match`, `image_select`, `dot_draw`,
`connect_dots`, `spot_difference`) exist in every book's real content and already have working
server graders (Story 2.5), so a Problem using any of them currently only shows the "chưa hỗ trợ"
placeholder Story 2.6 leaves for unsupported types.

**Approach:** Add one widget per remaining type to Story 2.6's widget-switcher (exact extension
point TBC — re-confirm the actual file/component structure Story 2.6 lands with before writing any
code; this spec assumes a switcher exists that dispatches by Part `type`, matching Story 2.6's own
Code Map intent, but the precise file(s) may differ from what's guessed here). Each widget
implements its own UX-DR9 interaction — most are drag-based with an explicit tap-alternative (never
drag-only, per UX-DR9's "dragging always has a tap alternative") — and reuses Story 2.1's
components wherever the shape fits, adding new small presentational pieces only where none of the
existing 10 components cover the interaction (e.g. no existing component draws a line between two
tapped items for `match`, or places a dot on a tapped image region for `dot_draw`).

## Boundaries & Constraints

**Always:**
- **Dependency on Story 2.6**: re-read Story 2.6's actual landed `SessionPlayer.tsx`/widget
  switcher structure before writing any code here — this spec's Code Map is a placeholder pending
  that. Do not assume file names/locations below are final.
- **Per-type interaction** (UX-DR9's exact wording, EXPERIENCE.md's Problem Type table):
  - `order`: drag number tiles into slots (snap into place); tap-a-tile-then-a-slot as the
    non-drag alternative — REQUIRED, not optional, for any implementation.
  - `grid_fill`: tap a cell, then the `NumberPad` (same interaction shape as `number_input`,
    just laid out as a grid); cells already filled in the book (`GridCell` marked given) are
    locked (visually grey, not tappable).
  - `match`: tap a left item, then a right item, draws a line between them; tapping an existing
    line removes it (un-pairs).
  - `image_select`: tap one region-hotspot on the image (or several, if `multi: true`); selected,
    not submitted until ✔ — same "select now, submit on Check" pattern as `multiple_choice`.
  - `dot_draw`: tap inside the box to add a dot; tap an existing dot to remove it; a visible
    counter shows how many dots are placed (against the box's own `given` count already present
    before any child interaction).
  - `connect_dots`: tap numbered dots in order; a line follows the taps; tapping the WRONG next
    dot makes it wiggle and does **not** count as an Attempt (no `attempt` event posted) — only
    tapping ✔ once the full sequence is drawn submits an Attempt (matches Story 2.7's own explicit
    acceptance criterion, distinct from every other type's "submit on ✔ regardless").
  - `spot_difference`: tap a difference on the right-hand image (left is the static reference); a
    correct spot gets a ring, a counter shows "n/count"; wrong taps don't get a permanent ring
    (implementer's call on wrong-tap feedback, e.g. a brief flash) but don't count as a submitted
    Attempt either — same submit-only-on-✔ pattern as `connect_dots`.
- **✔ Kiểm tra gating**: enabled only when the current Part's interaction is "complete" by its own
  type's definition (every `order` slot filled, every `grid_fill` empty cell filled, every `match`
  left item paired, at least one `image_select` region selected, `connect_dots`'s full sequence
  drawn, `spot_difference`'s full `count` of differences found) — reuse the same client-side
  completeness-check pattern Story 2.6 established for the basic 5 types.
- **Submit shape**: match Story 2.5's already-fixed, already-documented submitted-value shapes
  exactly (see `learning/graders.py`'s own module docstring, copied here for convenience):
  `order` → `{"order": list[str]}`; `match` → `{"pairs": list[[left_key, right_key]]}`;
  `image_select`/`multiple_choice`-shape → `{"selected": list[str]}`; `grid_fill`/`dot_draw` →
  `list[{"key": str, "value": str}]` (same keyed-numeric shape as `number_input`); `connect_dots` →
  `{"sequence": list[int]}`; `spot_difference` → `{"region_keys": list[str]}`.
- **Correct/wrong feedback**: reuse Story 2.6's exact feedback sequencing (green/chime/praise on
  correct; shake/orange/boop then 400ms-delayed Hint on first wrong; Solution panel on second
  wrong) — this story only adds new ways to REACH a submittable state, not a new feedback model.
- **Accessibility**: every new interactive element (a drag tile, a match line's tap target, a dot,
  a region hotspot) keeps the ≥64px touch target rule and is operable by tap alone (drag is always
  optional per UX-DR9) — no interaction in this story may be drag-only.

**Never:**
- No backend changes — Story 2.5 already built every grader this story's widgets submit to.
- No changes to Story 2.6's basic-5-type widgets beyond whatever shared plumbing (the switcher
  itself, the submit/feedback hooks) naturally needs a new `case` added.
- `spot_difference`'s wrong-tap feedback and `connect_dots`'s wiggle are purely client-side; neither
  posts an event until the Part is actually complete and ✔ is tapped.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| order, drag | drag a tile into a slot | tile snaps, ✔ enables once all slots filled | N/A |
| order, tap alternative | tap tile then tap slot | same result as drag, no pointer drag events needed | N/A |
| grid_fill, locked cell | tap a given/locked cell | no-op, cell stays locked | N/A |
| match, tap pair then remove | tap left+right (line drawn), tap the line | line removed, pair cleared | N/A |
| image_select, multi | `multi: true`, tap 2 regions | both selected, ✔ enabled | N/A |
| dot_draw, add/remove | tap box (dot added), tap dot (removed) | counter updates each time | N/A |
| connect_dots, wrong next dot | tap a non-sequential dot | dot wiggles, no Attempt posted | N/A |
| connect_dots, full correct sequence then ✔ | all dots tapped in order | one Attempt posted, graded correct | N/A |
| spot_difference, correct spot | tap a real difference region | ring shown, counter increments, no Attempt yet | N/A |
| spot_difference, all found then ✔ | count reached | one Attempt posted with all region_keys | N/A |
| Unsupported-type placeholder removed | any of these 7 types now render their real widget | "chưa hỗ trợ" no longer shown for them | N/A |

## Code Map

**Confirmed against Story 2.6's actual landed structure** (commit ed8fca3): the switcher lives in
`frontend/src/pages/ProblemPlayer.tsx`'s `PartPlayer.widget()` (a function returning the right
widget component by `part.type`, currently a `switch`/lookup over the 5 basic types plus
`UnsupportedWidget` as the fallback); each widget is its own file under
`frontend/src/components/widgets/` (`NumberInputWidget.tsx`, `CompareWidget.tsx`,
`MultipleChoiceWidget.tsx`, `NumberTreeWidget.tsx`, `CountImageWidget.tsx`, `UnsupportedWidget.tsx`,
plus a shared `types.ts` and `widgets.css`) — this story adds 7 more sibling files to that same
folder and 7 more entries to the `PartPlayer.widget()` dispatch, following that exact pattern.
`PartPlayer` already owns submit/feedback/phase state generically (not per-widget-type), including
the `attemptSeq`-keyed remount-on-retry pattern (Story 2.6's own fix for `count_image`'s dots) —
reuse this same mechanism for any new widget with per-attempt local state (`order`'s tile
positions, `dot_draw`'s dots, `connect_dots`'s drawn sequence, `spot_difference`'s found rings).

- New widget components, one per type, composing Story 2.1's pieces plus small new ones where
  needed (a line-drawing piece for `match`/`connect_dots`, a drag-tile piece for `order`, a
  hotspot-image piece for `image_select`/`spot_difference`, a dot-canvas piece for `dot_draw`).
- `frontend/src/pages/ProblemPlayer.tsx`'s `PartPlayer.widget()` gains 7 more entries; its
  `isComplete()`/submit-payload-building logic (currently per-type, inline) grows 7 more branches
  matching the exact submitted-value shapes documented in `learning/graders.py`'s module docstring
  (copied into this spec's Boundaries above).
- `connect_dots`/`spot_difference`'s "no Attempt until ✔" behavior needs `PartPlayer`'s existing
  submit trigger to stay gated on an explicit ✔ tap for these types too (already true for all 5
  basic types — confirm this isn't accidentally different for these two, since they're the first
  types where the interaction itself has a notion of "wrong" that does NOT trigger a submit).
- `_bmad-output/implementation-artifacts/deferred-work.md` — note `expression_input` (in
  EXPERIENCE.md's interaction table but not in this story's or any other Epic 2 story's acceptance
  criteria) as out of scope for all of Epic 2, if it isn't already covered elsewhere.

## Tasks & Acceptance

- [ ] Re-confirm Story 2.6's actual widget-switcher structure; adjust this Code Map before coding.
- [ ] 7 new widgets, each with its UX-DR9 interaction, each with a working tap-alternative where a
      drag interaction exists.
- [ ] `connect_dots`/`spot_difference`'s submit-only-on-full-completion-and-✔ behavior (no attempt
      posted for an intermediate wrong tap).
- [ ] ✔ gating per type's own completeness rule.
- [ ] All new tests pass; `tsc -b`/`eslint`/full frontend suite clean; no regression in Story
      2.6's basic-5-type tests.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-29

**Code Map re-confirmed.** Story 2.6 landed exactly as this spec's Code Map assumed
(commit `ed8fca3`): `PartPlayer.widget()` in `frontend/src/pages/ProblemPlayer.tsx` is a
`switch` over `part.type`, one sibling file per type under
`frontend/src/components/widgets/`, `UnsupportedWidget` as the fallback. Added 7 sibling
widget files and 7 `case`s, following the existing files' exact prop/styling conventions.

**New widget files** (`frontend/src/components/widgets/`): `OrderWidget.tsx`,
`GridFillWidget.tsx`, `MatchWidget.tsx`, `ImageSelectWidget.tsx`, `DotDrawWidget.tsx`,
`ConnectDotsWidget.tsx`, `SpotDifferenceWidget.tsx`. No separate shared presentational
pieces were extracted into their own files (unlike the Code Map's suggestion of "a
line-drawing piece for `match`/`connect_dots`, a hotspot-image piece for
`image_select`/`spot_difference`, a dot-canvas piece for `dot_draw`") -- each widget's line-
drawing / hotspot-image / dot-canvas is a few lines of inline SVG/`<div>`s, and the two
line-drawing cases turned out to need genuinely different strategies (`match` measures live
DOM rects via `useLayoutEffect`, since its items are plain list rows with no inherent
coordinates; `connect_dots` uses the dots' own normalised 0-1 image coordinates directly, no
measurement needed) -- factoring them into one shared component would have added an
abstraction layer without real reuse. `image_select` and `spot_difference` also ended up
different enough (bbox-hotspot-over-one-image vs free-tap-over-two-images with no hotspot
data at all, see the Spec Change Log entry below) that a shared "hotspot-image" piece wasn't
a clean fit either. This is a deviation from the Code Map's suggestion, made for concrete
reuse-vs-abstraction reasons above, not an oversight.

**`ProblemPlayer.tsx` (`PartPlayer`) plumbing added, shared by the new widgets:**
- Lifted state: `pairs` (`match`'s left→right map), `pickedItem` (the tap-alternative's
  "picked tile/left-item", shared by `order` and `match`), `sequence` (`connect_dots`'s
  ordered taps), `foundRegions` (`spot_difference`'s found spots). All FOUR persist across a
  retry exactly like `values`/`selected` already did for the basic 5 -- unlike
  `count_image`'s dots, these ARE the graded answer, not a non-graded aid, so (per this
  story's own reasoning about `dot_draw` below) there is no `attemptSeq` remount for any of
  them.
- New handlers: `handlePickItem`/`handlePlaceItem` (`order`'s drag-or-tap placement, and
  `match`'s "pick a left item" step), `handlePairRight`/`handleRemovePair` (`match`),
  `handleSetValue` (`dot_draw`'s direct keyed-value set, bypassing `NumberPad`),
  `handleTapDot`/`handleFoundRegion` -- both return a `boolean` ("was this tap accepted")
  so the widget can render its own purely-local wrong/wiggle/flash feedback without ANY
  `PartPlayer` state changing on a wrong tap (see the ✔-gating note below).
- `handleToggleOption` (`multiple_choice`'s existing handler) generalised to also cover
  `image_select` -- both share the exact same "select now, submit on ✔" shape and the same
  `multi: boolean` field, so `image_select` needed zero new plumbing beyond the type guard.
- `slotKeysFor()`/`isComplete()`/`buildValue()` grew branches for all 7 types, matching the
  submitted-value shapes from `learning/graders.py`'s docstring exactly (verified against
  the actual grader functions, not just the docstring prose -- see `grade_spot_difference()`
  discussion below).
- `grid_fill` joined `NUMERIC_TYPES` (shows the shared `NumberPad`, exactly like
  `number_input` -- per the spec, "same interaction shape, just laid out as a grid").
  `order`/`match`/`image_select`/`dot_draw`/`connect_dots`/`spot_difference` do NOT show the
  `NumberPad` (none of them take typed digits).

**`order`'s tap-alternative** (REQUIRED per Boundaries & Constraints): tap a tray tile
(`onPickItem`) to pick it up, then tap a position slot (`onPlaceItem`) to place it there --
this also clears the item from any OTHER slot it was previously in first, since a position
slot holds a permutation. Tapping an already-FILLED slot with nothing picked instead picks
that slot's tile back up (a natural "undo", also exercised by a test). Drag-and-drop is
implemented alongside via plain HTML5 `draggable`/`onDragStart`/`onDragOver`/`onDrop`,
calling the SAME `onPlaceItem(slotKey, itemKey)` with an explicit `itemKey` instead of
relying on `pickedItem` -- so both paths share one code path in `PartPlayer`, and neither is
a fallback shim for the other. (Drag-and-drop itself isn't exercised by the automated tests
-- jsdom's `DataTransfer` support is minimal/unreliable across the ecosystem for this -- but
the tap-alternative, which is the REQUIRED path, is fully tested.)

**`match`'s tap-alternative** (its ONLY interaction, per the spec -- there's no drag
variant specified for `match`): tap a left item (`onPickItem`) then a right item
(`onPairRight`) draws a line (an SVG `<line>` between the two buttons' measured centres, via
`useLayoutEffect` + `getBoundingClientRect()`). "Tapping an existing line removes it" is
implemented as tapping EITHER endpoint of an already-paired item (`onRemovePair`) -- there is
no separate hit-target for the line itself, since the line is a thin, precisely-positioned
SVG stroke that would fail the ≥64px touch-target rule on its own; tapping either of its two
(already ≥64px) endpoints is the practical equivalent and is what the automated tests
exercise.

**`connect_dots`/`spot_difference`'s "no Attempt until ✔" gating**: confirmed this needed NO
change to `PartPlayer`'s submit trigger -- `handleCheck()` (the only place that ever calls
`postEvent.mutateAsync()`) is already, and remains, reachable ONLY from the ✔ button's
`onClick`. What's new for these two types is that individual taps can be locally "wrong"
(an out-of-sequence dot, a duplicate/already-found spot) -- `handleTapDot()`/
`handleFoundRegion()` reject such taps and return `false` BEFORE any `PartPlayer` state
changes (not even `retryIfSettled()` runs), so a wrong tap is a pure no-op from
`PartPlayer`'s point of view; `ConnectDotsWidget`/`SpotDifferenceWidget` render the
wiggle/flash entirely with their own local `useState`, never touching lifted state. This
also means a wrong tap can never itself trigger a submit, satisfying the acceptance
criterion by construction rather than by a special-cased check.

**`dot_draw` deviation**: the frozen ✔-gating list in Boundaries & Constraints enumerates 6
of the 7 types explicitly (`order`, `grid_fill`, `match`, `image_select`, `connect_dots`,
`spot_difference`) but omits `dot_draw`. Treated it the same as the OTHER multi-slot keyed
types (`number_input`/`grid_fill`/`count_image`, all sharing the generic "every slot's
`values` entry is non-empty" `isComplete()` fallback) -- i.e. every box needs at least one
add/remove tap before ✔ enables, even if the box's `given` count alone would already be a
valid answer. `dot_draw`'s dot positions (needed only for rendering/undo, not for grading --
only the resulting COUNT is submitted) are local `useState` inside `DotDrawWidget`, but
UNLIKE `count_image`'s dots there is no `attemptSeq` remount: since the derived count IS the
graded answer (lifted into `values` via the new `onSetValue`), clearing the visual dots on a
retry while `values` kept the old count would desync the two, so both persist together
across a retry, exactly like every other keyed type's `values`.

**Verification**: `npx tsc -b`, `npx eslint .`, and the full `npx vitest run` frontend suite
all clean (using the fast rsync-to-`/tmp` + fresh `npm ci` workaround for this machine's slow
`/mnt/c` disk). 220/220 tests pass excluding one pre-existing, unrelated failure
(`src/pages/ExtractionPage.test.tsx`, 3 failing) confirmed to fail identically on the
`dev` baseline (commit `ed8fca3`, before any Story 2.7 change) run in the same isolated
copy -- a pre-existing issue, not a regression from this story. `ProblemPlayer.test.tsx`
alone: 35/35 passing (28 pre-existing Story 2.6 tests + 1 updated + a full new describe
block per Story 2.7 type covering ✔-gating, the tap-alternative, the exact submitted-value
shape, and -- for `connect_dots`/`spot_difference` -- that a wrong/duplicate tap posts no
event at all).

### 2026-09-29: Review triage fixes

- **#1 (medium, fixed)**: `DotDrawWidget.tsx`'s `addDot` had no proximity/dedup check --
  added the same `BUCKET_PCT`-quantization pattern `SpotDifferenceWidget.tsx` already uses
  (`bucketKey(x, y)`, `BUCKET_PCT = 12`), but kept purely local to `DotDrawWidget` (unlike
  `spot_difference`'s, this dedup never touches lifted `PartPlayer` state -- `dot_draw`'s
  dots are local render state to begin with). A tap whose bucket matches an already-placed
  dot's bucket now REMOVES that dot instead of adding a new, overlapping one, so a real
  double-tap even a few px off the previous dot's center no longer silently inflates the
  submitted count. Added a regression test (`ProblemPlayer.test.tsx`, `dot_draw` describe:
  "a tap near an existing dot (not exactly on it) removes it instead of adding a second,
  overlapping dot") and a `getBoundingClientRect` mock for that describe block (jsdom's
  default all-zero rect made every tap's normalised (x,y) resolve to the same `Infinity`,
  same issue `spot_difference`'s test already worked around) -- also had to widen the
  existing "posts [{key, value}] on ✔" test's two tap coordinates so they land in
  DIFFERENT buckets (10,10 and 20,20 were, under the fixed test rect, the same bucket and
  would have collapsed to a dedup-remove instead of two adds; changed the second tap to
  200,200, matching the fixture `spot_difference`'s own test already uses for the same
  reason).
- **#2 (low, fixed)**: strengthened `spot_difference`'s "all-found-then-✔" payload
  assertion from `region_keys` `toHaveLength(2)` to a full `toEqual({ part_key, value:
  { region_keys: [...] } })`, matching every other type's payload test. Computed the exact
  expected keys from the fixture's fixed 300×300 test rect and the two fireEvent tap
  coordinates already in that test (`d_0_0`, `d_5_5`).
- **#3 (low, fixed)**: added a short entry to the Spec Change Log below (duplicating the
  Implementation Notes' "`dot_draw` deviation" reasoning) so a reader scanning only the
  Spec Change Log for "how was a spec ambiguity resolved" doesn't miss it.
- **#4 (low, top 2 done)**: added `match`'s "tapping a second left item before any right
  tap switches the pick, not corrupting state" and `connect_dots`'s "a backward tap after
  partial progress (1→2→1) is rejected like a genuinely wrong dot" to
  `ProblemPlayer.test.tsx`. Skipped, logged as test-coverage debt per the triage's own
  time-box: `order` with `direction: "custom"`, and the "unsupported placeholder removed"
  claim for the 6 Story-2.7 types other than the one the swapped-fixture test already
  covers.
- **Verification**: rsynced source (excl. `node_modules`/`dist`/`dev-dist`) to `/tmp`,
  fresh `npm ci` there, then `npx vitest run` (full suite: 222/225 passing, same 3
  pre-existing `ExtractionPage.test.tsx` failures noted in the entry above, unrelated to
  this story), `npx vitest run src/pages/ProblemPlayer.test.tsx` (38/38, up from 35 --
  the 3 new tests above), `npx tsc -b` clean, `npx eslint .` clean.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

### 2026-09-29: `spot_difference`'s child View has no hotspot data

`content/schema.py`'s `SpotDifferenceView` (the child-facing bundle shape) carries only
`image_left`/`image_right`/`count` -- unlike `image_select`'s `ImageSelectView`, which does
expose `regions: list[Region]` (key + bbox) for client-side hit-testing, `SpotDifferenceView`
exposes NO region/bbox data at all. The actual difference locations live only in
`SpotDifferencePart.answer.regions` (`content/schema.py`), which is never sent to the child
(by design -- an `AnswerBearing` field). `learning/graders.py`'s `grade_spot_difference()`
does an exact `region_key` SET comparison against that server-only answer.

This means the child's tapped screen position can never be translated into a `region_key`
that matches the server's real answer keys -- there is no shared vocabulary between what the
client can compute from a tap (a screen coordinate) and what the grader compares against
(author-assigned keys tied to author-drawn bboxes the client never receives). Given this
story's Never-list ("no backend changes... `content.schema` still stands"), this can't be
fixed from the frontend alone.

**What this story ships anyway**: the full described UX -- tap the right image, a ring per
found spot, an "n/count" counter, wrong/duplicate taps get a transient flash (not a
permanent ring) and post no Attempt, ✔ enables at `count` and submits
`{"region_keys": [...]}` on tap -- using a CLIENT-DERIVED region key (tapped point quantised
into a coarse percentage-grid bucket, so nearby re-taps count as the same spot rather than
inflating the count). This satisfies every UI/interaction acceptance criterion in the I/O
matrix and Boundaries & Constraints, but the submitted `region_keys` will not match the
server's real answer keys in production, so a real `spot_difference` Part will currently
always grade incorrect no matter what the child taps. **Follow-up needed**: either
`SpotDifferenceView` needs to start exposing region/bbox data to the child (mirroring
`image_select`'s `Region` shape -- which would not leak anything the child can't already see
by eye, since spot-the-difference's whole premise is that the difference is visible), or the
grader needs a geometry-tolerant comparison against a coordinate the client CAN produce
faithfully. Recorded here rather than in `deferred-work.md` since it's specific to this
story's own Part type, not an out-of-scope type like `expression_input`.

### 2026-09-29: `dot_draw`'s ✔-gating wasn't in the frozen Boundaries list

Boundaries & Constraints' ✔-gating list enumerates 6 of the 7 types explicitly (`order`,
`grid_fill`, `match`, `image_select`, `connect_dots`, `spot_difference`) but omits `dot_draw`.
Resolved by treating it like the other multi-slot keyed types (`number_input`/`grid_fill`/
`count_image`): every box needs at least one add/remove tap before ✔ enables, via the
generic "every slot's `values` entry is non-empty" `isComplete()` fallback, even though the
box's own `given` count alone would already be a valid answer. Full reasoning is in the
Implementation Notes' "`dot_draw` deviation" entry; duplicated here per review finding #3 so
a reader scanning only this section doesn't miss that a spec ambiguity was resolved.

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `DotDrawWidget`'s `addDot` has no proximity/dedup check (unlike `SpotDifferenceWidget`'s `BUCKET_PCT` quantization) -- a real double-tap even one pixel off the previous dot's center silently adds a second overlapping, visually-indistinguishable dot, inflating the submitted count above what the child intended | medium | confirmed by 1 reviewer; this is a real production UX/data-quality risk (jsdom can't even simulate the exact scenario since RTL's fireEvent dispatches directly on an element rather than doing coordinate-based hit-testing) -> patch: add the same proximity-bucket dedup `SpotDifferenceWidget` already uses, so a tap near an existing dot removes it instead of adding a new one |
| 2 | `spot_difference`'s "ring shown" cosmetic claim and the "all-found-then-✔" payload check are both weaker than the I/O matrix's literal claim: no test queries for the ring CSS class, and the payload assertion only checks `region_keys` length, not full key equality (unlike every other type, which uses `toEqual` on the full payload) | low | -> patch: add the missing `toEqual` full-payload assertion for spot_difference's all-found case; the ring-CSS assertion is optional given this type's known separate backend-gap limitation, skip if time-constrained |
| 3 | `dot_draw`'s ✔-gating judgment call (verified correct, not under-gated) is documented only in Implementation Notes, not the Spec Change Log, even though it's a resolution of a genuine spec ambiguity (the type wasn't in the frozen gating list) | low | -> patch: move or duplicate a short note into the Spec Change Log so a future reader scanning only that section doesn't miss it |
| 4 | Several "verified correct by code reading, not exercised by any test" scenarios: `match` tapping a second left item before any right tap; `connect_dots` a backward tap after partial progress (dot 1→2→1); `order` with `direction: "custom"`; the "unsupported placeholder removed" claim for the other 6 types (only directly asserted for the type used in the swapped fixture) | low | all confirmed non-bugs by 2 reviewers via code trace -> patch: add the cheapest 2-3 as time allows (match's left-switch and connect_dots' backward-tap are highest value since they're the most plausible real child behaviors); log the rest as test-coverage debt if time-constrained |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed the dot_draw proximity-dedup fix (`BUCKET_PCT`/`bucketKey()`, mirroring `SpotDifferenceWidget`) directly in source. `tsc -b`/`eslint` clean. Full frontend suite: 228/231 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story). No critical/high-severity findings emerged from the independent 3-reviewer pass -- the work was sound overall; the one real finding (dot_draw stray dots) and several minor coverage gaps are now fixed. Note: `spot_difference` remains non-functional for real grading due to a backend content-schema gap (no hit-test region data exposed to the child view) that is out of this story's scope -- logged in deferred-work.md for a future story. Story marked done.

</frozen-after-approval>
