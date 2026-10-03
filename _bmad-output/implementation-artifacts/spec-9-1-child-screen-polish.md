---
title: 'Story 9.1: Child screen navigation and visual polish'
type: 'feature'
created: '2026-10-03'
status: 'done'
baseline_commit: '82ede48'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Anh reported the child-facing screens feel hard to use -- specifically "looks
plain or unfinished" and "hard to find things / get lost". Direct code investigation (not
guesswork) found the root cause: `DESIGN.md`'s design tokens ARE correctly generated into
`frontend/src/styles/tokens.css`, and some leaf components built from them (`HomeCard`,
`Badge`, `AnswerSlot`, `NumberPad`) ARE correctly styled per spec. But the PAGE SHELLS
around those components were never wired up: `index.css`'s base `:root`/`body` uses generic
`system-ui` font and white background (never the generated Nunito/warm-cream tokens), and
every child screen (Home, Library, LessonDetail, Badges, SessionPlayer/the Problem screen)
uses a text link buried at the BOTTOM of the page ("Về trang chủ" / "Về Sách") instead of
`EXPERIENCE.md`'s own explicit navigation rule: "every child surface has one big ⬅ back
button in the top-left corner and nothing else in the chrome." The Problem screen -- where a
child spends the most time -- has no persistent top bar at all, and (before Story 8.1
extended it to quiz/exam only) showed no progress indicator outside those two modes either.

**Approach:** Fix the page shells, not the design system or the leaf components (neither is
broken). A new shared `ChildTopBar` component (⬅ back, progress dots, 🔊 where relevant)
replaces every bottom-of-page text link. `index.css`'s base styles switch to the design
tokens so every child page inherits the right look by default instead of opting in
component-by-component. Library's lesson rows and the Badges layout are restyled to match
`HomeCard`'s already-correct chunky-card treatment. Pure frontend change: CSS plus one new
component and its wiring into 5 existing pages.

## Boundaries & Constraints

