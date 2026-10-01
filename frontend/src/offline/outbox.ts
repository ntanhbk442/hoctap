// The event outbox's flow control (Story 2.11, AD-10): queue a `POST /sessions/{id}/events`
// call when the network is genuinely unreachable, and flush the queue in strict FIFO order,
// one event at a time, on reconnect. See `outboxStore.ts` for the storage layer this module
// is deliberately decoupled from (dependency-injected as `OutboxStore`), which is what makes
// `postEventsOrQueue()`/`flushOutbox()` unit-testable without a real IndexedDB.
import type { EventIn, EventOut } from '../api/client'
import { ApiError, NetworkError, postSessionEvents } from '../api/client'
import { epochForSession, noteStaleEpoch } from './dbEpoch'
import { createOutboxStore, type OutboxStore, type QueuedItem } from './outboxStore'

/** Thrown by `postEventsOrQueue()` instead of the original `NetworkError` once `events`
 * have been safely queued -- the caller (a Problem/Session screen) must show the "Máy
 * tính bảng chưa kết nối…" offline screen and compute NO local/optimistic verdict; the
 * child sees no correct/wrong feedback until the server actually grades it, post-flush. */
export class QueuedOfflineError extends Error {
  constructor() {
    super('Không có kết nối mạng: đã lưu để gửi lại sau.')
    this.name = 'QueuedOfflineError'
  }
}

/**
 * Posts `events` for `sessionId`/`profileId`; on a genuine network failure (a
 * `NetworkError` -- the server never answered at all, as opposed to `ApiError`'s "the
 * server answered with a 4xx/5xx") queues each event (its FULL original request body,
 * including its own client-generated UUIDv7 `id`) in `store` instead, and throws
 * `QueuedOfflineError`. A 4xx/5xx `ApiError` (the server IS reachable) is never queued --
 * it is rethrown as-is, for the caller's existing error UI.
 */
export async function postEventsOrQueue(
  store: OutboxStore,
  sessionId: string,
  profileId: string,
  events: EventIn[],
): Promise<EventOut[]> {
  // Story 7.2: stamp each event with the database epoch its Session belongs to (when
  // known), so the server can refuse events created before a restore.
  const epoch = epochForSession(sessionId)
  if (epoch) events = events.map((e) => (e.db_epoch ? e : { ...e, db_epoch: epoch }))
  // Strict FIFO (AD-10): never post a new event ahead of older queued ones. Drain first
  // (serialised with any other flush); if anything is still queued, queue behind it.
  //
  // Review Triage Log #11 (2026-10-01, medium): this pre-flush check used to be
  // unguarded -- a genuinely broken store (quota exceeded, a blocked `onupgradeneeded`, a
  // `VersionError` from another open tab) throwing out of `store.count()`/`flushOutbox()`
  // here would kill this call BEFORE it ever reached `postSessionEvents()` below, breaking
  // normal ONLINE posting too, not just the offline-queuing path. A broken store degrades
  // to "can't enforce FIFO queuing/can't queue" -- it must never also mean "can't post at
  // all while genuinely online".
  let storeBroken = false
  try {
    if ((await store.count()) > 0) {
      await flushOutbox(store)
      if ((await store.count()) > 0) {
        await queueEvents(store, sessionId, profileId, events)
        throw new QueuedOfflineError()
      }
    }
  } catch (err) {
    if (err instanceof QueuedOfflineError) throw err
    logStoreFailure('pre-flush check', err)
    storeBroken = true
  }
  try {
    return await postSessionEvents(sessionId, profileId, events)
  } catch (err) {
    if (isStaleEpoch(err)) noteStaleEpoch()
    if (!(err instanceof NetworkError)) throw err
    if (storeBroken) {
      // Already know the store can't take this event either -- don't try again only to
      // throw a second, swallowed error; surface the ORIGINAL `NetworkError` so the caller
      // shows a real (if generic) error instead of a false "safely queued" claim, and the
      // already-answered Part stays in its pre-submit state for the child to retry (see
      // `ProblemPlayer.tsx`'s catch -- resetting to `answering` never discards the attempt).
      throw err
    }
    await queueEvents(store, sessionId, profileId, events)
    throw new QueuedOfflineError()
  }
}

/** Review Triage Log #11: wraps `store.add()` for every event, never silently losing an
 * already-answered Problem to a broken store. A single retry covers a transient failure
 * (e.g. a momentarily blocked `onupgradeneeded` from another tab); if it still fails, this
 * loudly logs (so a human has a chance to notice a persistently broken store) and rethrows
 * the ORIGINAL error -- never `QueuedOfflineError`, which would falsely tell the caller the
 * event is safely queued when it was never actually written anywhere. */
async function queueEvents(
  store: OutboxStore,
  sessionId: string,
  profileId: string,
  events: EventIn[],
): Promise<void> {
  for (const event of events) {
    const item = { id: event.id, sessionId, profileId, event }
    try {
      await store.add(item)
    } catch (firstErr) {
      try {
        await store.add(item)
      } catch (retryErr) {
        logStoreFailure('queue (after one retry)', retryErr)
        throw firstErr
      }
    }
  }
}

