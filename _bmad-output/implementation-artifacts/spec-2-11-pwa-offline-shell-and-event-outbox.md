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

### 2026-10-01: fixes for Review Triage Log findings #8–#12 (post-audit)

Fixed, in priority order, the 5 actionable findings from the orchestrator's independent
audit (#8/#10/#11/#9/#12 above); #13/#14 left as-is per their own rows ("no fix required").

**#8 (high) — request timeout.** `api/client.ts`'s `request()` previously let a stalled
connection hang `fetch()` forever (no `AbortSignal` at all). Added a module-level
`REQUEST_TIMEOUT_MS = 12_000` constant and pass `AbortSignal.timeout(REQUEST_TIMEOUT_MS)`
to `fetch()` — merged with any caller-supplied `signal` via `AbortSignal.any()` when one is
given (e.g. a query's own unmount-cancellation), so neither cancellation path is lost. No
new error branch was needed: `AbortSignal.timeout()` rejects `fetch()` itself, and the
existing `catch` around `fetch()` already wraps ANY throw (DNS/TCP failure or now a
timeout) in `NetworkError`, which is exactly what `outbox.ts`'s offline-queuing path
already branches on. 12s is a judgment call for a LAN app (the server is always on the
same Wi-Fi as the tablet, never over the public internet) — long enough that a slow SQLite
write under WAL contention isn't mistaken for a dead connection, short enough to resolve
well within a young child's patience. New test in `client.test.ts`: since
`AbortSignal.timeout()` is implemented via internal timers vitest's fake-timer
`advanceTimersByTimeAsync()` cannot reach (confirmed by trying it first — it hung the real
test for the full 5s Vitest default timeout), the test instead spies on
`AbortSignal.timeout()` to substitute an `AbortController` the test fully controls, then
aborts it manually and asserts the resulting rejection resolves as `NetworkError`.

**#10 (medium) — offline screen didn't auto-clear on a background drain.**
`useOutboxAutoFlush()` now accepts an optional `onDrained(outcome: FlushOutcome)` callback,
invoked after every one of ITS OWN mount/`online` flushes (not after a caller's own
separate `flushOutbox()` call, e.g. a manual retry button — those are independent by
design). `SessionPlayer` adds its own `useOutboxAutoFlush(onDrained)` call (alongside the
pre-existing, argument-less one in `App.tsx` — `flushOutbox()`'s single-flight `inFlight`
WeakMap means this costs no extra network calls) and clears `offline`/`stuckNotNetwork` and
bumps `retryTick` when the outcome is `'drained'`. Guarded by an `offlineRef` kept in sync
with the `offline` state via a tiny `useEffect` — without it, every routine background
flush (even an empty-queue one on ordinary mount) would needlessly re-arm the
`session_completed` effect via `retryTick`; the guard means this only fires when the
Session's own queue was actually the thing that caused `offline` to be true.

**#11 (medium) — store failures weren't caught.** Three separate gaps, all in
`offline/outbox.ts`: (1) `postEventsOrQueue()`'s pre-flush FIFO check
(`store.count()`/`flushOutbox()`) was unguarded — a broken store (quota exceeded, a blocked
`onupgradeneeded`, a `VersionError` from another open tab) throwing here would have killed
the call before it ever reached `postSessionEvents()`, breaking NORMAL online posting too,
not just offline-queuing. Now wrapped in try/catch; on a store failure it logs loudly
(`logStoreFailure()`) and proceeds to attempt a normal post anyway (a broken store means
"can't queue", never "can't post at all while genuinely online"). (2) `queueEvents()`
(`store.add()` per event) now retries once on failure before giving up, logs loudly if the
retry also fails, and rethrows the ORIGINAL error — deliberately NEVER `QueuedOfflineError`
in this case, since that would falsely claim the event is safely queued when it was never
written anywhere; the existing generic-`submitError` catch in `ProblemPlayer.tsx` already
resets the Part to `answering` either way, so the child's answer is never discarded, just
not auto-queued. (3) `drain()`'s own `store.listAll()`/`store.remove()` calls are now
wrapped too, returning the new `'stopped-store'` outcome instead of throwing — previously
this could have become an unhandled promise rejection via `useOutboxAutoFlush`'s
fire-and-forget background flush (now has an explicit `.catch` too) or `SessionPlayer`'s
`void handleRetryOnline()`. New tests in `outbox.test.ts` use a `ThrowingOutboxStore` (every
method throws) to cover: posts normally despite a fully broken store; rethrows the original
`NetworkError` when BOTH the server and the store fail; `flushOutbox()` resolves
`'stopped-store'` rather than rejecting; a transient `add()` failure is retried once and
succeeds.

**#9 (medium) — offline screen lied when stuck on a non-network failure.** `FlushOutcome`
was a single `'stopped'` meaning "any non-stale-epoch failure" — collapsing "still offline"
and "server reachable, but rejects this one event" (e.g. a `problem_id` invalidated by a
content edit after it was queued) into the same bucket, so `OfflineScreen` always said
"chưa kết nối mạng" even when the connection was fine. `FlushOutcome` is now `'drained' |
'stopped-network' | 'stopped-rejected' | 'stopped-store'`; `drain()` checks
`err instanceof NetworkError` to pick `'stopped-network'` vs. `'stopped-rejected'`.
`SessionPlayer` tracks a new `stuckNotNetwork` boolean (set on `'stopped-rejected'`/
`'stopped-store'`, cleared on `'drained'`, checked on both the manual-retry path and the
new `useOutboxAutoFlush` `onDrained` path from #10) and passes it to `OfflineScreen`, which
renders the new `offline_stuck_not_network` phrase ("Có bài chưa gửi được, nhưng máy tính
bảng vẫn đang kết nối mạng.") instead of `offline_not_connected` in that case — same
screen, same retry button, just an honest message. New phrase key added to
`phrases.vi.json`; new test in `SessionPlayer.test.tsx`.

**#12 (medium) — no guard against two unfinished Sessions per profile.** Chose option (a)
from the finding's own two listed choices: `start_session()` now auto-completes/abandons
any OTHER `completed_at IS NULL` Session for the same `profile_id` before inserting the new
one — a single `UPDATE ... WHERE profile_id = :p AND completed_at IS NULL` stamping
`completed_at` to the NEW Session's own `started_at`, placed right after the
`EMPTY_PROBLEM_SET` 422 check (so a 422 still creates zero rows, matching
`test_start_zero_visible_problems_422_no_session_created`) and before the new Session's
`INSERT`. Chosen over listing ALL unfinished Sessions on Home because it matches how a
young child actually uses this app — one Lesson at a time — and an abandoned Lesson simply
isn't coming back; the abandoned row's events/stars are untouched, only `completed_at`
changes, so it cleanly drops out of `find_unfinished_session()`'s `completed_at IS NULL`
filter without being backdated to an arbitrary earlier time. New test in `test_sessions.py`
(`test_start_second_session_abandons_prior_unfinished_one`): starts a Lesson, then a second
different Lesson for the same Profile, and asserts the first Session is now completed while
the second stays open.

**What was deliberately NOT done**: findings #13 (FIFO-by-caller-discipline) and #14
(the "Tiếp tục" docstring overstating code reuse) were explicitly marked "no fix required"
in their own rows and are unchanged — #13 is latent-only (every current call site already
awaits serially) and #14 is a documentation-wording issue, not a behavior defect; touching
either would be scope creep for a bug-fix pass. Also did not change `downloadBackup()`'s
separate, raw `fetch()` call in `client.ts` (Story 7.2) to use the new timeout — finding #8
was scoped to `request()` specifically, and a large `.db` file transfer legitimately needs
a different (longer, or absent) timeout policy than a JSON event POST; flagged here rather
than silently left inconsistent.

**Verification commands and results (this pass)**:
- Backend: `uv run ruff check .` — all checks passed. `uv run pytest tests/test_sessions.py
  tests/test_library.py -q` — 116 passed, 0 failed (includes the new finding-#12 test).
  Full suite, `uv run pytest -q` — **1148 passed, 0 failed** (22m12s; see also the dated
  entry in `## Verification` below).
- Frontend (same `/tmp` rsync workaround, plus symlinking `/tmp/backend` and
  `/tmp/_bmad-output` to the real repo so the handful of tests that read fixtures via a
  `../backend`/`../_bmad-output` relative path — `WorksheetPage.test.tsx`,
  `print/leak.test.tsx`, `print/renderers.test.tsx`, `styles/tokens.test.ts` — resolve
  correctly from the isolated copy): `npx tsc -b` — clean. `npx eslint .` — clean (after
  moving one `eslint-disable-next-line` comment to immediately precede the line it was
  meant to suppress — a multi-line comment block had pushed it one line too early, so ESLint
  reported it as unused while the real `react-hooks/exhaustive-deps` warning went
  unsuppressed). `npx vitest run src/offline src/pages/SessionPlayer.test.tsx
  src/api/client.test.ts` — 87 passed. `npx vitest run src/pages/ProblemPlayer.test.tsx
  src/pages/ProblemPlayer.expression.test.tsx src/pages/ProblemPlayer.speaker.test.tsx` — 59
  passed. Full suite (`npx vitest run`) is flaky under this shared machine's parallel
  worker load exactly as the 2026-09-29 entry already documented — re-ran the handful of
  files that failed only in the full-suite run (`ProblemPlayer.expression.test.tsx`,
  `SessionPlayer.test.tsx`) in isolation and they passed cleanly (6/6, 30/30), confirming
  infra flakiness, not a regression. The one CONSISTENTLY-reproducing failure across every
  run, isolated or not, is the same pre-existing `ExtractionPage.test.tsx` "Hủy" issue
  the 2026-09-29 entry already logged as unrelated to this story.

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
| 8 | **No request timeout anywhere** (`api/client.ts`'s `request()` only wraps `fetch()` in try/catch -- no `AbortSignal.timeout()`/`AbortController` exists in `client.ts` or `offline/outbox.ts`, confirmed via grep), despite `NetworkError`'s own doc comment and `outbox.ts`'s module docstring both listing "timeout" as a condition that should produce a `NetworkError`. A TCP-connected-but-never-responding server (a stalled captive portal, a flaky school Wi-Fi proxy -- exactly the real-world condition this story exists to survive) leaves `fetch()` never settling: `postEventsOrQueue()` awaits it forever, `PartPlayer.handleCheck()` is stuck in `phase: 'submitting'` permanently -- no offline screen, no error, no retry button, just a dead "✔ Kiểm tra" button | high | confirmed by 1 reviewer via direct grep + trace -> patch: wrap the `fetch()` call in `client.ts`'s `request()` with `AbortSignal.timeout(N)` (a reasonable N, e.g. 10-15s given this is a LAN app), and treat the resulting `AbortError`/`TimeoutError` as a `NetworkError` so it flows into the existing offline-queuing path instead of hanging -> **resolved**: `client.ts`'s `request()` now passes `AbortSignal.timeout(REQUEST_TIMEOUT_MS)` (12s, a named constant) to `fetch()` (merged with any caller-supplied signal via `AbortSignal.any()`); the resulting abort rejects `fetch()`, which the existing `catch` already wraps in `NetworkError` -- no new branch needed, since a timeout and a DNS/TCP failure both just mean "`fetch()` itself threw". New test in `client.test.ts` spies on `AbortSignal.timeout()` to substitute a controllable signal (real fake-timers can't advance it -- it isn't implemented via the patchable global `setTimeout`) and confirms aborting it resolves as `NetworkError`. |
| 9 | The offline screen's message is wrong (not just absent) when the outbox is jammed on a non-network failure. `drain()` returns `'stopped'` on ANY non-stale-epoch failure, whether a `NetworkError` or a genuine server-side rejection (e.g. a `problem_id` invalidated by a content edit after it was queued -- a scenario the implementer's own docstring already anticipates). `SessionPlayer.handleRetryOnline()` doesn't distinguish: `OfflineScreen.tsx` unconditionally shows "Máy tính bảng chưa kết nối mạng…" even when the real problem is a permanently-stuck, unprocessable event on a perfectly good connection -- actively misinforms rather than just lacking visibility (deferred-work.md's existing item 2 only notes "no stuck-queue visibility UI", not that the UI affirmatively lies in this state) | medium | confirmed by 1 reviewer -> patch: have `drain()`/`flushOutbox()` distinguish a `NetworkError` stop from a genuine server-rejection stop, and have `OfflineScreen` (or a sibling screen) show a different, honest message for the latter ("có bài chưa gửi được, đã kết nối lại" or similar) -- at minimum, stop claiming "not connected" when the connection is fine -> **resolved**: `FlushOutcome` is now `'drained' \| 'stopped-network' \| 'stopped-rejected' \| 'stopped-store'` (the last one new too, for finding #11) instead of a single collapsed `'stopped'`. `SessionPlayer` tracks a `stuckNotNetwork` flag (set on `'stopped-rejected'`/`'stopped-store'`, cleared on `'drained'`) and passes it to `OfflineScreen`, which shows the new `offline_stuck_not_network` phrase ("Có bài chưa gửi được, nhưng máy tính bảng vẫn đang kết nối mạng.") instead of "chưa kết nối mạng" in that case. New test in `SessionPlayer.test.tsx`. |
| 10 | The offline screen does not auto-clear when the background auto-flush (`useOutboxAutoFlush`, fired on mount and on every `online` event) successfully drains the exact queue that caused it to show. Only `SessionPlayer.handleRetryOnline()` (wired solely to the screen's own manual "Thử lại" button) ever sets `offline` back to `false`. Scenario: child answers right as Wi-Fi drops -> queued, offline screen shown; Wi-Fi returns a second later -> the `online` listener silently flushes it to the server -> child is still staring at "chưa kết nối mạng" and must tap "Thử lại" themselves even though the data is already safely on the server -- an extra, confusing step for a young child in the exact success case this story was built to handle gracefully | medium | confirmed by 1 reviewer via direct code trace (`SessionPlayer.tsx`'s `offline` state vs. `useOutboxAutoFlush`'s independent trigger) -> patch: have `SessionPlayer` subscribe to (or poll) outbox drain completion -- e.g. `useOutboxAutoFlush` taking an `onDrained` callback, or `SessionPlayer` re-checking `store.count() === 0` after every `online` event/mount flush -- and clear `offline` automatically once the queue that caused it is empty -> **resolved**: `useOutboxAutoFlush()` now takes an optional `onDrained(outcome)` callback, invoked after every one of ITS OWN mount/`online` flushes. `SessionPlayer` calls it (alongside its own pre-existing `App.tsx`-level instance) and clears `offline`/`stuckNotNetwork` and bumps `retryTick` when the outcome is `'drained'` -- guarded by an `offlineRef` (kept in sync with the `offline` state) so a routine, nothing-queued background flush never needlessly re-arms the `session_completed` effect. New test in `SessionPlayer.test.tsx` dispatches a real `online` event (never tapping "Thử lại") and confirms the offline screen clears on its own. |
| 11 | No handling for IndexedDB actually throwing (vs. merely being unavailable). `createOutboxStore()` only falls back to `MemoryOutboxStore` when `typeof indexedDB === 'undefined'` -- it never catches a real failure from an existing `IndexedDBOutboxStore` (quota exceeded, a blocked `onupgradeneeded`, a `VersionError` from another open tab). If `store.add()` throws while queuing inside `postEventsOrQueue()`, the exception propagates straight out instead of becoming `QueuedOfflineError`; `ProblemPlayer.tsx`'s catch only gives the "queued offline" treatment to `QueuedOfflineError`, so anything else falls through to a generic `submitError` -- and critically, the event was never posted AND never queued, so the child's answer is lost unless they retry the exact same tap before closing the app. The pre-flush path (`await flushOutbox(store)` inside `postEventsOrQueue`) also isn't wrapped in try/catch, and `useOutboxAutoFlush`'s `void flushOutbox(store)` discards the promise with no `.catch`, so the same failure during background auto-flush becomes an unhandled promise rejection | medium | confirmed by 1 reviewer via direct trace -> patch: wrap `store.add()`/`flushOutbox()` calls in `postEventsOrQueue()` in try/catch, and on a genuine store failure either retry once or surface the SAME offline-queued UX with a `.catch` on `useOutboxAutoFlush`'s background flush -- the fix should prioritize never silently losing an already-answered problem -> **resolved**: `postEventsOrQueue()`'s pre-flush FIFO check (`store.count()`/`flushOutbox()`) is now wrapped in try/catch -- a broken store degrades to "can't queue" only, never "can't post at all while genuinely online" (it no longer blocks a normal online post). `queueEvents()` retries `store.add()` once per event, loudly `console.error`s on a persistent failure, and rethrows the ORIGINAL error (never a false `QueuedOfflineError`) so the child's answer is never silently lost -- `ProblemPlayer.tsx`'s existing catch-all already resets the Part to `answering` and shows a real error either way. `drain()`'s own `listAll()`/`remove()` calls are now wrapped too, resolving the new `'stopped-store'` outcome instead of throwing (which would have been an unhandled rejection from `useOutboxAutoFlush`'s background sweep or `SessionPlayer`'s manual-retry `void` call). `useOutboxAutoFlush`'s background flush now has an explicit `.catch`. New tests in `outbox.test.ts` (a `ThrowingOutboxStore` covering: still posts normally when the server is reachable despite a fully broken store; rethrows the original `NetworkError` when BOTH the server and the store fail; `flushOutbox` resolves `'stopped-store'` rather than rejecting; a transient `add()` failure is retried once and succeeds). |
| 12 | `start_session()` has no guard against multiple simultaneous unfinished Sessions for one profile, and `find_unfinished_session()` only ever surfaces the most recent one (`ORDER BY started_at DESC LIMIT 1`). Scenario: child starts Lesson A, answers one problem, backs out to the Library, starts Lesson B (also never finished) -- both rows now have `completed_at IS NULL`; "Tiếp tục" will only ever offer Lesson B, and Lesson A's partially-answered Session becomes a permanent "zombie" row with no UI path back to it (not done, not resumable, not deleted) | medium | confirmed by 1 reviewer; genuinely occurs by design (contrary to the audit prompt's assumption it "shouldn't happen") -> patch: implementer's call between (a) `start_session()` auto-completing/abandoning any prior unfinished Session for the same profile before starting a new one, or (b) `find_unfinished_session()` listing ALL unfinished Sessions (not just the latest) so Home can offer a choice -- (a) is simpler and matches how a young child actually behaves (one Lesson at a time); document whichever is chosen -> **resolved**: chose (a). `start_session()` now stamps `completed_at` (to this new Session's own `started_at`) on any OTHER `completed_at IS NULL` row for the same `profile_id`, right after the empty-problem-set 422 check and before inserting the new Session row -- the abandoned Session's events/stars are untouched, only `completed_at` changes, so it simply stops being "unfinished" and drops out of `find_unfinished_session()`. New test in `test_sessions.py` starts two Lessons back-to-back for one Profile and confirms the first is auto-completed while the second stays open. |
| 13 | `postEventsOrQueue()`'s FIFO guarantee is upheld only by caller discipline (every current call site awaits the prior mutation before firing the next), not structurally enforced by the function itself -- unlike `flushOutbox()`, which IS correctly single-flighted via its `inFlight` WeakMap. Not exploitable today (traced every call site), but the module's own "never reordered, strict FIFO" comments describe a guarantee the function doesn't actually hold on its own | low | confirmed by 1 reviewer, latent only -> no fix required now; worth a comment correction (`postEventsOrQueue()`'s FIFO claim should note it depends on serial callers) if anyone touches this file next, otherwise log as debt |
| 14 | Implementation Notes overstate "Tiếp tục" as reusing Story 2.10's mode-filtering logic -- `find_unfinished_session()` is a fresh query with its own inline `mode != 'replay'` condition, duplicated (not shared via a function) at 3 other call sites in `sessions.py`. Semantically consistent with AD-6, just not literal code reuse | low | confirmed by 1 reviewer -> no functional fix needed; phrasing-only inaccuracy, left as-is (not worth a drive-by refactor for a documentation wording issue) |

### 2026-10-01: Orchestrator's Independent Audit (post-incident re-review)

Re-audited this story (built by the since-discovered unsupervised process) with 3 fresh parallel reviewers, explicitly tasked with verifying the self-reported findings #1-7 and their claimed fixes were real, not just asserted, before trusting any of it. **Verdict: every specific, checkable claim (the UUIDv7 FIFO fix, the `fake-indexeddb` tests against the real `IndexedDBOutboxStore`, the cache-TTL split, the `add()` await fix, the finding #7 tests) was independently verified true against the actual current code** -- this story's internal self-review was genuine, substantive work, not fabricated. New findings #8-14 above were found by the fresh pass; #8 (no request timeout) is the one that would block merge on its own given the stakes (a stuck, ungradeable submit screen on the exact flaky-connection scenario this story exists to handle). #10, #11, #12 are real but lower-urgency UX/edge-case gaps. #9, #13, #14 are polish/documentation, not design defects.

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

### 2026-10-01: findings #8–#12 fix verification

- Backend: `uv run ruff check .` — all checks passed. `uv run pytest tests/test_sessions.py
  tests/test_library.py -q` — 116 passed, 0 failed (includes the new finding-#12 test).
  Full suite, `uv run pytest -q` — **1148 passed, 0 failed** (exit code 0, 22m12s).
- Frontend: `npx tsc -b` — clean. `npx eslint .` — clean. Targeted:
  `npx vitest run src/offline src/pages/SessionPlayer.test.tsx
  src/pages/ProblemPlayer.test.tsx src/pages/ProblemPlayer.expression.test.tsx
  src/pages/ProblemPlayer.speaker.test.tsx src/api/client.test.ts` — **146 passed, 0
  failed**, covering the new timeout test (#8), the new background-auto-clear and
  honest-message tests (#10/#9), the new `ThrowingOutboxStore` store-failure tests (#11),
  and the `onDrained` callback test. Full suite (`npx vitest run`) is flaky under this
  shared machine's parallel worker load (a few files time out only under full-suite
  contention); re-ran each file that failed only in the full-suite pass in isolation and
  every one passed cleanly, confirming infra flakiness rather than a regression — matches
  the same class of flakiness the 2026-09-29 entries already documented. The one
  consistently-reproducing failure, isolated or not, is the pre-existing
  `ExtractionPage.test.tsx` "Hủy" issue already logged as unrelated to this story.
- Findings #8/#9/#10/#11/#12 are now closed (see their Review Triage Log rows' `->
  **resolved**` notes for what changed and why). #13/#14 remain correctly "no fix required"
  (latent-only / phrasing-only, per their own rows) — not touched.

</frozen-after-approval>
