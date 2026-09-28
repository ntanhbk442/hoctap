---
title: 'Story 2.1: Design tokens, Nunito and core components'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:8d04ac4f01715688c7348142b4a1d41fa7931801'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-hoctap-2026-09-26/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The frontend has no design system yet — plain browser defaults, no Vietnamese-capable self-hosted font, and none of the child-facing widgets the Problem player (Epic 2's later stories) will build on. Every screen from here needs the same tokens and the same base components, or each story reinvents its own styling.

**Approach:** Turn `DESIGN.md`'s frontmatter tokens into CSS custom properties exactly as specified (UX-DR1), self-host Nunito with the Vietnamese subset (UX-DR2), and build the ten named child-facing components as reusable React components, each matching its `DESIGN.md` component spec and its behavioural note in `EXPERIENCE.md`. A `useMotion()` hook centralises `prefers-reduced-motion` so every later animated component (Star burst, feedback banners, etc.) reads one source of truth.

## Boundaries & Constraints

**Always:**
- **Tokens as CSS custom properties**, one file `src/styles/tokens.css`, generated to match `DESIGN.md`'s frontmatter exactly — every `colors.*` key becomes `--color-<key>` with its exact hex value (no rounding, no re-deriving), every `typography.*` role becomes `--font-<role>-family/-size/-weight/-line-height`, `rounded.*` becomes `--radius-<key>`, `spacing.*` (including the two named keys `touch-min`, `key`) becomes `--space-<key>`. A test parses `DESIGN.md`'s YAML frontmatter and asserts every value is present verbatim in the generated CSS, so the token file can't silently drift from the design doc.
- **Nunito self-hosted**: `.woff2` files (weights actually used — 600, 700, 800; the design uses no others) placed under `frontend/public/fonts/`, referenced by `@font-face` in `src/styles/fonts.css` with `unicode-range` covering the Vietnamese subset (Latin + Latin Extended Additional, matching Google Fonts' own `vietnamese` subset range) so only that subset downloads. `font-display: swap`. The service worker (`vite-plugin-pwa`'s existing `workbox` config) precaches the font files, verified by a build-output check that `dist/fonts/*.woff2` are listed in the generated precache manifest.
- **Ten components**, each in `src/components/<Name>/<Name>.tsx` with a co-located test, matching `DESIGN.md`'s Components section and using only the CSS tokens (no hard-coded hex/px for anything token-covered):
  1. **SpeakerButton** — round, `primary-soft` background, `primary` icon; `size=touch-min`; a visual "pulsing" state class while `playing` is true (CSS animation, not JS timers) — this story renders the visual states only; the real audio hookup is Story 2.9.
  2. **HomeCard** — `card-home` spec; a `wide` variant (double-width, `primary-pressed` bottom edge) for "Bài hôm nay".
  3. **AnswerSlot** — `answer-slot` spec; `default` / `active` (border colour swap) / `correct` (green + ✔) / `wrong` (orange + shake, skipped entirely under reduced motion) states.
  4. **NumberPad** — a 3×4 grid of `numpad-key`-styled keys (0–9, ⌫, and a comma key that the caller can hide via a prop, per FR-9's grades-1–3-vs-4–5 split); emits a digit/backspace/comma callback, no numeric logic (that's the widget layer in later stories).
  5. **ChoiceChip** — `choice-chip` spec; `selected` state (`primary-soft` background); supports a text child or an image child.
  6. **FeedbackBanner** — `feedback-correct` / `feedback-retry` variants sliding up from the bottom (CSS transform/opacity transition; instant show/hide under reduced motion per UX-DR11).
  7. **HintBubble** — `hint-bubble` spec, with a 💡 icon slot and a 🔊 slot (renders the SpeakerButton).
  8. **SolutionPanel** — a stepped reveal container (steps rendered one at a time via a `revealedCount` prop — no internal timing/animation logic yet, that arrives with the real Solution flow in Epic 2's grading stories).
  9. **ProgressDots** — `progress-dot` spec; `done` / `current` / `todo` per dot from an array prop.
  10. **StarBurst** — an accessible "N ⭐" indicator with a burst animation on mount when `justEarned` is true, skipped under reduced motion (shows the static end-state instead).
- **`useMotion()` hook** (`src/hooks/useMotion.ts`): wraps `window.matchMedia('(prefers-reduced-motion: reduce)')`, reactive to changes (listens for the media query's `change` event), with a safe SSR/test fallback (`false`) when `matchMedia` is unavailable — every animated component above reads this hook rather than querying the media feature itself, so tests can mock one hook.
- **No red on child components (UX-DR5)**: a lint-level check (a small test scanning the ten components' source and `tokens.css` for the literal `--color-` values search: none of the child-facing component files may reference an undefined "danger/error/red" token, and `tokens.css` itself must not define one — this positively encodes UX-DR5 as a test rather than a docstring).
- **Touch targets**: every interactive component (SpeakerButton, AnswerSlot, NumberPad keys, ChoiceChip) renders at `--space-touch-min` (64px) or larger — asserted in each component's test via computed/inline style, not just visual review.
- **Parent Area is explicitly untouched by this story** — it keeps its current plain styling (per the existing `index.css` comment); these tokens and components are for the child-facing screens only. Parent styling tokens (`parent-surface`, `parent-border`, `parent-body`, `parent-heading`) are added to `tokens.css` now (since they're in `DESIGN.md`'s frontmatter) but not yet consumed anywhere.

**Never:**
- No Problem-type-specific logic (number formatting, grading, template rendering) — these are pure presentational components consumed by later stories.
- No real TTS/audio wiring in SpeakerButton (Story 2.9) and no real Session/progress state wiring in ProgressDots/StarBurst (Stories 2.4/3.1) — this story only builds the visual components to spec.
- No changes to any existing screen (Home, ParentHome, Setup, etc.) to *use* these components yet — that migration happens naturally as later Epic 2 stories build the screens that need them.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Token fidelity | DESIGN.md frontmatter | every colors/typography/rounded/spacing value present verbatim in tokens.css | a mismatch fails the generation test |
| Font precached | production build | `dist/fonts/*.woff2` listed in the Workbox precache manifest | build-output test |
| AnswerSlot states | default/active/correct/wrong props | matching visual class + `aria-live` announcement text differs | N/A |
| Reduced motion, wrong | `prefers-reduced-motion: reduce`, wrong state | no shake class applied, colour/icon change still shown | N/A |
| Reduced motion, StarBurst | `justEarned=true`, reduced motion | static "N ⭐" shown immediately, no burst animation class | N/A |
| Touch targets | render each interactive component | computed min dimension ≥ 64px | N/A |
| No red | scan component sources + tokens.css | no undefined danger/red token reference found | test fails if one is added |
| NumberPad comma | `showComma=false` | comma key not rendered; grid still fills sensibly | N/A |
| SolutionPanel reveal | `revealedCount=2` of 4 steps | first 2 steps rendered, rest absent (not just hidden) | N/A |
| ProgressDots | `dots=['done','current','todo','todo']` | 4 dots, matching colour classes in order | N/A |
| SpeakerButton pulsing | `playing=true` | pulsing animation class present; absent when `playing=false` | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/index.css` -- the existing plain global stylesheet; the "(design tokens arrive in Epic 2)" comment on `.parent` marks where Parent styling is deliberately left alone.
- `frontend/vite.config.ts` -- the existing `VitePWA`/`workbox` config (precache patterns) to extend so the new font files are included.
- `frontend/src/App.tsx`, `src/main.tsx` -- where `tokens.css`/`fonts.css` get imported globally.
- `_bmad-output/planning-artifacts/ux-designs/ux-hoctap-2026-09-26/DESIGN.md` -- the frontmatter is the literal source of truth for every token value; the Components section for each of the ten components' visual spec; `EXPERIENCE.md` (same folder) for the Accessibility Floor and Interaction Primitives (reduced motion, no-colour-alone) behavioural rules.
- `frontend/src/test/render.tsx` -- the existing test-render helper pattern (used by ParentHome/Setup tests) to follow for the new component tests.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/scripts/gen-tokens.mjs` + `npm run gen:tokens` -- parses `DESIGN.md`'s YAML frontmatter and writes `frontend/src/styles/tokens.css`; committed output, regenerated on demand (matching the `gen:api` pattern already in this repo).
- [x] `frontend/public/fonts/nunito-{600,700,800}.woff2` (sourced from Google Fonts' Nunito, Vietnamese-subsetted) + `frontend/src/styles/fonts.css` (`@font-face` rules).
- [x] `frontend/vite.config.ts` -- add the font files to the Workbox precache glob.
- [x] `frontend/src/hooks/useMotion.ts` (+ test).
- [x] `frontend/src/components/{SpeakerButton,HomeCard,AnswerSlot,NumberPad,ChoiceChip,FeedbackBanner,HintBubble,SolutionPanel,ProgressDots,StarBurst}/` -- one folder per component, `.tsx` + `.css` (using only token custom properties) + `.test.tsx`.
- [x] `frontend/src/styles/no-red.test.ts` (or similar) -- the UX-DR5 scanning test described above.
- [x] `frontend/src/main.tsx` -- import `tokens.css`/`fonts.css` globally (before `index.css`); leave `.parent`/Parent Area rules in `index.css` untouched.

**Acceptance Criteria:**
- Given `npm run build`, when the output is inspected, then `tokens.css` contains every `DESIGN.md` frontmatter value verbatim and the font files appear in the precache manifest.
- Given each of the ten components rendered in its test with every documented state/prop combination, then the matching DESIGN.md-specified colours/sizes apply, touch targets are ≥ 64px, and reduced-motion variants render correctly with `useMotion()` mocked true/false.

## Implementation Notes

- **Real Nunito glyph data, not placeholders.** Google's `fonts.googleapis.com/css2?family=Nunito:600,700,800` now serves Nunito as a single variable font (has `fvar`/`gvar`), so the naive per-weight download gives the *same* file for every weight. Instead: downloaded the variable font's `latin` instance (basic Latin/digits) and its `vietnamese` instance (Vietnamese-only diacritics, confirmed via `fonttools ttx -t cmap` — it alone has no basic-Latin glyphs) from `fonts.gstatic.com`, used `fonttools varLib.instancer` to produce true static instances at `wght=600/700/800` from each, then `fonttools merge` to combine each pair's glyph sets into one font per weight (verified the merged `cmap` has both `A`/`0` and `Đ`/combining-acute), fixed up the `name`/`OS-2`/`head` tables per weight (family "Nunito", correct `usWeightClass`, bold bit only on 700), and re-flavored to `.woff2`. These are genuine, correctly-weighted Nunito glyphs — no placeholder/dummy binaries were needed since network access to Google Fonts was available in this sandbox.
- **`unicode-range` covers Basic Latin + the Vietnamese-specific ranges** (`U+0000-00FF` plus `U+0102-0103, 0110-0111, 0128-0129, 0168-0169, 01A0-01A1, 01AF-01B0, 0300-0301, 0303-0304, 0308-0309, 0323, 0329, 1EA0-1EF9, 20AB`), not Google's own fragmented `vietnamese` subset alone — that subset (as served today) contains *only* the diacritic/tone glyphs and no basic Latin letters or digits, so using it verbatim would have silently fallen back to a system font for every plain digit and ASCII letter. This matches the spec's own parenthetical ("Latin + Latin Extended Additional").
- **Tokens/fonts wiring lives in `src/main.tsx`** (imports `./styles/tokens.css` and `./styles/fonts.css` before `./index.css`), not inside `index.css` itself via `@import` — functionally equivalent (both end up in the same global stylesheet graph before Vite bundles), but keeps `index.css` completely untouched, which more literally satisfies "Parent Area is explicitly untouched by this story."
- **Touch-target testability:** jsdom (the Vitest environment) does not resolve CSS custom properties in `getComputedStyle` (verified directly: a `var(--x)` inline style or class rule reads back as the literal string `"var(--x)"`, never a resolved px value) and this repo's Vitest config does not enable CSS processing for tests (`css` is unset, so external stylesheet rules are not applied to jsdom at all). So each touch-sized element (SpeakerButton, AnswerSlot, NumberPad keys, ChoiceChip) also sets its size as inline `style` from `src/styles/dimensions.ts` (`TOUCH_MIN = 64`, `KEY_SIZE = 80` — mirroring `tokens.css`'s `--space-touch-min`/`--space-key`), so each component's test can assert the rendered size deterministically, per the spec's own I/O matrix ("asserted... via computed/inline style, not just visual review"). The CSS files still use the token custom properties for real browser rendering.
- **`gen-tokens.mjs`** uses `js-yaml` (added as a direct devDependency; it was already present transitively) to parse the `---`-delimited frontmatter and writes every `colors.*` / `typography.<role>.*` / `rounded.*` / `spacing.*` key verbatim. `tokens.test.ts` independently re-parses `DESIGN.md`'s frontmatter (not by importing the generator) and asserts each value is present in the committed `tokens.css`, so a stale/hand-edited token file fails the test even if the generator itself would produce something different.
- **HomeCard's long-press** uses a `useRef`-based timer (not component-local `let` variables) so it's correct across re-renders; a tap that ends before 500ms fires `onClick`, a hold past 500ms fires `onLongPress` and suppresses the click a real browser still sends on pointerup.

## Spec Change Log

- 2026-09-28 — Note (implementer): no frozen-intent changes. Two small non-frozen clarifications recorded above under Implementation Notes: tokens/fonts are wired from `main.tsx` rather than via `@import` inside `index.css` (same net effect, `index.css` stays byte-for-byte untouched), and the font files' `unicode-range` covers Basic Latin + Vietnamese-specific ranges rather than Google's own (Latin-less) `vietnamese` subset id, matching the spec's own "Latin + Latin Extended Additional" wording.
- 2026-09-28 — Note (implementer, environment): this shared machine's `/mnt/c` (WSL9p/drvfs) filesystem is extremely slow for many-small-file Node workloads — `require('jsdom')` alone took ~90s there (vs. ~1s on a native filesystem), which exceeds Vitest's hard-coded 60–90s worker-start timeouts regardless of `--pool`, `maxWorkers`, or free memory (this run had 1.5–6.6GiB "available" throughout, so it was not the memory-pressure failure mode recorded in Stories 1.9/1.10). Worked around it by `rsync`-ing the frontend tree (including `node_modules`, already `npm install`ed) to the native ext4 filesystem under `/tmp` and running the full Vitest suite, build, and lint from there; the source of truth (all edits) remained under `/mnt/c/.../frontend`. `require('jsdom')` took ~1.1s from `/tmp`, and the suite completed in ~24s.
- 2026-09-28 — Finding (implementer, pre-existing, unrelated): running the full suite from a working filesystem surfaced 3 pre-existing failures in `src/pages/ExtractionPage.test.tsx` ("starts one", "asks to confirm the spend", "cancels a run") — confirmed to fail in isolation too, and unrelated to this story (no file this story touches is imported by that page or its test). Story 1.10's own Spec Change Log records that this exact file could never be run to completion on this machine before now, so this may be the first time it has actually executed here; it is plausible nobody has seen it pass. Not investigated or fixed as out of scope for Story 2.1 — flagging for the owner.
- 2026-09-28 — Fixes (implementer, addressing Review Triage Log #1–#10, #12): all confirmed findings patched.
  - **#1 HomeCard long-press:** the click handler now consumes-and-resets `longPressed.current` the moment any click is handled (not only on the next `pointerdown`), so a keyboard Enter/Space activation after a prior long-press is never permanently swallowed. Added `onPointerCancel={endPress}` and a `clearTimeout` at the top of `startPress` before arming a new timer. Added three tests: keyboard activation after a prior long-press, pointer-cancel clearing a pending timer, and a second `pointerdown` clearing the first pending timer.
  - **#2 dimensions.ts drift:** `tokens.test.ts` now asserts `TOUCH_MIN`/`KEY_SIZE` (in px) equal the parsed `DESIGN.md` `spacing['touch-min']`/`spacing['key']` strings.
  - **#3 missing 500 weight:** derived `nunito-500.woff2` with the same fonttools instance+merge method as 600/700/800 (verified real glyph coverage for basic Latin + Vietnamese), added its `@font-face` rule to `fonts.css`.
  - **#4 SpeakerButton `aria-pressed`:** removed (this isn't a toggle button); added `aria-busy={playing}` instead.
  - **#5 AnswerSlot accessible name:** now `` `${label}: ${value || 'trống'}` ``, so the digit(s) typed are exposed to assistive tech, not just transiently via the live-region announcement. Test added.
  - **#6 FeedbackBanner hidden state:** added `aria-hidden={!visible}` and `pointer-events: none` on `.feedback-banner-hidden`. Test added; one pre-existing test adjusted to query by text instead of role, since `getByRole` correctly excludes `aria-hidden` elements now.
  - **#7 gen-tokens.mjs validation:** added `validateDesign()` — throws a clear error if the frontmatter isn't an object, or if any `typography.<role>` is missing `fontFamily`/`fontSize`/`fontWeight`/`lineHeight`; wired into `main()`.
  - **#8/#9 tokens.test.ts duplication:** now imports `designPath` and `parseFrontmatter` from `gen-tokens.mjs` instead of re-declaring the path and re-implementing the frontmatter regex (needs a `@ts-expect-error` on the `.mjs` import — no type declarations for a plain script — confirmed this doesn't mask a real error by running `tsc -b` clean).
  - **#10 ChoiceChip hardcoded 88:** moved to `CHOICE_CHIP_MIN_HEIGHT` in `dimensions.ts`, with a comment noting it's `DESIGN.md`'s `components.choice-chip.minHeight` literal (not a `{spacing.*}` token, so it's outside item #2's sync test).
  - **#12 spec wording:** fixed the Tasks checkbox line to say `main.tsx` (Code Map already said this correctly).
  - **#11 barrel export, #13 precache-manifest test:** left as rejected, per explicit instruction not to add either.
  - Verified with the coordinator's faster method: `rsync --exclude=node_modules --exclude=dist --exclude=dev-dist` (source only) to `/tmp`, then `npm ci` there (~50s) instead of copying `node_modules`. Ran only the tests covering edited files (`HomeCard`, `SpeakerButton`, `AnswerSlot`, `FeedbackBanner`, `ChoiceChip`, `tokens.test.ts`, `no-red.test.ts` — 7 files, 34/34 passed), plus `npx tsc -b` (clean) and `npm run lint` (clean) from the same synced copy, and re-ran `gen-tokens.mjs` there to confirm its output is still byte-identical to the committed `tokens.css` after adding validation.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | HomeCard long-press guard (`longPressed.current`) only resets on pointerdown; a keyboard Enter/Space click after any prior long-press is silently swallowed forever; also no `onPointerCancel` handler, and a second pointerdown before the first timer fires leaks the earlier timeout | high | confirmed by 2 reviewers independently, different angles (stuck ref + missing pointercancel + timer race) -> patch: reset the guard on click too (or redesign so click isn't gated by a ref that only pointer events clear), add onPointerCancel=endPress, clearTimeout before setting a new one; add a keyboard-activation test |
| 2 | dimensions.ts (TOUCH_MIN/KEY_SIZE) hand-duplicates tokens.css's touch-min/key with no test tying them together; a future DESIGN.md spacing change could update tokens.css and its own hardcoded-string test but leave dimensions.ts (and therefore actual rendered component sizes) stale, undetected | high | confirmed with a concrete demonstrated failure-to-catch scenario -> patch: add an assertion (tokens.test.ts or new dimensions.test.ts) that TOUCH_MIN/KEY_SIZE equal the parsed DESIGN.md spacing values |
| 3 | fonts.css self-hosts only weights 600/700/800; DESIGN.md's parent-body role specifies weight 500, which has no @font-face and will synthesize/fallback, contradicting the offline-font guarantee for that token | medium | confirmed — real gap, though parent-body is unconsumed until a later story migrates Parent Area styling -> patch: add the 500 weight (or explicitly note in tokens.css/fonts.css that parent-body is deferred until Parent Area migration, with a tracking comment) |
| 4 | SpeakerButton sets aria-pressed={playing}, implying toggle-button semantics for what is really a momentary "play this audio" action | medium | confirmed against ARIA authoring practices -> patch: remove aria-pressed; use aria-label + a live status region (or aria-busy) if "currently playing" needs to be conveyed |
| 5 | AnswerSlot's aria-label replaces the accessible name entirely, so the digit(s) actually entered are not exposed to screen readers except transiently via a live-region announcement | medium | confirmed via accessible-name computation rules -> patch: keep the value in the accessible name, e.g. aria-label={`${label}: ${value || 'trống'}`} (empty/blank), updated as value changes |
| 6 | FeedbackBanner's hidden state only animates transform/opacity; the element stays in the DOM and reachable by assistive tech / pointer events while invisible | medium | -> patch: add aria-hidden when hidden, and pointer-events:none in that state |
| 7 | gen-tokens.mjs has no validation of DESIGN.md's frontmatter shape (missing/malformed typography fields, null frontmatter) — fails with an unhelpful crash instead of a clear message | low | dev-only script, but cheap to fix -> patch: add the two suggested guards (frontmatter is an object; each typography role has its 4 fields) |
| 8 | The DESIGN.md path is hardcoded independently in both gen-tokens.mjs and tokens.test.ts | low | -> patch: export the path as a constant from one, import in the other, or put it in one small shared config module |
| 9 | tokens.test.ts reimplements gen-tokens.mjs's frontmatter-parsing regex instead of importing parseFrontmatter | low | -> patch: import and reuse the function |
| 10 | ChoiceChip hardcodes minHeight:88 inline instead of a named constant/token like the other components use | low | -> patch: add to dimensions.ts alongside TOUCH_MIN/KEY_SIZE (and cover it by the new item-2 sync test) |
| 11 | No barrel export (src/components/index.ts) for the ten new components | low | reject — not requested by spec; every consuming story can add imports as needed, premature to add now |
| 12 | Tasks/Code Map wording says tokens/fonts are imported "globally" via index.css; actual (correct) implementation imports them in main.tsx before index.css | low | spec-wording nit, not a code bug (cascade order is correct: tokens+fonts load first, then index.css's Parent Area overrides) -> patch: fix the one line of spec prose in Code Map, no code change |
| 13 | No test inspects the generated service-worker precache manifest/globPatterns for the font files (only manually confirmed by the orchestrator this round) | low | reject — no established pattern of testing workbox config anywhere in this repo; out of proportion for this story |

## Verification

**Commands run:**
- `cd frontend && npm run gen:tokens` -- wrote `src/styles/tokens.css`; matches `DESIGN.md`'s frontmatter verbatim (spot-checked and covered by `tokens.test.ts`).
- `cd frontend && npm install` -- added `js-yaml`/`@types/js-yaml` as direct devDependencies (previously only transitive).
- `cd frontend && npx tsc -b` -- clean, no type errors (from `/mnt/c`, ~70s — slow but did complete; unlike Vitest, `tsc`'s own worker model doesn't hit the same hard 60–90s timeout).
- `cd frontend && npm run build` -- succeeded: `dist/fonts/{nunito-600,700,800}.woff2` present, and confirmed present in the generated `dist/sw.js` Workbox precache manifest (`grep -o '"fonts/[^"]*\.woff2"' dist/sw.js` -> all three). 15 precache entries, 504.94 KiB, built in ~40s.
- `cd frontend && npm run lint` -- clean (run from the `/tmp` copy after the `/mnt/c` slow-FS workaround above).
- `cd frontend && npx vitest run` (from the `/tmp` copy, see Spec Change Log) -- **127/130 tests passed, 23/24 files passed.** The only failures are the 3 pre-existing/unrelated `ExtractionPage.test.tsx` failures noted above. Every test for this story's own work passed: `tokens.test.ts` (5), `no-red.test.ts` (2), `useMotion.test.ts` (3), and all ten components' `.test.tsx` files (SpeakerButton, HomeCard, AnswerSlot, NumberPad, ChoiceChip, FeedbackBanner, HintBubble, SolutionPanel, ProgressDots, StarBurst).

**Expected vs actual:** all pass except the one noted, pre-existing, unrelated `ExtractionPage.test.tsx` gap (see Spec Change Log) -- not caused by, or fixed as part of, this story.

**Left incomplete / risky:**
- The `ExtractionPage.test.tsx` pre-existing failure above is unresolved — needs its own investigation by the owner, unrelated to this story's scope.
- The Nunito `.woff2` files are real, correctly-weighted, network-sourced glyph data (not placeholders) built by instancing and merging Google's own variable-font subsets with `fonttools`, but they were assembled by this agent rather than downloaded as Google's pre-built static per-weight files (which no longer exist as such). If a byte-for-byte "exactly what Google Fonts would have served historically" file is ever required, that would need re-deriving; functionally (glyph shapes, coverage, weights) they are correct.
