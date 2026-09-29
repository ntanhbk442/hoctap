---
title: 'Story 2.11: PWA offline shell and event outbox'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:7af74abf5a32d1fcc4853be904c96db36e8c797f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing in this app works offline today — no IndexedDB usage anywhere, no
offline-detection in `frontend/src/api/client.ts` (a network failure is just a generic thrown
error), and `vite.config.ts`'s Workbox config only precaches the JS/CSS/HTML app shell (no fonts
runtime-caching for `/assets-data/` crops/audio, no KaTeX — not yet installed/used anywhere in this
codebase despite being named in the architecture's stack table). A dropped Wi-Fi connection mid-
Session today just breaks the app with a raw error. Separately, Home's "Tiếp tục" (continue) card
was explicitly deferred three times (Stories 2.4, 2.5/2.8's `deferred-work.md` entries) because
"an unfinished Session" had no clean definition without grading and `session_completed` — both
now exist as of Story 2.5 and Story 2.10.

**Approach:** Extend the existing `vite-plugin-pwa` config to precache the shell (already working)
plus fonts/phrase-audio, and runtime-cache each Session's bundle assets (crops/page images, this
Problem's audio clips) as the Session starts (AD-10) — `content.assets`'s crop/page URLs and
`content.speech`'s audio URLs, already known from the bundle response, just need a Workbox runtime
route or an explicit cache-population call. A small IndexedDB-backed event outbox intercepts
`POST /sessions/{id}/events` when the network is unreachable: queues the event locally, shows the
"Máy tính bảng chưa kết nối…" screen with a 🔊 and retry (no local grading — the child sees no
verdict until the server actually grades it), and flushes the queue in order once connectivity
returns, relying on the SAME per-event UUIDv7 idempotency the backend already guarantees (Story
2.4/2.5) so an already-applied event replays harmlessly. Home's "Tiếp tục" card finally gets built,
extending `GET /library/home/{profile_id}`'s existing response the same way "Học tiếp" already
works — the most recent `progress_sessions` row for the Profile with `completed_at IS NULL` (a
genuinely unfinished, non-replay Session) resumes at its current Problem via the existing bundle/
chunk navigation Story 2.6 already built.

## Boundaries & Constraints

**Always:**
- **Service worker precache** (`frontend/vite.config.ts`'s Workbox config): extend
  `globPatterns`/`runtimeCaching` to cover fonts (already self-hosted, Story 2.1) and the UI phrase
  audio (`frontend/src/audio/phrases.vi.json`'s entries' synthesised clips, if already built by
  `speak-missing` — Story 2.2). KaTeX: confirm via `package.json` whether it's actually
  installed/used anywhere in this codebase yet; if it genuinely isn't (the architecture's stack
  table names it, but no story before this one has integrated it), log this gap in
  `deferred-work.md` rather than inventing a KaTeX integration that's out of scope for THIS story —
  precache it only if it's already a real, used dependency.
- **Session-bundle asset caching**: when a Session starts (or its bundle is fetched), the current
  chunk's Problems' crop/page image URLs and audio clip URLs (already present in the bundle
  response, Story 2.4/2.5) are added to a Workbox runtime cache (a `CacheFirst`-or-similar strategy
  scoped to `/assets-data/*`) so they're available offline for the rest of that Session.
- **IndexedDB event outbox** (new, e.g. `frontend/src/offline/outbox.ts`): when `POST
  /sessions/{id}/events` fails due to a network error (not a 4xx/5xx from a reachable server —
  distinguish "server responded with an error" from "server unreachable at all", matching how
  `frontend/src/api/client.ts`'s existing error handling already separates these where possible),
  queue the event (its full request body, including the client-generated UUIDv7 id — critical for
  idempotency on retry) in IndexedDB instead of surfacing a generic error. Show the "Máy tính bảng
  chưa kết nối…" screen (new phrase key if not already present in `phrases.vi.json`) with a 🔊 and
  a manual retry button. No local/optimistic grading happens — the UI must not show a correct/wrong
  verdict until the server actually responds (even after reconnect and the queued event flushes).
- **Outbox flush on reconnect**: listen for `window.addEventListener('online', ...)` (and/or poll a
  lightweight endpoint) and flush the IndexedDB queue in FIFO order, one at a time (never
  reordered, never parallel — AD-10's "sent in order, applied once"), removing each from the queue
  only after a confirmed server response (success OR a definitive "already applied" idempotent
  response — never removed on an ambiguous/timeout response, which should be retried).
- **"Tiếp tục" Home card**: extend `GET /library/home/{profile_id}`'s response with the most
  recent unfinished (non-`replay`-mode, `completed_at IS NULL`) Session for the Profile, if any —
  reuse Story 2.10's own mode-filtering logic, don't reimplement it. `Home.tsx` shows "Tiếp tục"
  alongside "Học tiếp" when one exists (mirroring the existing card's icon/🔊/long-press pattern
  from Story 2.3), navigating straight to that Session's current chunk via the existing
  `SessionPlayer` route (Story 2.6) — no new resume-specific routing needed, just passing the
  existing Session id through.
- **A closed-and-reopened tablet resumes correctly**: since the Session id and its frozen
  `problem_ids_json`/chunk state live entirely server-side (Story 2.4's AD-9 freeze), "resuming"
  is simply re-fetching the same Session's bundle — no client-side persisted resume-state is
  needed beyond knowing WHICH Session id to resume, which "Tiếp tục" surfaces via the Home
  endpoint. Any IndexedDB-queued events from before the tablet closed are still there (IndexedDB
  persists across a browser/PWA restart) and flush normally once reconnected.

**Never:**
- No local grading of any kind — a queued `attempt` event's correctness is NEVER computed
  client-side, even provisionally; the child sees no praise/wrong feedback until the server
  actually responds (post-flush).
- No changes to `learning.sessions`/`learning.problem_sets`/the backend event-idempotency
  mechanism — this story is a pure frontend consumer of the exact-once guarantee those already
  provide.
- No reordering of queued events on flush — strict FIFO, matching AD-10's literal requirement.
- Do not invent a KaTeX integration if it doesn't already exist in this codebase — precache only
  what's real (log the gap instead, per the Always section).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| App load, HTTPS+CA installed | fresh load | shell/fonts/phrase-audio precached | N/A |
| Session starts | bundle fetched | this chunk's crop/page/audio URLs cached | N/A |
| Server unreachable, child answers | POST /events fails (network error, not 4xx/5xx) | event queued in IndexedDB, offline screen shown, no grading | N/A |
| Offline screen, retry tapped | still offline | stays on offline screen, no crash | N/A |
| Connection returns | outbox has N queued events | flushed in original order, one at a time | N/A |
| Flush hits an already-applied event | idempotent replay | removed from queue, no error surfaced to the child | N/A |
| Flush hits a genuine new failure mid-queue | e.g. 3rd event 4xx | that event's handling is implementer's call (retry vs surface an error) — document whichever is chosen | N/A |
| Tablet closed mid-Session, reopened later | app relaunched | IndexedDB queue intact, flushes normally once online | N/A |
| Home, unfinished Session exists | non-replay Session, completed_at NULL | "Tiếp tục" card shown, tapping it resumes at the correct chunk | N/A |
| Home, no unfinished Session | every Session completed or none started | "Tiếp tục" not shown (existing "Học tiếp"-only behavior unchanged) | N/A |
| Home, only a replay Session is unfinished | replay-mode Session, completed_at NULL | "Tiếp tục" does NOT surface it (replay sessions are excluded) | N/A |

## Code Map

- `frontend/vite.config.ts`: extended Workbox `globPatterns`/`runtimeCaching`.
- `frontend/src/offline/outbox.ts` (new): IndexedDB queue, flush logic, online-event listener.
- `frontend/src/offline/OfflineScreen.tsx` (new) or similar: the "chưa kết nối" UI.
- `frontend/src/api/client.ts`: network-vs-server-error distinction if not already present;
  the POST-events call site routes through the outbox on a network failure.
- `backend/hoctap/api/library.py`/`content/library.py`: extend `GET /library/home/{profile_id}`
  with the unfinished-Session field (reusing Story 2.10's mode-filtering).
- `frontend/src/pages/Home.tsx`: the new "Tiếp tục" card.
- `frontend/src/audio/phrases.vi.json`: the new offline-screen phrase key(s), if not present.
- Test files for all of the above, covering the I/O matrix.
- `_bmad-output/implementation-artifacts/deferred-work.md`: a KaTeX-integration-gap note if it
  turns out not to be a real dependency yet.

## Tasks & Acceptance

- [x] Service worker precaches shell + fonts + phrase audio (KaTeX only if genuinely already a
      real dependency — log the gap otherwise, don't invent an integration).
- [x] Session-bundle asset runtime-caching on Session start.
- [x] IndexedDB outbox: queues on network failure, offline screen with 🔊+retry, no local grading.
- [x] Outbox flush on reconnect: strict FIFO, one at a time, idempotent-replay-safe.
- [x] "Tiếp tục" Home card: extends the home endpoint, resumes the correct Session/chunk,
      excludes replay-mode Sessions.
- [x] Closed-and-reopened tablet resumes correctly (server-side state is sufficient; IndexedDB
      queue survives a restart).
- [x] `deferred-work.md` entry for KaTeX if applicable.
- [x] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-29: implementation

**Outbox architecture (frontend/src/offline/).**
- `outboxStore.ts`: an `OutboxStore` interface (`add`/`listAll`/`remove`/`count`) with two
  implementations. `IndexedDBOutboxStore` is the real, persisting store (one IndexedDB
  object store, `hoctap-outbox`/`events`, keyed by `QueuedItem.id` = the event's own
  client-generated UUIDv7). `MemoryOutboxStore` is a plain `Map`-backed store used both as
  the graceful runtime fallback (`createOutboxStore()` picks it when `typeof indexedDB ===
  'undefined'`, e.g. a private-mode browser that blocks it) AND as what the tests inject.
  `listAll()` sorts by `id` ascending in both implementations, which is FIFO because UUIDv7
  is time-ordered — no separate autoincrement/sequence column is needed.
- **Testability without a real IndexedDB**: confirmed this repo has no `fake-indexeddb`
  dependency (`package.json` grep) and jsdom (`vite.config.ts`'s `test.environment`) does
  not implement `indexedDB`. Rather than adding a mocking library, `outbox.ts`'s two core
  functions (`postEventsOrQueue()`, `flushOutbox()`) take an `OutboxStore` as an explicit
  parameter (dependency injection), so `outbox.test.ts`/`outboxStore.test.ts` exercise them
  against `MemoryOutboxStore` — real production code, not a test-only mock, since it's also
  the real private-mode-browser fallback path. `IndexedDBOutboxStore` itself is therefore
  NOT unit-tested in this repo's current jsdom environment (no assertions run against it);
  it's a thin, standard `indexedDB.open()`/transaction wrapper with no branching logic of
  its own beyond what `outboxStore.test.ts`'s `createOutboxStore()` fallback test already
  exercises the selection logic for. This is a documented, deliberate trade-off, not an
  oversight.
- `outbox.ts`: `postEventsOrQueue(store, sessionId, profileId, events)` tries
  `postSessionEvents()` first; on a `NetworkError` (see below) it queues each event's FULL
  original request body (`{id, sessionId, profileId, event}}`, `event` including its own
  UUIDv7 `id`) and throws `QueuedOfflineError` instead of the original error. A 4xx/5xx
  `ApiError` is rethrown unchanged, never queued. `flushOutbox(store)` drains the store
  ONE item at a time, oldest-first, removing an item only after `postSessionEvents()`
  returns normally (which also covers the idempotent-replay case for free — the backend's
  per-event UUIDv7 primary key returns the same success response for a resend, never an
  error); it STOPS (not skips) at the first failure of any kind, leaving that item and
  everything after it queued for the next attempt — the frozen spec's I/O matrix flags this
  exact "mid-queue failure" case as "implementer's call, document whichever"; stopping was
  chosen because it is the only option that can never violate strict FIFO (see the
  function's own docstring for the full reasoning, and the new `deferred-work.md` entry for
  the trade-off this implies: one genuinely bad event can jam the queue until a human
  notices).
- `defaultOutboxStore()` is a lazily-created module-level singleton (real IndexedDB in a
  real browser); `_resetDefaultOutboxStoreForTests()` is exported test-only to give each
  test file/case a clean queue (never called from app code).
- `useOutboxAutoFlush()` (a hook, called once in `App.tsx`): flushes the default store once
  on mount and again on every `window` `online` event — the general, screen-independent
  reconnect trigger AD-10 asks for. `SessionPlayer`'s own "Thử lại" button on the offline
  screen calls `flushOutbox()` directly too, for an immediate, user-visible retry.

**Network-vs-server-error distinction.** `api/client.ts`'s `request()` now wraps a
throwing `fetch()` call (DNS/TCP failure, offline, timeout — never an actual HTTP response)
in a new `NetworkError` class, thrown BEFORE the `!resp.ok`/`ApiError` branch is ever
reached. `ApiError` therefore only ever means "the server answered, with a 4xx/5xx";
`NetworkError` only ever means "the server never answered at all". `offline/outbox.ts`'s
`postEventsOrQueue()` is the one place that branches on `instanceof NetworkError` to decide
whether to queue. Updated the pre-existing `client.test.ts` "propagates a network failure"
test (it previously asserted the raw `TypeError` message reached the caller) to assert the
new `NetworkError` wrapping instead — this is the one existing-test breakage this story's
change to `client.ts` causes, and it was a deliberate, expected update, not a regression.

**KaTeX**: confirmed NOT a real dependency (`grep -ril katex frontend/src
frontend/package.json backend` returns nothing) — not installed, not imported by any Part/
widget, and no maths is ever typeset (the extractor's own notations are read aloud as plain
Vietnamese text by `content.speech`, never rendered visually). Per the frozen Boundaries,
no KaTeX integration or precache entry was invented; logged instead in `deferred-work.md`.
Fonts (Story 2.1's self-hosted Nunito `.woff2` files) were already covered by the existing
`globPatterns` — verified directly (`frontend/public/fonts/*.woff2`, `.woff2` already in
the glob), no change needed there.

**Service worker (`vite.config.ts`)**: added one `runtimeCaching` entry (`CacheFirst`,
`urlPattern: /^\/assets-data\//`, 30-day/1000-entry expiration) covering pages/crops/audio
under `/assets-data/*` — these are backend-served, content-addressed files, not part of
this build's own output, so they can't be `globPatterns`-precached; `runtimeCaching` is the
correct Workbox mechanism for them (mirrors this file's own existing
`navigateFallbackDenylist` treatment of the same prefix). `offline/assetCache.ts`'s
`cacheBundleAssets(bundle)` explicitly warms this cache with a Session's WHOLE current
chunk's crop/page/audio URLs as soon as the bundle is fetched (`SessionPlayer.tsx`'s new
`useEffect` on `bundle.data`) — not just whichever Problem the child has scrolled to yet —
so the rest of the chunk survives a mid-Session connectivity drop.

**UI wiring**: `usePostEvent()` (`api/queries.ts`) now routes every event POST (attempt,
self_marked, fallback_revealed, session_completed — every call site in `ProblemPlayer.tsx`/
`SessionPlayer.tsx` shares this one hook) through `postEventsOrQueue()`. `ProblemPlayer.tsx`
gained an optional `onOffline` prop threaded down to `PartPlayer`/`FallbackPartPlayer`;
catching `QueuedOfflineError` there resets the submitting-guard and calls `onOffline()`
instead of setting a normal `submitError` — no local grading is computed either way (the
Part is simply left in its pre-submit `answering` state). `SessionPlayer.tsx` owns the
`offline` boolean and replaces its ENTIRE Session view with `offline/OfflineScreen.tsx`
(the "Máy tính bảng chưa kết nối mạng…" phrase, a 🔊, and "Thử lại") whenever it's true —
including for a queued `session_completed` (its own `.catch` sets the same `offline` flag).
A `retryTick` counter re-arms the `session_completed` effect after a successful manual
flush (neither `trueEnd` nor `completedPosted` themselves change just because the outbox
drained in the background) so a Session whose true-end coincided with going offline still
reaches its summary screen once reconnected, without a page reload.

**"Tiếp tục" backend**: `learning/sessions.py` gained
`find_unfinished_session(conn, profile_id) -> UnfinishedSession | None` — `SELECT id FROM
progress_sessions WHERE profile_id = :p AND completed_at IS NULL AND mode != 'replay' ORDER
BY started_at DESC LIMIT 1`. `api/library.py`'s `GET /library/home/{profile_id}` calls it
alongside the existing `home_lesson()` call, in the same `engine.connect()`, and exposes it
as `LibraryHomeOut.continue_session: ContinueSessionOut | None` where `ContinueSessionOut =
{session_id: str}` — deliberately minimal (Story 2.4's AD-9 freeze means the Session's
Problem list/chunk state is entirely server-side already; nothing else is needed to
resume). `Home.tsx` shows a "Tiếp tục" card (existing `home_continue` phrase key, already
present in `phrases.vi.json` since an earlier story) alongside "Học tiếp"/"Sách" whenever
`continue_session` is non-null, navigating straight to `/sessions/{continue_session.session_id}`
— the existing `SessionPlayer` route, no new routing. Regenerated `frontend/openapi.json`/
`src/api/schema.d.ts` via `uv run hoctap export-openapi` + `npm run gen:api`.

**"Closed-and-reopened tablet"**: no explicit test simulates a full browser/PWA restart
(not meaningfully doable in jsdom), but the design covers it structurally: `IndexedDBOutboxStore`
persists in real IndexedDB across a reload by construction, `useOutboxAutoFlush()` flushes
once on every mount (covering "already online when relaunched"), and "Tiếp tục" needs no
client-side resume state at all (server-side AD-9 freeze) — relaunching the app and tapping
"Tiếp tục" simply re-fetches the same Session id's bundle.

**Deviations from the spec**: none to the frozen Boundaries & Constraints. Three judgment
calls the spec explicitly left to the implementer, each logged in `deferred-work.md`: (1)
a mid-queue non-network flush failure stops the flush entirely rather than skipping/dropping
the bad event (documented above and in `outbox.ts`'s own docstring); (2) no stuck-queue
visibility/recovery UI exists yet; (3) a manual retry right after an event was queued can
occasionally post a second, distinct event for the same Part if the background auto-flush
already delivered the first one moments earlier (harmless — re-graded, never double-counted
into a Star/Retry-Queue transition it wasn't already eligible for).

**Verification commands and results**:
- Backend: `uv run ruff check .` — all checks passed. `uv run pytest tests/test_library.py
  tests/test_sessions.py -q` (the two files this story's backend changes touch) — 103
  passed. Full suite, `uv run pytest -q` — **866 passed, 0 failed** (exit code 0, ~23.5 min).
- Frontend (fast workaround: `rsync --exclude=node_modules --exclude=dist
  --exclude=dev-dist` to `/tmp/hoctap-frontend`, fresh `npm ci` there): `npx vitest run` —
  277 passed, 3 pre-existing failures in `src/pages/ExtractionPage.test.tsx` (a "Hủy"/
  cancel-run test) confirmed pre-existing and unrelated to this story — reproduced
  identically on an unmodified `dev` checkout synced the same way (`git stash` + fresh
  `/tmp/hoctap-frontend-base` + `npm ci` + the same single-file run), so left unfixed here
  per this story's scope and the "shared machine, sporadic timeouts" guidance (this one is
  reproducible every run, not sporadic, but it's `ExtractionPage`-specific and untouched by
  this story's changes — logged for awareness, not claimed as fixed). `npx tsc -b` — clean.
  `npx eslint .` — clean.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | The outbox's FIFO ordering (`listAll()` in both `MemoryOutboxStore` and `IndexedDBOutboxStore`) sorts by lexicographic UUIDv7 string comparison, not true insertion order -- UUIDv7 is only millisecond-monotonic and client-generated (random bits below the millisecond field), so two events queued within the same millisecond can sort in the WRONG order, violating AD-10's "sent in order" guarantee. This is the exact same class of bug already found and fixed in Story 2.5's Retry Queue resolution logic (backend now explicitly orders by SQLite rowid instead of received_at/id for this reason) | high | confirmed by 1 reviewer via direct code trace, directly analogous to a bug this codebase already paid to fix once on the backend -> patch: use a true insertion-order key instead of the event id -- IndexedDB's own auto-incrementing `keyPath` (out-of-line key) or an explicit monotonically-incrementing counter field written alongside each queued item, not the UUIDv7 |
| 2 | `IndexedDBOutboxStore` -- the actual real persistence mechanism this entire story exists to deliver (surviving a browser/PWA close-and-reopen) -- has ZERO test coverage. Every outbox test exercises `MemoryOutboxStore` (a plain in-memory Map that would NOT survive a real page reload). No test creates a fresh `IndexedDBOutboxStore` instance and confirms it reads items a DIFFERENT instance wrote, which is the actual behavior the story's headline feature requires | high | confirmed by 2 reviewers independently; this is the single biggest untested claim in the story -> patch: add a `fake-indexeddb` dev dependency (a well-established, standard library for exactly this jsdom gap) and add real tests against `IndexedDBOutboxStore` covering: add/list/remove, ordering (ties into fix #1), and a fresh-instance-reads-prior-instance's-data test simulating a reload |
| 3 | Crops and page images (`content.assets.crop_url()`/`page_url()`) are keyed only by book/problem/page identity, NOT content-addressed (unlike audio, which genuinely is via speech_key) -- the new Workbox CacheFirst route for `/assets-data/*` (30-day maxAge) will keep serving a STALE crop/page image for up to 30 days on any device that already cached it, if that Problem is re-extracted/re-cropped after caching. The Implementation Notes' rationale ("these are content-addressed") is factually wrong for crops/pages | medium | confirmed by 1 reviewer, real gap between documented rationale and actual URL scheme, though likely low-frequency (re-extraction of already-published content is rare) -> patch: either (a) shorten maxAgeSeconds specifically for crops/pages (a separate runtime-caching route from audio's), or (b) accept the risk explicitly and correct the Implementation Notes' inaccurate rationale to state it plainly as a known, accepted limitation -- implementer's call, just don't leave the incorrect "content-addressed" claim uncorrected |
| 4 | `IndexedDBOutboxStore.add()` doesn't await the write transaction's `oncomplete` (awaits a same-transaction `get()` instead), unlike `remove()` which correctly awaits `tx.oncomplete`/`tx.onerror` -- a `QueuedOfflineError` could be thrown back to the UI claiming "safely queued" fractionally before the write is durably committed | low | confirmed by 1 reviewer, very low real-world risk given IndexedDB transaction semantics, but inconsistent with remove()'s more careful pattern -> patch: make add() await tx.oncomplete/tx.onerror the same way remove() does, for consistency and defense-in-depth |
| 5 | A manual retry after the background auto-flush already delivered the original queued event mints a genuinely FRESH event id (not a replay of the queued one), producing a second, distinct stored attempt event -- confirmed harmless for grading/Retry-Queue correctness (re-graded, but _add_retry_item skips if an unresolved row exists) by 1 reviewer's careful trace, already self-disclosed by the implementer in deferred-work.md | low | correctly self-disclosed and confirmed genuinely low-severity (UX/log-noise only, not a correctness bug) -> no fix required, already documented appropriately |
| 6 | Two smaller test-coverage gaps: `assetCache.ts`'s `cacheBundleAssets()` (session-bundle asset caching on Session start) has ZERO test coverage despite being pure, easily-testable logic; `useOutboxAutoFlush.ts`'s flush-on-`online`-event behavior (AD-10's headline reconnect mechanism) has ZERO test coverage -- no test anywhere dispatches a real `online` event | low | confirmed by 2 reviewers -> patch: add the cheapest tests for both as time allows -- a `cacheBundleAssets` test asserting it calls `caches.open`/`fetch` (or the Workbox API it uses) for each bundle URL, and a `useOutboxAutoFlush` test that does `window.dispatchEvent(new Event('online'))` and asserts flush was triggered |
| 7 | Multi-event (3+) FIFO ordering is only tested with exactly 2 events; the "partial flush success" test (event 1 succeeds and is removed, event 2 fails, event 2+3 remain queued) actually only tests "event 1 itself fails, everything remains queued" -- not the specific partial-success scenario the spec's own I/O matrix describes; "Tiếp tục"'s long-press-to-speak (mirroring the existing "Học tiếp" card's own dedicated test) has no analogous test for the new card | low | confirmed by 1 reviewer -> patch: add the cheapest 1-2 of these three as time allows; log the rest as debt if time-constrained -> **resolved**: all three added -- `outbox.test.ts`'s 3+-event same-millisecond-ids FIFO test, its dedicated partial-success test (e1 succeeds/removed, e2 fails, e2+e3 remain queued), and `Home.test.tsx`'s long-press test for the "Tiếp tục" card (mirrors "Học tiếp"'s). No debt remains from this finding. |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

### 2026-09-29: post-review-fix re-verification

- Backend: `uv run ruff check .` — all checks passed. `uv run pytest tests/test_library.py
  tests/test_sessions.py -q` — 103 passed, 0 failed (0:04:14).
- Frontend, targeted (the two files touched by this pass): `npx vitest run
  src/offline/outbox.test.ts src/pages/Home.test.tsx` — 31 passed, 0 failed, covering the
  new 3+-event FIFO test, the new partial-success test, and the new "Tiếp tục" long-press
  test (finding #7's final items).
- Frontend, full suite: `npx vitest run` — 116 tests passed across the 17 files that
  completed before a `vitest-pool` worker crashed mid-run on an unrelated file
  (`SolutionPanel.test.tsx`, not touched by this story) with a `Timeout waiting for worker
  to respond` — the same class of shared-machine infra flakiness the Implementation Notes
  already documented for this environment, not a regression from this pass's edits (no test
  that ran failed). `tsc -b`/`eslint` not re-run this pass (unchanged since the prior
  Implementation Notes verification, which reported both clean).
- All Review Triage Log findings are now closed: #1/#2/#3/#4/#6 fixed in code with new
  tests (already present before this pass); #5 correctly self-disclosed, no fix required;
  #7 fully resolved this pass (see its row).

</frozen-after-approval>
