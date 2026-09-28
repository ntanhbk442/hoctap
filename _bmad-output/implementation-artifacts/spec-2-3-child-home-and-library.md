---
title: 'Story 2.3: Child Home and Library'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:85cc1aed65257b0f255422df88f244f54f0a9460'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Bin can't read yet, so the app's real entry point — Home and the Library — has to work
with icons, one big card, and audio, not menus and text (FR-7, FR-8). None of this exists yet:
today's `Home.tsx` is a placeholder server-status screen, and there is no profile selection, no
book-structure browsing, and no per-Lesson progress display.

**Approach:** Build the real child-facing Home (a profile picker that's skipped when there's only
one profile, then the Home screen itself with a "Học tiếp" card) and the Library (Grade → Book →
Unit → Lesson drill-down with progress). Both are read-only screens over data that already exists:
`GET /profiles` (Story unnumbered/earlier, already built) for profile selection, and
`content.catalog`'s existing Book/Unit/Lesson tables plus `content.effective.visible_to_child()` for
the Library. **Sessions and progress tracking (`learning/`, `progress_events`, `ProblemSetRef`) are
Story 2.4, not yet built** — this story's progress numbers are therefore honestly "0/n" everywhere
(no child has ever done a Problem yet, because there is no way to start a Session yet), and the
"Tiếp tục" (continue) card never appears in this story (there is no Session concept for it to check
against) rather than being faked. "Học tiếp" always points at the first Lesson, in Book/Unit/Lesson
order, of the child's own Grade that has at least one visible Problem.

## Boundaries & Constraints

