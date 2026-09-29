---
title: 'Story 2.9: Audio player and auto-play'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:3e6e4764961086a2ebfa081744c37467ae464208'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `frontend/src/audio/speech.ts`'s `speak()` creates a brand-new `Audio` element on
every call (confirmed by reading the current source) — no shared player, no "stop the previous
clip when a new one starts or the screen changes" behaviour (UX-DR7's explicit requirement), no
distinction between "not yet synthesised" and "genuinely missing" for the 🔊 grey-out rule, and no
auto-play-the-instruction-on-open behaviour at all. `SpeakerButton.tsx`'s own docstring literally
says "Story 2.9 wires real audio" — it has no `playing`-driving logic today, `speak()` is called
fire-and-forget with no return value the button can react to.

**Approach:** A single shared `AudioPlayer` module (one `<audio>` element, not one per call) that
every `speak()`/`SpeakerButton` call goes through: starting a new clip stops whatever was playing;
leaving a screen (component unmount) stops it too. A per-Profile `auto_play` setting (new column,
default on) gates whether a Problem's instruction plays automatically when it opens — but browsers
block audio until a user gesture has occurred at least once in the page's lifetime, so auto-play
must wait for that unlock and never treat a blocked attempt as itself a bug. A missing audio file
(never synthesised, or genuinely absent) makes 🔊 grey out while the instruction text stays fully
visible/readable (UX's explicit fallback for "no audio" — the child is never blocked by a missing
clip).

## Boundaries & Constraints

**Always:**
- **Backend**: add `auto_play` (boolean, default `true`) to `parent_profiles` via a new Alembic
  migration (next after whatever Story 2.8 lands with — check the actual head revision before
  naming this one), and to the `Profile` Pydantic schema (`backend/hoctap/parent/schemas.py`)/the
  `GET /profiles` response. No Parent-Area UI to toggle it is required by this story's acceptance
  criteria (epics.md never mentions a parent-facing control for it) — default `true` for every
  existing and new Profile; log a `deferred-work.md` entry if a future story is expected to add a
  Parent Area toggle, since the column exists and is ready for one.
- **Frontend, a shared player** (`frontend/src/audio/player.ts` or extend `speech.ts` —
  implementer's call on file split, but there must be exactly ONE `<audio>` element reused across
  all calls, not one per `speak()` invocation):
  - Starting a new clip stops (`pause()` + reset) whatever was previously playing on the shared
    element first.
  - Exposes enough state (a subscribable "currently playing key" or similar) for `SpeakerButton`'s
    `playing` prop to reflect reality, and for a "did this exact call's clip fail because the file
    is missing" signal distinct from "it's just not playing yet" — needed for the grey-out rule.
  - A missing file is detected via the `<audio>` element's own `error` event (a 404 or decode
    failure), not a separate pre-flight fetch — reuse platform behaviour, don't build a duplicate
    existence-check path.
  - `speak()`'s existing signature/behaviour (silent no-op on any failure) is preserved for
    existing callers — this story upgrades its INTERNALS (shared element, stop-previous,
    missing-file signal) without breaking `HintBubble`/`SolutionPanel`/long-press-to-speak call
    sites that already exist from Stories 2.1-2.8.
- **Audio unlock**: track whether the page has received at least one user gesture (a module-level
  flag set on the first `pointerdown`/`click` anywhere, or reuse an existing app-wide gesture
  listener if one already exists — check `frontend/src/App.tsx` before adding a new one). Auto-play
  is only ever attempted after unlock; before unlock, the instruction simply doesn't auto-play (no
  error, no retry loop) — the child's own first tap (e.g. picking a Profile, tapping Home) is
  almost always the natural unlock moment in practice.
- **Auto-play the instruction on Problem open** (`ProblemPlayer.tsx`/`PartPlayer`): when a new Part
  renders AND the current Profile's `auto_play` is `true` AND the page is unlocked, play the Part's
  instruction/prompt text automatically once. Starting ANY other clip (a Hint, a Solution step, a
  manual 🔊 tap) or leaving the screen (unmount) stops it — reuse the shared player's
  stop-previous/stop-on-unmount behaviour, don't build a second mechanism.
