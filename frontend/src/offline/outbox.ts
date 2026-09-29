// The event outbox's flow control (Story 2.11, AD-10): queue a `POST /sessions/{id}/events`
// call when the network is genuinely unreachable, and flush the queue in strict FIFO order,
// one event at a time, on reconnect. See `outboxStore.ts` for the storage layer this module
// is deliberately decoupled from (dependency-injected as `OutboxStore`), which is what makes
// `postEventsOrQueue()`/`flushOutbox()` unit-testable without a real IndexedDB.
import type { EventIn, EventOut } from '../api/client'
import { NetworkError, postSessionEvents } from '../api/client'
import { createOutboxStore, type OutboxStore } from './outboxStore'

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
  try {
    return await postSessionEvents(sessionId, profileId, events)
  } catch (err) {
    if (!(err instanceof NetworkError)) throw err
    for (const event of events) {
      await store.add({ id: event.id, sessionId, profileId, event })
    }
    throw new QueuedOfflineError()
  }
}

export type FlushOutcome = 'drained' | 'stopped'

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
export async function flushOutbox(store: OutboxStore): Promise<FlushOutcome> {
  for (;;) {
    const items = await store.listAll()
    if (items.length === 0) return 'drained'
    const next = items[0]
    try {
      await postSessionEvents(next.sessionId, next.profileId, [next.event])
    } catch {
      return 'stopped'
    }
    await store.remove(next.id)
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