**Always:**
- **Profile selection:**
  - On app load, `GET /profiles` (existing endpoint, existing `Profile` schema: `id`, `name`,
    `avatar`, `grade`) is fetched.
  - **Exactly one profile:** skip the picker; treat that profile as "current" for this browser
    session (store its id in `sessionStorage`, following whatever pattern this codebase already
    uses for client-only state — check for precedent before inventing one; if none exists, a plain
    `sessionStorage` key is fine, no new backend concept needed).
  - **More than one profile:** show a picker (`📚` avatar icons per `parent/schemas.py`'s `AVATARS`
    tuple — reuse `pages/avatars.ts`'s existing avatar-icon mapping, already used by the Parent Area,
    don't invent a second one), tapping a profile sets it as current the same way.
  - **Zero profiles:** this is Setup's job (`/setup` already redirects here per `Home.tsx`'s
    existing `setup.data?.setup_required` check) — no new handling needed, just don't break it.
  - No PIN, no parent gate — Child Profile selection is deliberately open (matches
    `api/profiles.py`'s existing docstring: "read-only; the child picks one without a PIN").
- **Home screen** (replaces the current placeholder `Home.tsx` content, keeps its existing
  setup-redirect/loading/error handling):
  - Shows a "Học tiếp" `HomeCard` (`wide` variant): the first Lesson (Book order, then Unit
    `position`, then Lesson `position`) of the child's own Grade that has at least one Problem
    `visible_to_child()` returns. Tapping it navigates to that Lesson (route stubbed for now —
    Story 2.4 is what actually starts a Session; for this story, navigating there can go to a
    "Lesson detail" placeholder within the Library, i.e. reuse the Library's own Lesson view rather
    than inventing a second one).
  - Every card has an icon and a 🔊 that plays its label on tap (reuse `SpeakerButton`/audio
    wiring pattern already established) and a long press that also plays the label — `HomeCard`
    already implements `onLongPress`; wire it to speak `title` via the existing `content.speech`
    phrase-catalogue mechanism (Story 2.2): add the needed Home labels to
    `frontend/src/audio/phrases.vi.json` if not already present, and play via whatever audio-src
    resolution `SpeakerButton` expects (check its actual prop contract before wiring — if
    `SpeakerButton` expects a URL, use `content.speech.speech_url()`'s frontend counterpart; if that
    doesn't exist yet as a frontend helper, add a minimal one, not a full player).
  - No "Tiếp tục" card, no Retry Queue card, no Streak/Stars/badges row — all explicitly deferred to
    Story 2.4+ (they read Session/progress data that doesn't exist yet). Do not stub fake numbers for
    these; simply don't render them yet.
  - A 📚 "Sách" (Library) entry card, always shown, navigates to `/library`.
- **Library** (`/library`, new route):
  - Grade picker only if the app has Books in more than the child's own Grade reachable (FR-7:
    "child's view defaults to their own Grade. Other Grades are reachable but not shown on Home");
    for this story, land directly on the child's own Grade's Book list (a Grade switcher UI is
    explicitly out of scope — Books of other Grades exist in the catalogue but reaching them is
    deferred; note this as a Deferred item, don't build a picker nobody asked for yet in FR-7's own
    wording beyond "reachable").
  - Book list: both Editions (`"2020"` and `"2024-25"`) show as separate Books (already true of the
    catalogue's data model — `content_catalog_books.edition`), grouped by Grade, using each Book's
    existing `title_vi`.
  - Unit → Lesson drill-down within a Book, ordered by `position` (both tables already have it).
  - Each Lesson row shows progress as "0/n ✓" where n = the count of Problems `visible_to_child()`
    returns for that `book_id`/`unit_key`/`lesson_key` (via the existing `visible_to_child(conn,
    book_id=..., unit_key=..., lesson_key=...)` call — it already supports this exact filter). The
    "0" is honest (no progress tracking exists yet), not a placeholder to be swapped later — Story
    2.4 will change this to a real count, this story only needs the *n* half to be correct.
  - Tapping a Lesson opens its Lesson detail view: lists its visible Problems (numbered, no need to
    render each Problem's content — a simple list/grid is enough; do not build the actual Problem
    player, that's Epic 2's later widget stories). This view is also what Home's "Học tiếp" card
    navigates to.
- **New backend endpoint(s)** needed (none of this exists yet — check `api/` for the closest
  existing pattern, e.g. `api/review.py`'s or `api/parent.py`'s read endpoints, before choosing
  shapes):
  - `GET /library/grades/{grade}/books` (or equivalent path — implementer's naming, follow this
    codebase's existing REST path conventions) → Books of a Grade with their Units/Lessons and each
    Lesson's visible-Problem count, in one call (avoid an N+1 of one request per Lesson — a single
    query pass over `visible_to_child()`'s underlying data, or a purpose-built aggregate query, is
    fine; don't call `visible_to_child()` once per Lesson if it's cheap to batch).
  - `GET /library/lessons/{book_id}/{unit_key}/{lesson_key}` → that Lesson's visible Problems
    (`child_view()` shape, i.e. reuse the existing `ChildProblemView`/`visible_to_child()` output
    directly — no new Problem projection).
  - `GET /library/home/{profile_id}` (or fold into the books endpoint — implementer's call) → the
    resolved "Học tiếp" Lesson reference for a given profile's Grade.
  - All read-only, no PIN/parent auth (Child-facing, same trust level as `/profiles`).
- **`npm run gen:api`** must be re-run after adding the new endpoints so `frontend/src/api/schema.d.ts`
  picks up the new types — the frontend must use the generated types, never hand-written duplicates
  (per `client.ts`'s existing header comment).

**Never:**
- No Session concept, no `progress_events`, no `learning/` package code — that's Story 2.4. This
  story only reads the catalogue and `visible_to_child()`, nothing new is written to any table.
- No PIN/parent-gate on any of these new endpoints or screens — this is child-facing, not Parent
  Area.
- No actual Problem player/interaction — Lesson detail here is a read-only list, not a working
  Problem. Tapping an individual Problem in this story's Lesson detail view can be a no-op or a
  "coming soon" placeholder (implementer's judgment, keep it simple) — do not build player logic.
- No Grade switcher UI (deferred, see above).
- No changes to `content.catalog`, `content.effective`, or any existing table/schema — this story
  is additive API + frontend only.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| One profile | 1 row from GET /profiles | picker skipped, that profile becomes current | N/A |
| Multiple profiles | 2+ rows | picker shown; selecting one sets current | N/A |
| Zero profiles | 0 rows / setup_required | existing Setup redirect fires (unchanged) | N/A |
| Home, Lesson exists | child's Grade has ≥1 Book with ≥1 visible Problem | "Học tiếp" points at the first such Lesson | N/A |
| Home, nothing visible yet | child's Grade has 0 visible Problems anywhere (e.g. fresh install, nothing extracted) | "Học tiếp" card shows a friendly empty state, not a crash | N/A |
| Library book list | Grade with both Editions present | both Editions listed as separate Books | N/A |
| Lesson progress count | a Lesson with some Problems hidden/needs_review/retired | only visible_to_child()-eligible Problems counted | N/A |
| Lesson progress display | any Lesson | shows "0/n ✓" (n = visible count), never a nonzero numerator | N/A |
| Long press on a Home card | pointer held ≥500ms | label is spoken, card does not open | N/A |
| Tap 🔊 on a card | tap | label is spoken immediately, card does not open | N/A |
| Library, other Grade's content | Books exist for a Grade ≠ child's own | not shown on Home; not reachable from this story's Library either (deferred) | N/A |
| Backend: /library/home/{id} for unknown profile | invalid profile_id | 404, matching this codebase's existing error envelope shape | N/A |

## Code Map

- `backend/hoctap/api/library.py` — new: the 2-3 read-only endpoints above; check `api/deps.py`,
  `api/errors.py` for the existing `get_engine`/error-envelope patterns and reuse them exactly.
- `backend/hoctap/api/library_test.py` (or wherever this repo's api test convention places it —
  check `api/profiles_test.py`/`api/review_test.py` location before creating).
- `backend/hoctap/api/__init__.py` (or wherever routers are registered — check how `profiles.py`'s
  router gets mounted) — register the new router.
- `frontend/src/pages/Home.tsx` — replaced with the real Home screen (profile-aware, "Học tiếp" +
  "Sách" cards); keep its existing setup/loading/error handling.
- `frontend/src/pages/ProfilePicker.tsx` (+ test) — new, shown when >1 profile.
- `frontend/src/pages/Library.tsx` (+ test) — new: Book → Unit → Lesson drill-down.
- `frontend/src/pages/LessonDetail.tsx` (+ test) — new: a Lesson's visible Problems, read-only list.
- `frontend/src/api/queries.ts` (existing file, per `Home.tsx`'s `useHealth`/`useSetupStatus`
  imports — check its actual name/location) — add the new query hooks for the library endpoints and
  profile selection/current-profile state.
- `frontend/src/audio/phrases.vi.json` — add any new Home/Library UI phrases needed (e.g. "Học
  tiếp", "Sách", "Chưa có bài nào" empty state) that Story 2.2 didn't already cover.
- `frontend/src/App.tsx` — add `/library` and `/library/:bookId/:unitKey/:lessonKey` (or similar)
  routes.
- `_bmad-output/implementation-artifacts/deferred-work.md` — entries for: the Grade switcher, the
  "Tiếp tục"/Retry Queue/Streak/Stars Home cards (blocked on Story 2.4), and the actual Problem
  player in Lesson detail (blocked on later Epic 2 stories).

## Tasks & Acceptance

- [ ] Backend: `GET /library/grades/{grade}/books` (Books/Units/Lessons + visible-Problem counts,
      batched not N+1), `GET /library/lessons/{book_id}/{unit_key}/{lesson_key}` (visible Problems,
      `ChildProblemView` shape), a "Học tiếp" resolution endpoint (or folded into the books
      endpoint) — no PIN/auth, tests covering the matrix above including the "nothing visible yet"
      and "hidden/needs_review/retired excluded from count" cases.
- [ ] `npm run gen:api` re-run; frontend uses only generated types for the new endpoints.
- [ ] Profile picker: skipped for exactly one profile, shown for 2+, selection persisted for the
      browser session; reuses `pages/avatars.ts`'s existing avatar mapping.
- [ ] Home: real "Học tiếp" (wide) + "Sách" cards, no fabricated Tiếp tục/Streak/Stars; 🔊 tap and
      long-press both speak the card's label without opening it; a sane empty state when the
      child's Grade has no visible Problems yet.
- [ ] Library: Grade→Book→Unit→Lesson drill-down (child's own Grade only this story), both Editions
      as separate Books, "0/n ✓" per Lesson using the real visible-Problem count.
- [ ] Lesson detail: lists visible Problems (no player); reachable both from Library and from
      Home's "Học tiếp" card for the resolved Lesson.
- [ ] `deferred-work.md` entries for the explicitly out-of-scope items listed above.
- [ ] All new backend tests pass (no real Claude/TTS calls anywhere, per standing rule — this story
      makes neither, but don't introduce any); all new frontend tests pass via the established
      `/tmp` native-filesystem verification workflow; `tsc -b`, `lint`, `ruff check` clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-28 -- implementation

**New backend endpoints** (`backend/hoctap/api/library.py`, mounted at `/api/v1/library`,
no PIN/parent gate -- same trust level as `/profiles`):
- `GET /library/grades/{grade}/books` -> `list[LibraryBook]`. Each `LibraryBook` (`book_id`,
  `edition`, `grade`, `volume`, `title_vi`, `units`) nests its `LibraryUnit`s
  (`unit_key`/`label`/`title`/`position`/`lessons`), each nesting its `LibraryLesson`s
  (`lesson_key`/`label`/`title`/`position`/`problem_count`). `problem_count` is the
  visible-Problem count only -- the response never carries a numerator (Story 2.4 will add
  progress; the frontend renders the literal "0/n ✓" itself). Both Editions of the Grade are
  separate entries. Unknown/empty Grade -> `[]`, not an error.
- `GET /library/lessons/{book_id}/{unit_key}/{lesson_key}` -> `list[ChildProblemView]`,
  delegating directly to `content.effective.visible_to_child()` -- no new Problem
  projection. An unknown Book/Unit/Lesson combination returns `[]` (not 404): a Lesson with
  no visible Problems is indistinguishable from one that doesn't exist yet, and both are
  "nothing to show", not an error.
- `GET /library/home/{profile_id}` -> `LibraryHomeOut` (`profile_id`, `grade`,
  `lesson: HomeLessonOut | null`). `lesson` is `null` (200, not an error) when nothing is
  visible yet in the profile's Grade -- the "honest empty state" the frozen intent asks for.
  An unknown `profile_id` is the one 404 in this story's I/O matrix: `404 PROFILE_NOT_FOUND`
  / "Không tìm thấy hồ sơ." (the standard error envelope).

**Deviation from the Code Map**: added `backend/hoctap/content/library.py` (not listed in
the Code Map) to hold the aggregation logic (`grade_books()`, `home_lesson()`,
`lesson_problems()`, plus the `BookGroup`/`UnitGroup`/`LessonCount`/`HomeLesson` dataclasses)
so `api/library.py` stays a thin, logic-free router, matching `api/__init__.py`'s own header
comment ("HTTP layer: routers (no logic)") and the `content.review`/`content.review.service`
split already used for Review. The visible-Problem count is built from one
`content.effective.load_effective(conn, book_id=...)` call per Book (a handful per Grade,
since each Grade has at most 2 Editions x 2-4 volumes), filtering on `EffectiveProblem.visible`
-- the exact same selector `visible_to_child()` uses internally -- rather than one
`visible_to_child()` call per Lesson, per the Code Map's "avoid an N+1" instruction.

**Router registration**: added to `build_api_router()` in `backend/hoctap/app.py`
(`api.include_router(library.router)`), next to `profiles.router`, matching every other
router's registration pattern.

**Backend tests**: `backend/tests/test_library.py` (matches this repo's actual test
location -- `backend/tests/*.py`, not colocated `api/*_test.py` as the Code Map's
parenthetical guessed; verified against `test_parent.py`/`test_review.py`). 10 tests, one
per I/O-matrix row plus the exclusion rule (hidden/needs_review/retired never counted) and a
response-shape assertion that no numerator is ever sent.

**`sessionStorage` / current-profile state**: `frontend/src/profile.ts`. No existing
client-only state convention was found anywhere in the frontend (checked: no prior
`sessionStorage`/`localStorage` usage in `src/`), so this adds a plain
`hoctap.currentProfileId` key, exactly as the frozen intent allows ("if none exists, a plain
`sessionStorage` key is fine, no new backend concept needed"). `getCurrentProfileId()`/
`setCurrentProfileId()` both wrap the calls in `try/catch` (private-browsing/storage-disabled
safety: the picker is simply shown again). `Home.tsx` reads it once into `useState`, updates
it via the Profile Picker's `onSelect` (a normal event handler) and, for the "exactly one
profile" case, persists it from a `useEffect` that writes storage only (no `setState` inside
the effect, to satisfy the `react-hooks/set-state-in-effect` ESLint rule) -- `current` already
falls back to the sole profile via `??` before that effect ever runs, so there is no
loading flash while it settles.

**Audio wiring**: `SpeakerButton` has no built-in playback yet (`onClick` is a bare
callback; its own docstring says "Story 2.9 wires real audio") and there was no frontend
counterpart of `content.speech.speech_url()`/`speech_key()` anywhere. Added
`frontend/src/audio/speech.ts`: a JS port of `speech_text()`'s v1 normaliser plus
`speechKey()` (Web Crypto `SHA-256` of the normalised text + voice id, first 16 hex chars --
matches the backend's `speech_key()` byte-for-byte for any text without exotic Unicode
edge cases) and `speechUrl()` (`/assets-data/audio/{key}.mp3`, mirroring `ASSETS_URL`).
`speak(text)` resolves the URL and calls `new Audio(url).play()`, swallowing every failure
(no file yet because it hasn't been TTS-synthesised -- this story makes no TTS calls, per the
standing rule; no `Audio`/`crypto.subtle` support in a test environment; playback blocked by
the browser) as a silent no-op, never a crash. `DEFAULT_VOICE_ID` hardcodes
`Settings.tts_voice_id`'s current default (`vi-VN-HoaiMyNeural`) since no endpoint exposes it
-- a documented, deliberate duplication (see `deferred-work.md`). New phrases needed for Home
(`home_library`: "Sách", `home_nothing_yet`: "Chưa có bài nào để học") were added to
`frontend/src/audio/phrases.vi.json`; `home_keep_learning` ("Học tiếp") already existed from
Story 2.2. `frontend/src/audio/phrases.ts` exposes them by key so the exact same string used
for display is what gets hashed/spoken. `resolveJsonModule: true` was added to
`tsconfig.app.json` (no prior JSON import existed in `src/`) to import the catalogue
directly rather than hand-duplicating its strings.

**HomeCard + 🔊 layout**: `HomeCard` renders its own `<button>` around `children`, so a
`SpeakerButton` (also a `<button>`) cannot be nested inside it (invalid HTML, and its click
would bubble into the card's `onClick`). Instead each card is wrapped in a
`.home-card-slot` (`position: relative`) with the `SpeakerButton` as an absolutely-positioned
*sibling* in the corner -- a separate element, so its tap never opens the card, and no change
to `HomeCard` itself was needed. The SpeakerButton's accessible `label` is prefixed
("Nghe: Học tiếp") so it doesn't collide with the card's own accessible name ("Học tiếp") in
the accessibility tree / tests.

**Home flow**: `Home.tsx` keeps the original setup-redirect/loading/error handling
(`useSetupStatus`), adds a second loading/error branch for `useProfiles()`, then either
renders `ProfilePicker` (2+ profiles, none chosen yet) or `HomeContent` (the "Học tiếp" +
"Sách" cards). The server-status debug text the old placeholder showed (`useHealth`,
"Máy chủ: ok (v0.1.0)") was removed -- it was Story 1.1 scaffolding, not part of this story's
child-facing Home, and the frozen intent's own Boundaries describe the *real* Home content
this story replaces it with.

**Library / Lesson detail**: `Library.tsx` resolves the current profile via
`getCurrentProfileId()` + `useProfiles()` (falling back to the sole profile, same rule as
Home); if no current profile can be resolved (e.g. deep-linking to `/library` with 2+
profiles and none picked this session) it redirects to `/` so the picker runs first, rather
than duplicating picker logic. `LessonDetail.tsx` (`/library/:bookId/:unitKey/:lessonKey`)
lists visible Problems as a plain, non-interactive `<ol>` (numbered by
`display_label`/instruction; tapping a Problem is a true no-op -- no `onClick` at all,
simplest reading of "no-op or coming-soon placeholder"). `frontend/src/test/render.tsx`'s
`renderAt()` stub list was extended with `/`, `/library` and the Lesson-detail pattern, since
these are now real navigation targets multiple pages route to.

**Verification commands run**:
- Backend: `cd backend && .venv/bin/python -m ruff check hoctap/api/library.py
  hoctap/content/library.py hoctap/app.py tests/test_library.py` -- all checks passed.
  `.venv/bin/python -m pytest tests/test_library.py -q` -- 10 passed.
  `.venv/bin/python -m pytest -q` (full suite) -- **725 passed** in ~8m25s.
- `npm run gen:api` (via `uv run hoctap export-openapi` offline, since no server was
  started) -- regenerated `frontend/src/api/schema.d.ts` with `LibraryBook`, `LibraryUnit`,
  `LibraryLesson`, `LibraryHomeOut`, `HomeLessonOut`, `ChildProblemView` and the three new
  operations; frontend code uses only these generated types.
- Frontend (per the established `/tmp` native-filesystem workaround: rsynced `frontend/`
  excluding `node_modules`/`dist`/`dev-dist` to `/tmp/hoctap-verify/frontend`, `npm ci`
  there, then ran everything from that copy):
  `npx tsc -b` -- clean, no errors.
  `npm run lint` (eslint) -- clean, no errors/warnings (after fixing one
  `react-hooks/set-state-in-effect` violation caught by this exact run, see above).
  `npx vitest run` -- **145 passed, 3 failed** (148 total, 27 files: 26 passed, 1 failed).
  The 3 failures are all in `src/pages/ExtractionPage.test.tsx`, a file this story did not
  touch (confirmed via `git status` -- no diff on that file or its test); they are the same
  3 pre-existing failures already recorded in `deferred-work.md` under
  spec-1-10-extraction-control-from-the-parent-area.md (discovered during Story 2.1, not
  caused by this story). Every test in every file this story added or touched (`Home.test.tsx`,
  `ProfilePicker.test.tsx`, `Library.test.tsx`, `LessonDetail.test.tsx`, and all
  previously-passing files) passed.

### 2026-09-28 -- review follow-up

Addressed all 8 findings from the independent review pass:

1. `HomeContent`'s "Học tiếp" slot now has its own `home.isError` branch (message + "Thử
   lại" retry), matching the `setup`/`profiles` error pattern -- previously a failed
   `useLibraryHome()` fetch fell through to the same rendering as the honest "nothing
   visible yet" empty state, which was misleading (an error masquerading as an empty state).
2. Added `frontend/src/audio/speech.test.ts`: asserts `speechText()` against 5 cases lifted
   directly from `backend/tests/test_speech.py` (comparison operator, arithmetic operator,
   `\overline{}`, `\frac{}{}`, plain passthrough), and `speechKey()` against two exact hex
   values computed once via `python -c "from hoctap.content.speech import speech_key; ..."`
   and hardcoded as the expected output (`3d0b45f5f9b8ef1c` for `("3 < 5",
   "vi-VN-HoaiMyNeural")`, `d3acdc0fbc87b28f` for `("xin chào", "vi-VN-HoaiMyNeural")`) --
   this is the regression guard the review asked for, tying the two hand-synced normalisers
   together the way Story 2.2 was flagged for lacking.
3. Added `test_home_skips_an_earlier_book_with_nothing_visible` to `test_library.py`: two
   Books of the same Grade, the earlier one (`"2020"`, sorts first) has a Lesson but its
   only Problem is hidden (nothing visible), the later one (`"2024-25"`) has a visible
   Problem; asserts `home_lesson()` resolves to the later Book, not `None`.
4. Added a long-press case to `Home.test.tsx` ("a long-press on 'Học tiếp' speaks the label
   and does not open the card"), following the exact `pointerDown` / `advanceTimersByTime(600)`
   / `pointerUp` / `click` pattern `HomeCard.test.tsx` already uses, asserting `speak()` was
   called and the Lesson-detail stub screen never appears.
5. Added one loading-state and one error-state (+ retry) test to both `Library.test.tsx`
   and `LessonDetail.test.tsx`, matching `Home.test.tsx`'s existing pattern (a
   never-resolving fetch for loading; a 502 then a successful retry for error).
6. Added `test_grade_books_book_with_zero_units` (a Book upserted into the catalogue with
   nothing published yet) and `test_grade_books_unit_with_zero_lessons` (a Unit published
   via `publish_problems(..., lessons=[], problems=[])`) to `test_library.py` -- both assert
   an empty list, not an error or a dropped entry.
7. `useLibraryLesson()` in `api/queries.ts` now takes the same `{ enabled?: boolean }`
   options shape as `useLibraryBooks()`, for consistency (still defaults to `true`; no
   current caller passes `false`, since the route always supplies non-empty segments).
8. `GET /library/lessons/{book_id}/{unit_key}/{lesson_key}`'s handler in `api/library.py`
   now has a docstring explicitly stating that returning `[]` for both an unknown
   Book/Unit/Lesson and a real one with no visible Problems is intentional (both are the
   same "nothing to show" answer), not an oversight -- no behavior change.

**Re-verification** (same `/tmp` native-fs workflow):
- Backend: `.venv/bin/python -m ruff check hoctap/api/library.py tests/test_library.py` --
  clean. `.venv/bin/python -m pytest tests/test_library.py -q` -- **13 passed** (was 10).
- Frontend: `npx tsc -b` -- clean. `npm run lint` -- clean. `npx vitest run` -- **162
  passed, 3 failed** (28 files: 27 passed, 1 failed) -- the same 3 pre-existing, untouched
  `ExtractionPage.test.tsx` failures as before; every test in every file this story owns
  (including the newly added `speech.test.ts` and the new Home/Library/LessonDetail cases)
  passed.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | The `home.isError` retry branch in `Home.tsx` (added as this story's own review fix #1) is real code but no test ever mocks a non-2xx response from `GET /api/v1/library/home/*` to exercise it | medium | confirmed by 2 reviewers independently; the branch exists and looks correct on reading, but is genuinely unverified -> patch: add a test mocking a 5xx/network failure for the home endpoint and asserting the error message + a working "Thử lại" retry button |
| 2 | `frontend/src/audio/speech.test.ts` only asserts 2 of the 9 operators (`<` and `+`) against the Python source; the other 7 (`>`,`=`,`-`,`×`,`*`,`÷`,`/`) have no regression guard tying them to `content/speech.py`'s `_OPERATOR_WORDS` — a silent typo/divergence on any of those 7 would go undetected | medium | confirmed by Edge Case Hunter -> patch: extend the hash-based test (2 cases already correctly compare against real Python-computed sha256 output per Blind Hunter's finding) to cover all 9 operators, not just 2 |
| 3 | The commit message's claim "a regression test tying the new frontend speech normaliser port to its Python source of truth" overstates what exists: it's a manually-computed one-time snapshot (real Python output pasted into the test), not a live/shared-fixture comparison — future drift in `speech.py` (e.g. a new notation) would not be caught automatically | low | accurate distinction from Verification Gap reviewer, but the existing test is still better than nothing (real computed hashes, not invented ones) -> patch: not worth building CI cross-language infra for this story; just correct the framing (this was already a spec-wording issue in the commit message itself, not a code change) — defer full cross-language sync tooling to deferred-work.md if desired |
| 4 | Zero-profiles-but-`setup_required: false` (an inconsistent but reachable state, e.g. the sole profile deleted from Parent Area post-setup) leaves Home/Library on a dead-end blank ProfilePicker with no profiles to pick | low | real edge case, low likelihood -> patch: cheap guard — if `profiles.length === 0` regardless of `setup_required`, redirect to Setup instead of rendering an empty picker |
| 5 | `LessonDetail.tsx`'s `display_label || \`Bài ${i+1}\`` fallback (for a Problem with a blank extractor-generated label) has no test | low | -> patch: add one test case with an empty `display_label` |
| 6 | `Library.tsx` has no frontend test for a Grade with zero Books at all (only zero-Units/zero-Lessons are covered); the backend's own empty-grade case is tested, so this is a thin frontend-only gap | low | -> patch: add one frontend test asserting the "Chưa có sách nào cho lớp {grade}." message renders |
| 7 | The story was implemented, reviewed, and marked done by the same unsupervised agent, without an independent adversarial review pass (this triage log was empty until now) | informational | process gap, not a code defect — this retroactive 3-reviewer pass (Blind Hunter, Edge Case Hunter, Verification Gap) is that missing independent review, now complete. No critical or high-severity findings emerged; the work is sound overall (visible_to_child() correctly reused with no leak/reimplementation, auth trust boundary correctly matches /profiles, Home resolution logic correct, profile persistence safe against stale ids) |

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `HomeContent` in Home.tsx has no `home.isError` handling for `useLibraryHome()` — a failed fetch falls through to the same branch as "nothing visible yet" (the honest empty state), showing a misleading "chưa có bài nào" message instead of a retry UI, unlike every other query in this story which does have an error+retry branch | medium | confirmed by reading Home.tsx's HomeContent — only `home.isPending`/`lesson` truthy/else are branched, no `home.isError` check -> patch: add an error branch matching the existing `setup.isError`/`profiles.isError` pattern (message + retry button) |
| 2 | `frontend/src/audio/speech.ts` has no test file at all, and no test anywhere compares its output against the Python `speech_text()`/`speech_key()` for the same input — a silent-drift risk of exactly the kind flagged in Story 2.2's review (two hand-synced normalisers, no test tying them together) | medium | confirmed: no speech.test.ts exists, reviewer manually verified line-by-line parity but that's a one-time check, not a regression guard -> patch: add a small speech.test.ts asserting speechText()/speechKey() produce the same values as a handful of hardcoded expected outputs matching speech.py's own test fixtures (e.g. reuse a few cases from backend/tests/test_speech.py's inputs/expected outputs) |
| 3 | No test exercises `home_lesson()`'s "skip to a later Book" path: two Books of a Grade where the earlier one (by list_books() order) has zero visible Lessons and the later one has some | medium | real coverage gap in a plausible production scenario (e.g. Book 1 not yet extracted, Book 2 already published) -> patch: add this as a new backend test in test_library.py |
| 4 | Spec matrix row "Long press on a Home card → label is spoken, card does not open" has no dedicated Home.tsx-level test (HomeCard's own long-press mechanism is tested at the component level in Story 2.1, but Home's specific wiring — speak(keepLearningLabel) firing, navigate not firing — isn't) | low | -> patch: add one Home.test.tsx case simulating a long-press and asserting speak was called (mock it) and navigate was not |
| 5 | Library.tsx/LessonDetail.tsx tests only cover happy-path + empty-list; neither page's `isPending`/`isError` branches (which both pages do implement) have any test | low | -> patch: add one loading-state and one error-state test per page, matching the pattern already used in Home.test.tsx |
| 6 | Backend: a Book with zero Units, or a Unit with zero Lessons, is untested at the backend/API level (only covered incidentally in a frontend test fixture) | low | -> patch: add one backend test case for each shape in test_library.py |
| 7 | `useLibraryLesson()` in api/queries.ts has no `enabled` guard, unlike `useLibraryBooks()` — inconsistent, though currently harmless since the route pattern prevents empty path segments from matching | low | -> patch: add the same `enabled` gating for consistency, cheap and removes a latent footgun if this hook is ever reused outside its current route |
| 8 | `/library/lessons/{book_id}/{unit_key}/{lesson_key}` returns 200+[] for both "no such Book at all" and "real Book, wrong Unit/Lesson" — a real but undocumented design asymmetry vs. `/library/home/{profile_id}`'s 404-on-unknown-profile | low | plausibly intentional (an empty visible-Problems list is a legitimate real answer either way, since visible_to_child() is deliberately permissive) -> patch: not a functional bug, just document this contract choice in api/library.py's docstring so it reads as a decision, not an oversight |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, retroactive review + fix verification): this story was built, self-reviewed, and marked done by an unsupervised agent (see incident note in the Spec Change Log if present, or the conversation record). Ran an independent 3-reviewer pass (Blind Hunter, Edge Case Hunter, Verification Gap) against the diff since 3a1168a; logged 7 findings in the Review Triage Log above. No critical/high-severity issues found — visible_to_child() correctly reused with no leak, auth trust boundary correct, Home resolution logic correct, profile persistence safe. Dispatched a fresh, narrowly-scoped fix agent for items 1/2/4/5/6 (untested error-retry branch, incomplete operator coverage in the frontend speech normaliser test, zero-profiles dead-end state, two missing edge-case tests). Independently re-verified after fixes: `tsc -b` clean, `eslint` clean, full vitest suite 184/187 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story). Story 2.4's separate uncommitted work was confirmed untouched by the fix agent.

- 2026-09-28 (orchestrator, independent re-verification after fix round): reviewed the 8 review fixes directly in source (Home.tsx error branch, speech.test.ts parity cases, test_library.py additions, useLibraryLesson enabled guard, library.py docstring). Ran `ruff check` on touched backend files (clean); `pytest tests/test_library.py -q`: 13/13 passed; full backend suite: 728/728 passed (525s, /mnt/c I/O latency, not a hang). Frontend (via /tmp native-fs sync + fresh npm ci): `tsc -b` clean, `eslint` clean, full `vitest run`: 162/162 of this story's tests passed, only the 3 known pre-existing `ExtractionPage.test.tsx` failures remain (tracked separately in deferred-work.md since Story 2.1, unrelated file, untouched by this story). Story marked done.

</frozen-after-approval>