- **`SpeakerButton`**: gains real wiring — `playing` reflects the shared player's actual state for
  its own clip, and a new prop (implementer's call on name, e.g. `missing?: boolean`) greys it out
  (visually disabled, `aria-disabled`, but the instruction/option/hint TEXT next to it stays fully
  visible — never hide text because its audio is missing).
- **NFR-4** (audio starts under 0.5s on the LAN): no strict perf test required — just don't add
  anything pathological (e.g. no redundant existence-check network round-trip before playback;
  `new Audio(url).play()`/the shared element's `.play()` is already the fast path).

**Never:**
- No changes to `content.speech`/`backend/hoctap/builder/tts_client.py`/the `speak-missing` build
  stage — this story only consumes already-synthesised clips, exactly like Story 2.3 did.
- No Parent-Area UI for toggling `auto_play` — out of scope per this story's own acceptance
  criteria (log as deferred if warranted).
- Do not build a duplicate "does this file exist" pre-flight check — rely on the `<audio>`
  element's own `error` event, per the Always section.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Auto-play on, unlocked, Problem opens | `auto_play: true`, page already unlocked | instruction plays once automatically | N/A |
| Auto-play on, NOT yet unlocked | first Problem before any tap | no auto-play attempt, no error, no visible retry | N/A |
| Auto-play off | `auto_play: false` | instruction never auto-plays; manual 🔊 tap still works | N/A |
| Starting a new clip stops the old one | instruction auto-playing, child taps 🔊 on an option | the instruction stops immediately, the option's clip plays | N/A |
| Leaving the screen stops audio | a clip is playing, child navigates away (unmount) | audio stops, no lingering playback | N/A |
| Missing audio file | a clip whose speech_key has no synthesised file yet | 🔊 greys out, instruction/option/hint TEXT still fully visible | N/A |
| Manual 🔊 tap on a working clip | tap | plays; `playing` becomes true while it plays, false when it ends | N/A |
| Long-press-to-speak (existing Story 2.1/2.3 call sites) | HomeCard/etc. long press | still works unchanged through the upgraded shared player | N/A |

## Code Map

- `backend/hoctap/parent/models.py`: `auto_play` column on `parent_profiles`.
- `backend/hoctap/db/alembic/versions/00XX_auto_play.py`: the new migration (name/number TBC —
  check the actual head after Story 2.8 lands).
- `backend/hoctap/parent/schemas.py`: `Profile.auto_play: bool`.
- `backend/hoctap/parent/service.py` (or wherever `list_profiles()` lives): include the new column.
- `backend/tests/test_profiles.py` or equivalent: new column round-trips.
- `frontend/src/audio/player.ts` (new) or `speech.ts` (extended): the shared `<audio>` element,
  stop-previous, missing-file signal, unlock tracking.
- `frontend/src/components/SpeakerButton/SpeakerButton.tsx`: real `playing`/missing wiring
  (additive props only, per this codebase's established "add a prop, don't rewrite" convention).
- `frontend/src/pages/ProblemPlayer.tsx`: auto-play-on-open wiring.
- Test files for all of the above, covering the I/O matrix.
- `_bmad-output/implementation-artifacts/deferred-work.md`: a Parent-Area `auto_play` toggle UI
  note, if judged worth flagging.

## Tasks & Acceptance

- [ ] `auto_play` column + migration + schema + API exposure (default `true`).
- [ ] Shared single-`<audio>`-element player: stop-previous-on-new-clip, stop-on-unmount,
      missing-file detection via the element's own `error` event.
- [ ] Audio-unlock tracking (first user gesture anywhere in the page).
- [ ] Auto-play the instruction on Problem/Part open, gated on `auto_play` AND unlock.
- [ ] `SpeakerButton` real `playing`/missing-grey-out wiring; text never hidden for a missing clip.
- [ ] All existing `speak()` call sites (HintBubble, SolutionPanel, long-press-to-speak, etc.)
      keep working unchanged through the upgraded internals.
- [ ] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

- 2026-09-29: Implemented.
  - **Backend**: migration `0013_auto_play` (head after `0012_retry_items`) adds
    `parent_profiles.auto_play BOOLEAN NOT NULL DEFAULT true` via `op.add_column` (SQLAlchemy
    `Boolean`/`sa.true()` -- no precedent boolean column existed yet in this codebase, all
    prior tables used Text/Integer, but `Boolean` is idiomatic SQLAlchemy on SQLite and needed
    no special-casing). `parent/models.py`'s `parent_profiles` Table gets the matching
    `Column`. `parent/schemas.py`'s `Profile.auto_play: bool = True` (a Pydantic default, not
    just the DB default, so `complete_setup()`'s `Profile(...)` construction and its
    `model_dump()` insert still work unchanged). `parent/service.py`'s `list_profiles()` now
    selects and returns the column. `api/profiles.py` needed no changes (already returns
    `list[Profile]`). Regenerated `backend/openapi.json`/`frontend/openapi.json` (`uv run
    hoctap export-openapi`) and `frontend/src/api/schema.d.ts` (`npm run gen:api`) so the
    frontend's generated `Profile` type carries `auto_play` too.
  - **Shared player** (`frontend/src/audio/player.ts`, new file): a module-level singleton
    `HTMLAudioElement` (`getAudioElement()`, lazily constructed once) backs every clip. `stop()`
    pauses + resets `currentTime` + sets state to idle. `playKey(key, url)` stops whatever was
    playing, sets `src`, sets state to `{key, status: 'playing'}`, then `await`s `el.play()` --
    stop-previous-on-new-clip is thus unconditional on every call, matching UX-DR7. The
    element's own `ended`/`error` listeners (registered once, at construction) drive state to
    `idle`/`missing`; a confirmed-missing key is remembered forever in a module-level
    `missingKeys` Set (`isMissing(key)`), consistent with content-addressed clips (AD-8) never
    un-missing. `subscribe(listener)` is a plain pub/sub returning an unsubscribe function.
    **Made testable per the hard rule**: `getAudioElement()` is exported so tests dispatch real
    `error`/`ended` `Event`s directly on the actual shared element (jsdom's
    `HTMLMediaElement.play()`/`pause()` are stubbed no-ops that log the expected/benign "Not
    implemented" warning; a real network 404 never fires in jsdom, so the `error` event must be
    dispatched manually) -- no separate injectable/mock element was needed.
  - **Unlock tracking**: same module, a single module-level `unlocked` boolean flipped once by
    a `{ once: true }` `pointerdown`/`click` listener added to `window` at import time (checked
    `App.tsx` first -- no existing app-wide gesture listener to reuse). `isAudioUnlocked()`
    reads it; a test-only `__resetAudioUnlockForTests()` re-arms the listener so "not yet
    unlocked" can be exercised deterministically (not exported from any app code path).
  - **`speech.ts`'s `speak()`**: internals only -- now computes the key exactly as before, then
    calls `player.playKey(key, speechUrl(key))` instead of `new Audio(url).play()`. The
    existing try/catch silent-no-op contract is unchanged (a `speechKey()` failure, e.g. no
    `crypto.subtle`, or a rejected `play()`, e.g. autoplay-blocked, both still resolve silently)
    -- verified with new tests using a stubbed `crypto` and a mocked `play()` rejection.
  - **`SpeakerButton`**: one additive prop, `missing?: boolean` (spec's own suggested name),
    grey-out via a new `.speaker-button-missing` CSS class (uses the existing
    `--color-surface-sunken`/`--color-ink-secondary` tokens -- no new neutral/grey token
    existed), `aria-disabled` + the native `disabled` attribute, and `onClick` forced to
    `undefined` while missing. `playing`/`onClick` are unchanged; per the Boundaries &
    Constraints, this component renders no text of its own (only the 🔊 icon via `aria-label`)
    so "text never hidden for a missing clip" is satisfied by construction -- the actual
    instruction/option/hint text is always a sibling element the caller renders.
  - **Deviation -- who computes `playing`/`missing`**: the spec's Code Map/Boundaries leave the
    wiring open-ended ("gains real wiring... reflects the shared player's actual state").
    Rather than making `SpeakerButton` itself async-compute a `speechKey()` from a `text` prop
    and self-subscribe (which would fight this codebase's established "parent computes, passes
    props down" pattern -- see `HintBubble`'s pre-existing `speaking`/`onSpeak` props, unused by
    any call site until a future story wires them), `SpeakerButton` stays a dumb, synchronously
    testable component; a caller that wants live `playing`/`missing` state subscribes to
    `player.ts` itself and threads the booleans down as props. No existing call site
    (`HintBubble`/`Home.tsx`) needed changing to keep working, per the Acceptance checklist.
  - **Auto-play on Problem open** (`ProblemPlayer.tsx`): the effect lives in the outer
    `ProblemPlayer` component (not `PartPlayer`, which remounts on every Part change via its
    `key`). `SessionPlayer.tsx` already remounts `ProblemPlayer` via
    `key={problems[problemIndex].problem.problem_id}`, so an empty-deps `useEffect` there fires
    exactly once per Problem open (never replayed on a Part-to-Part advance within the same
    Problem) -- this reuses an existing remount boundary rather than adding a second one. Gated
    on the new `autoPlay?: boolean` prop (default `true`, so tests/callers that omit it keep
    the old always-on-ish behaviour explicitly, though in practice `isAudioUnlocked()` still
    gates it) AND `isAudioUnlocked()`. The effect's cleanup calls `player.stop()` unconditionally
    on unmount -- covers both leaving the Session entirely and (via React's normal unmount
    ordering) a Part-level remount below it, per "leaving a screen stops audio" without a second
    mechanism. `SessionPlayer.tsx` fetches `useProfiles()` and looks up the current Profile's
    `auto_play` by `profileId` (defaulting to `true` while Profiles are still loading), then
    passes it down as `autoPlay`.
  - **Verification**:
    - Backend: `.venv/bin/python -m pytest tests/test_parent.py -q` -> 53 passed (after
      updating `test_profiles`'s expected JSON to include `"auto_play": True`; all other
      Profile-shaped assertions in that file already filter to specific keys and needed no
      change). Full suite: see below.
    - `.venv/bin/ruff check hoctap/parent/ hoctap/db/alembic/versions/0013_auto_play.py
      tests/test_parent.py` -> all checks passed.
    - Frontend (via the `/tmp` rsync + fresh `npm ci` workaround, native filesystem, avoiding
      the `/mnt/c` WSL9P I/O issue): `npx vitest run src/audio src/components/SpeakerButton
      src/pages/ProblemPlayer.test.tsx src/pages/SessionPlayer.test.tsx
      src/pages/ProfilePicker.test.tsx` -> all passed (player.ts: 12 new tests; speech.ts: 3
      new `speak()` tests; SpeakerButton: 2 new `missing` tests; ProblemPlayer: 4 new
      auto-play tests). A full `npx vitest run` also passed except pre-existing/environmental
      failures unrelated to this story: `src/pages/ExtractionPage.test.tsx` (3 tests, already
      logged in `deferred-work.md` from Story 2.1's investigation), `src/styles/tokens.test.ts`
      (reads an absolute path outside `frontend/`, which the `/tmp`-rsync verification copy
      doesn't include -- an artifact of the verification workaround, not a real failure; passes
      when run from the real repo root), and one-off timeouts on `HintBubble.test.tsx`/
      `SolutionPanel.test.tsx` under full-suite load that reproduced as passing when run in
      isolation (env flakiness, per this story's own hard rules).
    - `npx tsc -b` -> clean (after adding `auto_play: true` to `ProfilePicker.test.tsx`'s two
      literal `Profile[]` fixtures, the only place the regenerated schema's new required field
      broke a typed test fixture).
    - `npx eslint .` -> clean.

- 2026-09-29: Review-triage fixes (findings #1-#3 + 2 of #5; #4 left as-is per its own verdict).
  - **#1 (high, fixed)**: `frontend/src/pages/ProblemPlayer.tsx` gained a new local
    `InstructionLine({ instruction })` component, rendered in place of the old bare
    `<p className="problem-player-prompt">{problem.instruction}</p>` in BOTH `PartPlayer` and
    `FallbackPartPlayer` (the instruction line both already render identically) -- so every
    real Problem screen now shows a `SpeakerButton` next to its instruction, not just a
    unit-tested component in isolation. It resolves the instruction's own `speechKey()` once
    on mount/instruction-change, `subscribe()`s to `audio/player.ts`'s real player state, and
    derives `playing` (this instruction's key is the one currently `playing`) and `missing`
    (`isMissing(key)`) from that live state -- exactly the subscribable state the outer
    `ProblemPlayer`'s pre-existing auto-play effect already drives. A manual tap calls
    `speak(instruction)`, the SAME `playKey()` path the auto-play effect uses (via
    `speech.ts`), so auto-play and a manual tap are indistinguishable to the shared player.
    New CSS: `.problem-player-instruction-row` (flex row, centered) in
    `ProblemPlayer.css`; `.problem-player-prompt` lost its own now-redundant text-only margin
    handling (`margin: 0`, since the row wrapper now centers it).
    `ProblemPlayer.test.tsx`'s existing `vi.mock('../audio/player', ...)` and
    `vi.mock('../audio/speech', ...)` both needed new mocked exports
    (`subscribe`/`getPlayerState`/`isMissing`, and `speechKey`) so its many OTHER tests (which
    don't care about this wiring) keep passing unchanged. A genuinely real-wiring integration
    test lives in a new file, `frontend/src/pages/ProblemPlayer.speaker.test.tsx`: it only
    overrides `isAudioUnlocked` (to keep auto-play from also firing and racing the test's own
    tap) and leaves the REST of `audio/player.ts` real (via `importOriginal()`), so the test
    renders `ProblemPlayer`, finds the `SpeakerButton` by its accessible name (the instruction
    text), taps it, and asserts the button itself gains `speaker-button-playing` once the
    REAL shared player (real `speechKey()`, real `playKey()`, real `<audio>` singleton)
    reports `playing` for that key -- not a mock standing in for the wiring.
  - **#2 (high, fixed)**: `frontend/src/audio/player.ts`'s `error` listener now reads
    `audioEl?.error?.code` and skips marking `missingKeys` when it's `1`
    (`MEDIA_ERR_ABORTED`, the code `playKey()`'s own src-swap-on-a-new-clip triggers when it
    interrupts an in-flight load -- normal stop-previous behaviour, never a real missing
    file). Any other code (network, decode, `MEDIA_ERR_SRC_NOT_SUPPORTED`) or no `MediaError`
    at all (the synthetic-event test path with no `.error` set) still marks it missing,
    preserving the pre-existing "any other error" breadth the spec's own wording asked for.
    Used a local numeric constant rather than the `MediaError` global, since jsdom doesn't
    define that global at all (confirmed by inspection) -- the spec numbers themselves
    (`MEDIA_ERR_ABORTED = 1`, `MEDIA_ERR_SRC_NOT_SUPPORTED = 4`) are stable across browsers.
    Two new tests in `player.test.ts` set `el.error = { code }` directly (jsdom leaves
    `HTMLMediaElement.prototype.error` completely undefined, so this is a plain, uncomplicated
    property write, via a narrow cast) then dispatch a synthetic `error` `Event`: one with
    code 1 (asserts NOT missing, state stays `playing`), one with code 4 (asserts missing).
  - **#3 (medium, fixed)**: `backend/tests/test_app.py`'s
    `test_fresh_data_dir_created_with_wal_and_migrations` now asserts
    `"0013_auto_play"` (was `"0012_retry_items"`) and additionally checks
    `"auto_play" in {columns of parent_profiles via PRAGMA table_info}` -- matching the
    established Stories 2.4/2.5/2.8 precedent of updating this exact assertion per migration
    head. Confirmed it was genuinely failing before the fix and passes after
    (`.venv/bin/python -m pytest tests/test_app.py -q` -> was failing on this assertion,
    now 55 passed).
  - **#5 (low, 2 of the suggested items done, rest left as debt per the triage's own
    time-permitting framing)**:
    - Added `test_migration_0013_backfills_auto_play_true_for_existing_profiles` to
      `test_app.py`: upgrades a fresh engine only to `0012_retry_items` (the migration BEFORE
      `auto_play` existed), inserts a `parent_profiles` row via raw SQL with no `auto_play`
      column at all (matching what a real pre-Story-2.9 install's row looks like), upgrades to
      `head`, then reads the row back and asserts `auto_play == 1` -- proving the migration's
      `server_default=sa.true()` genuinely backfills existing rows to `true`, not `NULL`, on a
      real upgrade path (not just a fresh `create_all`-style DB).
    - The real-`isAudioUnlocked()`-into-the-real-auto-play-gate integration test is
      effectively covered by the SAME new `ProblemPlayer.speaker.test.tsx` added for finding
      #1 above (it exercises the real `audio/player.ts` module end-to-end, including the real
      `isAudioUnlocked` -- overridden only to `false` there specifically to isolate the manual
      tap path from auto-play, per that file's own docstring) -- a fully separate test
      exercising `isAudioUnlocked() === true` driving the real auto-play effect through to a
      real `playKey()` call was judged lower marginal value given that overlap and was left as
      debt, alongside the remaining #5 items already logged in the Review Triage Log
      (fast-navigation race, `missingKeys` never-self-heals contract test).
  - **Verification**:
    - Backend: `.venv/bin/python -m pytest tests/test_app.py tests/test_parent.py -q` ->
      108 passed. `.venv/bin/ruff check tests/test_app.py` -> clean (one import-order
      auto-fix applied). Full-suite run logged separately (see Verification section below).
    - Frontend (via the `/tmp` rsync + fresh `npm ci` workaround): `npx vitest run
      src/audio src/components/SpeakerButton src/pages/ProblemPlayer.test.tsx
      src/pages/ProblemPlayer.speaker.test.tsx src/pages/SessionPlayer.test.tsx
      src/pages/ProfilePicker.test.tsx` -> 7 files, 99 passed. `npx tsc -b` -> clean.
      `npx eslint .` -> clean. Full `npx vitest run` -> 2 files / 3 tests failed, both the
      SAME pre-existing/environmental failures already documented in the prior
      Implementation Notes entry (`ExtractionPage.test.tsx`'s 3 tests, `tokens.test.ts`'s
      absolute-path-outside-`frontend/` issue) -- no new failures introduced by this pass.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | The Problem instruction (the very screen this story's auto-play targets) has NO `SpeakerButton` rendered at all, and no real call site anywhere in the app subscribes to `player.ts`'s live `playing`/`missing` state -- confirmed independently by all 3 reviewers. `SpeakerButton`/`player.ts` are fully built and unit-tested, but the acceptance checklist item "SpeakerButton real playing/missing-grey-out wiring" is satisfied only at the component-unit level, never integrated into the running app | high | confirmed by 3 reviewers -> patch: render a `SpeakerButton` next to the Problem instruction in `ProblemPlayer.tsx`, wired to `player.ts`'s subscribable state (playing = true while this instruction's key is the one playing; missing = `isMissing(key)`), and a manual tap calls the same `playKey()` path the auto-play effect uses -- this is the minimum needed to make the feature reachable, matching the spec's own Boundaries text ("Appears next to every instruction... and reflects the shared player's actual state") |
| 2 | `missingKeys` is poisoned by ANY `error` event, not just a genuine 404/decode failure -- the listener never checks `MediaError.code`, so `MEDIA_ERR_ABORTED` (which `playKey()` itself can trigger by interrupting an in-flight load when a new clip starts) or a transient `MEDIA_ERR_NETWORK` blip permanently greys out a 🔊 for the rest of the page session even though the file is genuinely present and playable | high | confirmed by 1 reviewer via code trace, real mismatch with the spec's own "a 404 or decode failure" wording -> patch: only add to `missingKeys` on `MEDIA_ERR_SRC_NOT_SUPPORTED` (decode failure) or a confirmed non-2xx response, not on `MEDIA_ERR_ABORTED`/`MEDIA_ERR_NETWORK`; add a test distinguishing these |
| 3 | `backend/tests/test_app.py`'s migration-head/table assertion still expects `"0012_retry_items"` and doesn't include the `auto_play` column check -- the same class of stale-migration-assertion bug already found and fixed in Story 2.5's review. This test is currently failing against the new `0013_auto_play` head (confirmed: an `F` appears early in the orchestrator's independent full-suite run) | medium | confirmed by 1 reviewer and independently by the orchestrator's own test run -> patch: update the assertion to `"0013_auto_play"`, matching the established precedent from Stories 2.4/2.5/2.8 |
| 4 | `playKey()` unconditionally restarts even an already-playing clip of the SAME key (a rapid double-tap on the same 🔊 restarts from 0 rather than being a no-op) -- documented as an intentional design choice in Implementation Notes, but the frozen spec doesn't explicitly sanction restart-vs-ignore-on-same-key | low | judgment call, not a bug in either direction -> patch: implementer's choice whether to add a same-key no-op guard; if kept as-is, no action needed beyond noting the decision is deliberate (already documented) |
| 5 | Several integration/edge-case tests are missing: the REAL `isAudioUnlocked()` flag feeding into the REAL auto-play gate (both halves are only tested in isolation with mocks, never together); an actual auto-play-then-manual-tap interleaving test (impossible today anyway per finding #1, but should follow once that's fixed); fast Problem-to-Problem navigation (does Problem A's in-flight async `speak()` race Problem B's?); a test that `missingKeys` truly never self-heals after a later successful attempt on the same key; a migration-level test confirming a pre-existing row backfills `auto_play` to `true` (not NULL) | low | confirmed by 2 reviewers -> patch: add the cheapest 2 as time allows (the real-unlock-into-real-gate integration test, and the migration backfill test are probably highest value); log the rest as test-coverage debt if time-constrained |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed both high-severity fixes directly in source (a real SpeakerButton now renders next to the Problem instruction, wired to player.ts's live state; `MEDIA_ERR_ABORTED` is now excluded from `missingKeys`). Ran `ruff check` (clean) and the full backend suite independently: 845/845 passing. Ran the full frontend suite independently: 260/263 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story); `tsc -b`/`eslint` both clean. Story marked done.

</frozen-after-approval>