**Always:**
- `ChildTopBar` lives at `frontend/src/components/ChildTopBar/ChildTopBar.tsx`, following
  this codebase's established one-component-per-directory-with-its-own-CSS pattern (see
  `components/HomeCard/`, `components/Badge/`). Props: `onBack: () => void` (always
  required -- every child screen has somewhere to go back to), `dots?: DotState[]`
  (optional -- only Sessions pass this), `onSpeak?: () => void` (optional 🔊, only where a
  screen has something sensible to read aloud, e.g. the screen's own title).
- Every child screen's existing bottom "Về trang chủ"/"Về Sách" `<Link>` is REMOVED and
  replaced by `ChildTopBar` at the top of that screen's `<main>`, with the exact same
  navigation target the old link had (Home -> none needed, it IS home; Library/LessonDetail
  -> `/`; Badges -> `/`; SessionPlayer -> `/library`). No new navigation targets are
  invented -- this is a relocation and visual upgrade of existing back-navigation, not a
  change to where "back" goes.
- SessionPlayer's `ProgressDots` (currently gated to `isQuiz || isExam` only, per Story 8.1)
  moves into `ChildTopBar` and is shown for EVERY mode with more than one Problem in the
  current chunk, matching `EXPERIENCE.md`'s literal "top bar (back, progress dots, 🔊)" --
  this was always the intended behavior for every Session, not just quiz/exam; Story 3.4
  and 8.1 each separately, narrowly extended the old quiz-only gate rather than fixing the
  underlying gap, which this story now closes for good.
- `index.css`'s `:root` font-family becomes `var(--font-body-family)` (Nunito) and `body`'s
  background becomes `var(--color-surface-base)` (warm cream) -- these are the ALREADY
  GENERATED tokens in `styles/tokens.css`, not new values to invent. Parent Area screens
  (anything under `/parent/*`) must visually look UNCHANGED by this -- check `parent-surface`/
  `parent-border` greys are applied somewhere that overrides the new base, or scope the new
  base rule to child screens specifically (implementer's call on the cleanest CSS scoping
  mechanism; document whichever is chosen).
- Library's `.library-lesson-row` (and the equivalent Unit/Book headers) and Badges' own
  layout are restyled using the SAME tokens `HomeCard.css` already uses
  (`--radius-lg`/`--radius-md`, `--color-surface-raised`, the `box-shadow: 0 4px 0 0
  var(--color-surface-sunken)` "physical button" treatment) -- reuse the existing visual
  language, don't invent a new one.
- Every existing test that currently asserts on the old bottom-link text/role (e.g.
  `Badges.test.tsx`'s `getByRole('link', { name: 'Về trang chủ' })`,
  `SessionPlayer.test.tsx`'s `getAllByText('Về Sách')`) is updated to assert on
  `ChildTopBar`'s new back-button affordance instead -- these are expected, deliberate test
  updates, not regressions.

**Never:**
- No change to WHERE any back button navigates to (only how it looks/where it sits).
- No change to the Parent Area's own navigation or visual design -- explicitly out of scope
  per epic-9-context.md.
- No new Problem Type, Session mode, or backend/API change of any kind -- this is CSS plus
  one new presentational component.
- No change to `DESIGN.md`/`EXPERIENCE.md`/`tokens.css` themselves -- the design system is
  already correct; this story makes the app actually use it.
- Don't invent a hamburger menu, a tab bar, or any new navigation affordance beyond the
  single ⬅ back button `EXPERIENCE.md` already specifies -- "flat navigation... no tabs, no
  drawer, no menus" is an existing, deliberate rule, not something this story revisits.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Home | loaded | No `ChildTopBar` (Home has nowhere "back" to go -- it already has no back link today) | N/A |
| Library | loaded | `ChildTopBar` with ⬅ navigating to `/`, no progress dots (not a Session) | N/A |
| LessonDetail | loaded | `ChildTopBar` with ⬅ navigating to `/library` | N/A |
| Badges ("Huy hiệu của em") | loaded | `ChildTopBar` with ⬅ navigating to `/` | N/A |
| SessionPlayer, practice mode, 1 Problem in chunk | mid-session | `ChildTopBar` with ⬅ to `/library`, no dots (nothing to show progress through) | N/A |
| SessionPlayer, practice mode, multiple Problems | mid-session | `ChildTopBar` shows progress dots (done/current/todo), same visual states as today's quiz/exam dots | N/A |
| SessionPlayer, quiz/exam mode | mid-session | Same `ChildTopBar` + dots as every other mode now gets -- no behavior change from today's quiz/exam dots themselves, just no longer gated to only those two modes | N/A |
| Reduced Motion | any child screen | `ChildTopBar`'s back button and dots have no motion/animation to suppress in the first place (this story adds no new motion) | N/A |
| Parent Area screens | any `/parent/*` route | Visually unchanged -- the new base `index.css` font/background rule must not leak into Parent Area styling | N/A |
| Keyboard navigation | any child screen, PC browser | `ChildTopBar`'s back button is a real, focusable, labelled `<button>`/`<Link>` -- same accessibility floor `EXPERIENCE.md` already requires everywhere | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/components/ChildTopBar/ChildTopBar.tsx` (new), `ChildTopBar.css` (new),
  `ChildTopBar.test.tsx` (new) -- the shared component.
- `frontend/src/index.css` -- `:root`/`body` base font/background switch to tokens; scoping
  so Parent Area screens are visually unaffected.
- `frontend/src/pages/Home.tsx` -- no `ChildTopBar` needed (nowhere to go back to), but
  confirm it correctly inherits the new base page styling (font/background) with no
  per-page override needed.
- `frontend/src/pages/Library.tsx` -- `ChildTopBar` replaces the bottom "Về trang chủ"
  `<Link>`; `.library-lesson-row`/unit/book headers restyled.
- `frontend/src/pages/LessonDetail.tsx` -- `ChildTopBar` replaces the bottom "Về Sách"
  `<Link>`.
- `frontend/src/pages/Badges.tsx` -- `ChildTopBar` replaces the bottom "Về trang chủ"
  `<Link>`; badge grid/layout restyled to the `HomeCard` visual language where it doesn't
  already match.
- `frontend/src/pages/SessionPlayer.tsx` -- `ChildTopBar` replaces the bottom "Về Sách"
  `<Link>`; `ProgressDots` rendering moves into it and its gate changes from `isQuiz ||
  isExam` to "more than one Problem in the current chunk", for every mode.
- `frontend/src/pages/Badges.test.tsx`, `SessionPlayer.test.tsx` -- update the existing
  assertions on the old bottom-link text/role to the new `ChildTopBar` affordance.
- `frontend/src/pages/Library.test.tsx`, `LessonDetail.test.tsx` (if it exists) -- extend
  for the new `ChildTopBar`.

## Tasks & Acceptance

**Execution:**
- [ ] `ChildTopBar` component + its own tests (back button navigates correctly, dots render
      the right states, 🔊 fires when provided, renders nothing extra when optional props
      are omitted).
- [ ] `index.css` base font/background switched to tokens, verified not to leak into
      Parent Area screens.
- [ ] `Library.tsx`, `LessonDetail.tsx`, `Badges.tsx`, `SessionPlayer.tsx` wired to
      `ChildTopBar`, old bottom links removed.
- [ ] `SessionPlayer.tsx`'s progress-dots gate changed to "every mode, chunk length > 1".
- [ ] Library lesson rows / Badges layout restyled to the `HomeCard` visual language.
- [ ] Existing tests referencing the old bottom links updated; new tests for the above.
- [ ] Full frontend suite green; manual/visual sanity check if a dev server is available
      (this project's established practice for UI changes).

**Acceptance Criteria:**
- Given any child screen with a `ChildTopBar`, when a child looks at the top-left corner,
  then a clearly visible ⬅ button is there, and tapping it goes to exactly where the old
  bottom link used to go.
- Given a practice Session with 3 Problems in its current chunk, when the child is on
  Problem 2, then the top bar shows 3 dots: done, current, todo -- the same visual states
  quiz/exam mode already show today, now for every mode.
- Given the Parent Area (any `/parent/*` screen), when it renders, then its visual
  appearance (fonts, background) is unchanged from before this story.
- Given Library, when it renders, then lesson rows look like `HomeCard`-style cards (icon,
  rounded corners, the chunky bottom-edge shadow), not the old thin bordered list rows.

## Design Notes

`ChildTopBar` is deliberately a thin presentational wrapper, not a smart/connected
component -- every page passes it exactly what it needs (`onBack`, optional `dots`, optional
`onSpeak`), and it owns no routing or data-fetching logic itself. This keeps it trivially
reusable and testable in isolation, consistent with this codebase's existing component
conventions (`HomeCard`, `SpeakerButton`, etc. all follow the same shape).

The Parent-Area-scoping question (how to apply the new base styles to child screens only)
is left to the implementer's judgment -- this codebase's routing already distinguishes
child vs. parent routes (`/parent/*` prefix), so a CSS class on the root layout element per
route family, or a body-level class toggled by the router, are both reasonable; pick
whichever fits the existing `App.tsx` structure with the least new machinery.

## Verification

**Commands:**
- `cd frontend && npm run gen:api && npx tsc -b && npx eslint . && npm test -- --run` -- expected: pass
- `cd frontend && npm run build` -- expected: pass
- Manual: if a dev server can be started, visually check Home/Library/LessonDetail/Badges/a
  Session screen on both the child side and one Parent Area screen, confirming the Parent
  Area looks unchanged.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-10-03 -- initial implementation

Built per the Tasks & Acceptance checklist, in order:

- **`ChildTopBar`** (`frontend/src/components/ChildTopBar/ChildTopBar.tsx` + `.css` +
  `.test.tsx`, new): a thin presentational component -- `onBack: () => void` (required),
  `dots?: DotState[]`, `onSpeak?: () => void`. Renders a 64px (`--space-touch-min`) round ⬅
  button using the same chunky "physical button" treatment `HomeCard.css` already uses
  (`--radius-full`, `box-shadow: 0 4px 0 0 var(--color-surface-sunken)`, no shadow +
  `translateY(4px)` on `:active`), optional `ProgressDots` centred next to it, and an
  optional `SpeakerButton`. No routing/data-fetching of its own, per the Design Notes.
  5 tests cover: back button fires `onBack`; nothing extra renders when both optional props
  are omitted; dots render the right `done`/`current`/`todo` classes; an empty `dots` array
  renders no dots list; 🔊 fires `onSpeak` when provided.

- **Parent-Area CSS scoping (judgment call):** the spec's literal wording was "`index.css`'s
  `:root` font-family becomes `var(--font-body-family)`", but doing that literally would
  also repaint the Parent Area (nothing in the existing CSS overrides a `:root`/`body`
  font-family or background change for `/parent/*` screens) -- which directly violates this
  same story's "Parent Area must remain visually unchanged" constraint. Per the Design
  Notes' explicit permission to choose "a class on the root layout element per route family,
  or a body-level class toggled by the router", I added a `ChildShell` wrapper component in
  `frontend/src/App.tsx` (a one-line `<div className="child-shell">{children}</div>`) around
  every route element that is NOT under `/parent/*` (including `/setup`, `/exam/new`, and
  the `*` catch-all, since those are also child-facing/non-Parent) -- see `App.tsx`'s
  `routes` array. `frontend/src/index.css` then defines `.child-shell` with
  `font-family: var(--font-body-family)`, `color: var(--color-ink-primary)`,
  `background-color: var(--color-surface-base)`, `min-height: 100vh`, and leaves the
  original `:root`/`body` rule completely untouched, so the Parent Area keeps inheriting
  exactly what it always did. This was the smallest-diff option that fit the existing flat
  `routes` array (no nested-route/layout-route restructuring needed) and gives a single,
  easily-greppable toggle point.

- **`Library.tsx`, `LessonDetail.tsx`, `Badges.tsx`, `SessionPlayer.tsx`**: each page's
  bottom `<p className="parent-link"><Link>...</Link></p>` back-link is removed and
  `<ChildTopBar onBack={...} />` added at the top of every `<main>` the page can render
  (including loading/error early-return `<main>`s, not just the final success one -- a
  judgment call: the frozen matrix only describes the "loaded" case, but EXPERIENCE.md's
  "every child surface has one big ⬅ back button" doesn't carve out an exception for a
  loading spinner or an error message, and a child stuck on an error screen with literally
  no way back was already a latent gap this change fixes for free). Exact same navigation
  targets as the old links: Library/Badges -> `/`, LessonDetail/SessionPlayer -> `/library`.
  `Badges.tsx` gained a `useNavigate()` call it didn't need before (it previously only used
  `<Navigate>` for redirects).

- **`SessionPlayer.tsx`'s progress-dots gate**: moved `ProgressDots` out of the inline
  `(isQuiz || isExam) && <ProgressDots .../>` spot and into `ChildTopBar`'s `dots` prop. The
  new gate is `displayingProblem && problems.length > 1`, where `displayingProblem` mirrors
  the exact boolean chain the big content ternary already uses to reach the
  "actively playing a Problem" branch (not offline, has problems, not at exam/quiz/true-end,
  not chunk-done, profiles loaded) -- so dots never appear over a summary/results screen,
  matching today's behaviour of only showing dots while a Problem is live. This means a
  quiz/exam Session with only 1 Problem in its chunk NO LONGER shows dots (previously it
  always did, regardless of count, because the old gate only checked mode) -- this is the
  explicit, intended consequence of the frozen Boundaries' "more than one Problem in the
  current chunk" wording, not a missed regression.

- **Library lesson rows / Badges layout restyle**: `.library-lesson-row` (and the Concept
  tab's identical rows) now use `--radius-lg`, `--color-surface-raised`, and the same
  `box-shadow: 0 4px 0 0 var(--color-surface-sunken)` / `:active` press treatment as
  `HomeCard.css`, plus a small 📖 icon per row (`.library-lesson-icon`) echoing `HomeCard`'s
  icon slot. Book (`<h2>`) and Unit (`<h3>`) headers now use the `instruction`/`label`
  typography tokens instead of browser-default heading styles. `Badge` itself was already
  spec-correct (per the Intent), so `.badges-grid` only needed `justify-content: center` and
  a token-based margin -- no change to `Badge.tsx`/`Badge.css`.

- **Tests updated** (expected, deliberate changes per the frozen Boundaries, not
  regressions): `Badges.test.tsx`'s `getByRole('link', {name: 'Về trang chủ'})` ->
  `getByRole('button', {name: 'Quay lại'})`; `SessionPlayer.test.tsx`'s
  `getAllByText('Về Sách')` -> `getByRole('button', {name: 'Quay lại'})`, plus its single-
  Problem quiz test's dots assertion flipped from "1 list" to "no list" (see the gate note
  above), a new back-button-navigates-to-Library test, and a new multi-Problem practice-mode
  dots test (done/current/todo states). Added one back-button test each to
  `Library.test.tsx` and `LessonDetail.test.tsx`.

- **Out of scope, left untouched on purpose**: `ExamStart.tsx` also has a bottom "Về Sách"
  text link and is reached from Library, but it is not one of the 5 screens named in this
  story's frozen Intent/Code Map, so it was left as-is rather than silently expanding scope.
  Noting it here so a follow-up story can pick it up deliberately.

**Verification results:**
- `cd frontend && npx tsc -b` (run from a `/tmp` rsync copy per this environment's slow
  `/mnt/c` WSL filesystem, after `npm ci` there): clean, no errors.
- `npx eslint .` (same `/tmp` copy): clean, no errors or warnings.
- `npx vitest run` (same `/tmp` copy, with `backend/tests/fixtures` also rsynced over so
  `WorksheetPage.test.tsx`'s fixture reads resolve): 481 passed, 3 failed, across 52 test
  files. All 3 failures are in `ExtractionPage.test.tsx` (`cancels a run` and two others) --
  verified PRE-EXISTING and unrelated to this story by stashing all of this story's changes,
  re-running that same file in a clean `/tmp` copy, and confirming the identical 3 failures
  occur against baseline commit `82ede48` too. No test this story touched or added is among
  the failures.
- `cd frontend && npm run build` (real directory, not the `/tmp` copy): succeeds --
  `tsc -b && vite build` completes, emits `dist/` including the PWA service worker, only the
  pre-existing "chunk larger than 500kB" advisory warning (unrelated to this story).
  Confirmed the built CSS contains the expected
  `.child-shell{font-family:var(--font-body-family);...}` rule and the built JS references
  the `child-shell` class name.
- **Manual/visual check**: NOT performed in a real browser -- this environment has no
  browser-driving or screenshot capability available to me. The app is a client-rendered SPA
  (`createBrowserRouter`), so curling `dist/index.html` only shows an empty root div and
  proves nothing about rendered appearance; I verified the compiled CSS/JS artifacts
  directly instead (above). A human reviewer with a real browser should confirm the Parent
  Area (e.g. `/parent/dashboard`) still looks exactly as before, and that a child screen
  (e.g. `/library`) now shows the warm cream background, Nunito font, the new ⬅ top bar, and
  the restyled lesson-row cards, before this moves past `review`.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `ExamStart.tsx` (Story 8.1, the child's on-demand exam picker) still has the old bottom "Về Sách" text link -- it wasn't in this story's frozen Code Map's 5 screens (Home/Library/LessonDetail/Badges/SessionPlayer), so it was correctly left alone per scope, but it's now the one remaining child screen with the old pattern | low | self-disclosed by the implementer, confirmed by direct inspection -> no fix required under this story's frozen scope; logged here so a future pass (or a quick follow-up) picks it up rather than it being forgotten |
| 2 | `SessionPlayer.tsx`'s new `displayingProblem` constant duplicates (rather than reuses) the exact guard conditions the main render ternary further down the same function uses to reach the active-Problem view -- if that ternary's conditions change later without updating `displayingProblem` to match, the top bar's dots could silently show/hide incorrectly. Honestly flagged in the implementer's own code comment | low | confirmed by direct code read; a real but minor coupling risk, consistent with this codebase's practice of calling out unavoidable duplication explicitly rather than hiding it -> no fix required now; worth a follow-up refactor (e.g. deriving both from one shared boolean) if this function is touched again |
| 3 | No real-browser visual verification was possible (no browser-driving tool available to the implementer or this review) -- confirmed only via compiled CSS inspection (`.child-shell`/`.child-top-bar-back` rules present and correctly scoped in `dist/assets/*.css`, base `:root` font-family unchanged) and the full test suite | n/a | independently re-confirmed via the same compiled-output inspection approach -> genuinely open until a human (or a future session with real browser access) does a visual pass; not blocking given the CSS-level verification is solid, but flagged so it isn't mistaken for a completed visual QA step. |

Findings #1 and #2 require no code change (correctly scoped out / low-risk, honestly disclosed). Full frontend suite independently re-verified: `tsc -b`/`eslint` clean, all 70 tests across actually-touched files passing, production build succeeds with `.child-shell` confirmed present and `:root`'s base `system-ui` font-family confirmed unchanged (Parent Area unaffected) in the compiled CSS.