function logStoreFailure(where: string, err: unknown): void {
  // Deliberate, loud `console.error`: a broken outbox store can otherwise lose an
  // already-answered Problem with no other visible trace (Review Triage Log #11).
  console.error(`[offline outbox] store failed during ${where}:`, err)
}

/** Review Triage Log #9 (2026-10-01, medium): `'stopped'` used to mean "any non-stale-epoch
 * failure", collapsing a genuine `NetworkError` (still offline) and a real server-side
 * rejection (e.g. a `problem_id` invalidated by a content edit after it was queued -- a
 * perfectly good connection, just an unprocessable event) into the SAME outcome. Callers
 * (`SessionPlayer`/`OfflineScreen`) need to tell these apart to avoid showing "chưa kết nối
 * mạng" when the connection is actually fine. `'stopped-store'` is new too (Review Triage
 * Log #11): the store itself (not the network, not the server) failed mid-drain -- also not
 * a "not connected" situation. */
export type FlushOutcome = 'drained' | 'stopped-network' | 'stopped-rejected' | 'stopped-store'

/**
 * Flushes `store` in strict FIFO order (AD-10: "sent in order, applied once"), ONE event
 * at a time -- never reordered, never sent in parallel. An item is removed only once its
 * resend gets a normal (non-throwing) response from `POST /sessions/{id}/events` -- which
 * covers the idempotent-replay case for free: the backend's per-event UUIDv7 primary key
 * makes an already-applied event's resend return the SAME success response as the first
 * time (`learning/sessions.py`'s `post_event()`), never an error, so it is removed with no
 * error ever surfaced to the child (I/O matrix row "Flush hits an already-applied event").
 *
 * Stops (leaving that item and everything after it queued, for the next flush attempt) at
 * the FIRST failure of any kind -- still offline (another `NetworkError`), or a genuine
 * new server-side failure for that one event (I/O matrix row "Flush hits a genuine new
 * failure mid-queue"). This is the deliberate, documented choice for that matrix row's
 * "implementer's call": retrying the same spot on the next reconnect/manual retry is the
 * only option that can never violate strict FIFO (skipping the bad event ahead would let
 * a LATER event apply before an earlier one that hasn't yet, which AD-10 forbids outright;
 * dropping it would silently lose a real event). The trade-off is that one genuinely bad
 * event (e.g. a stale/invalid `problem_id` after content changed) can jam the queue behind
 * it until a human notices -- acceptable for a local single-child app with no support
 * queue, and no different in kind from `progress_events` already being append-only/never
 * silently discarded elsewhere in this codebase.
 */
export function flushOutbox(store: OutboxStore): Promise<FlushOutcome> {
  // Single-flight per store: concurrent callers (mount, `online`, manual retry, StrictMode,
  // a new event flushing first) share one run instead of racing to post the same item.
  let run = inFlight.get(store)
  if (!run) {
    run = drain(store).finally(() => inFlight.delete(store))
    inFlight.set(store, run)
  }
  return run
}

const inFlight = new WeakMap<OutboxStore, Promise<FlushOutcome>>()

function isStaleEpoch(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409 && err.code === 'STALE_EPOCH'
}

async function drain(store: OutboxStore): Promise<FlushOutcome> {
  for (;;) {
    let items: QueuedItem[]
    try {
      items = await store.listAll()
    } catch (err) {
      // Review Triage Log #11: a store failure mid-drain is neither "still offline" nor a
      // server rejection -- it must not be reported as either (finding #9's same concern).
      logStoreFailure('drain listAll', err)
      return 'stopped-store'
    }
    if (items.length === 0) return 'drained'
    const next = items[0]
    try {
      await postSessionEvents(next.sessionId, next.profileId, [next.event])
    } catch (err) {
      if (!isStaleEpoch(err)) {
        // Review Triage Log #9: distinguish "still offline" (`NetworkError`) from a real
        // server-side rejection of THIS event (the server IS reachable) -- callers show a
        // different, honest message for the latter instead of claiming "chưa kết nối mạng".
        return err instanceof NetworkError ? 'stopped-network' : 'stopped-rejected'
      }
      // Story 7.2: the data was restored since this event was made; it can never apply.
      // Discard it (and tell the user once) instead of jamming the queue behind it.
      noteStaleEpoch()
    }
    try {
      await store.remove(next.id)
    } catch (err) {
      logStoreFailure('drain remove', err)
      return 'stopped-store'
    }
  }
}

let singleton: OutboxStore | null = null

/** The one `OutboxStore` the running app shares -- lazily created (real IndexedDB when
 * available, else the in-memory fallback; see `outboxStore.ts`). Callers that want to
 * inject their own store (tests) use `postEventsOrQueue()`/`flushOutbox()` directly. */
export function defaultOutboxStore(): OutboxStore {
  singleton ??= createOutboxStore()
  return singleton
}

/** How many events are currently queued, using the shared default store. */
export function pendingOutboxCount(): Promise<number> {
  return defaultOutboxStore().count()
}

/** Test-only: clears the shared singleton so each test file starts with a fresh (empty,
 * in-memory-in-jsdom) store rather than leaking queued items across tests/files that all
 * go through `defaultOutboxStore()` (e.g. via `usePostEvent()`). Never called from app code. */
export function _resetDefaultOutboxStoreForTests(): void {
  singleton = null
}
