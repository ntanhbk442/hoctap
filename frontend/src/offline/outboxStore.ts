// The event outbox's storage layer (Story 2.11, AD-10). Kept as a small interface
// (`OutboxStore`) with two implementations -- `IndexedDBOutboxStore` (the real, persisting
// store a Service-Worker-capable browser always has) and `MemoryOutboxStore` (a plain
// array, used both as the graceful fallback when `indexedDB` genuinely isn't available --
// e.g. a private-mode browser that blocks it -- and as one of the concrete stores
// `outbox.test.ts` injects to unit-test `postEventsOrQueue()`/`flushOutbox()`'s FIFO and
// idempotent-replay logic). `IndexedDBOutboxStore` itself is exercised directly by
// `outboxStore.indexeddb.test.ts`, against the `fake-indexeddb` dev dependency (this repo's
// jsdom test environment has no real IndexedDB, and `fake-indexeddb` is the standard,
// well-established library for exactly this gap).
//
// FIFO ordering (2026-09-29 review fix, finding #1): ordering MUST be true insertion
// order, never a sort of the event's own UUIDv7 `id`. UUIDv7 is only millisecond-monotonic
// -- the bits below the millisecond field are client-generated randomness -- so two events
// queued within the same millisecond can sort in the WRONG order under a lexicographic id
// comparison, silently violating AD-10's "sent in order" guarantee. This is the exact same
// class of bug Story 2.5's Retry Queue resolution logic already hit and fixed on the
// backend (ordering explicitly by SQLite rowid, not a timestamp/id column, for this same
// reason). `MemoryOutboxStore` now relies on `Map`'s own guaranteed insertion-order
// iteration (a `.set()` on an already-present key updates the value WITHOUT moving its
// position -- exactly the "re-queuing overwrites in place" semantics this store wants).
// `IndexedDBOutboxStore` now keys its object store by a separate, out-of-line
// auto-incrementing `seq` field (assigned by IndexedDB itself on `add`), with a unique
// index on the event's own `id` for `get`/`remove`/dedupe-on-requeue lookups -- `getAll()`
// on a store keyed by an autoIncrement integer already returns records in true insertion
// order, so no further sorting is needed (or possible to get wrong) in `listAll()`.
import type { EventIn } from '../api/client'

/** One queued `POST /sessions/{id}/events` call's worth of a SINGLE event -- the full
 * original request body (`sessionId`/`profileId`/the whole `EventIn`, including its own
 * client-generated UUIDv7 `id`) so a flush resend is byte-for-byte the same request the
 * caller originally tried, and the backend's existing per-event idempotency (keyed on
 * `event.id`) handles a resend exactly like any other resend -- see `learning/sessions.py`'s
 * `post_event()`. */
export interface QueuedItem {
  /** = `event.id` (a UUIDv7). NOT used for ordering (see this file's module docstring) --
   * only for `remove()`/dedupe-on-requeue lookups. Re-queuing the same event id is
   * idempotent at the STORE level too (an `add()` of an id already present overwrites the
   * value in place, at its ORIGINAL position, never duplicating or reordering an entry). */
  id: string
  sessionId: string
  profileId: string
  event: EventIn
}

export interface OutboxStore {
  add(item: QueuedItem): Promise<void>
  /** Every queued item, in true insertion (FIFO) order -- see this file's module docstring
   * for why this can never be a sort of `QueuedItem.id`. */
  listAll(): Promise<QueuedItem[]>
  remove(id: string): Promise<void>
  count(): Promise<number>
}

/** The graceful-degrade / test-friendly store: a plain in-memory array. Never persists
 * across a reload -- only `IndexedDBOutboxStore` gives the "survives a closed-and-reopened
 * tablet" guarantee (this story's Boundaries & Constraints) that a real browser needs. */
export class MemoryOutboxStore implements OutboxStore {
  private items = new Map<string, QueuedItem>()

  async add(item: QueuedItem): Promise<void> {
    // `Map.set()` on an already-present key updates its value WITHOUT moving its iteration
    // position -- so this is true insertion order, never a sort of `item.id`.
    this.items.set(item.id, item)
  }

  async listAll(): Promise<QueuedItem[]> {
    return [...this.items.values()]
  }

  async remove(id: string): Promise<void> {
    this.items.delete(id)
  }

  async count(): Promise<number> {
    return this.items.size
  }
}

const DB_NAME = 'hoctap-outbox'
const DB_VERSION = 1
const STORE_NAME = 'events'
const BY_ID_INDEX = 'byId'

function openDb(dbName: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(dbName, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      // Keyed by an out-of-line, auto-incrementing `seq` (assigned by IndexedDB itself on
      // `add`/`put`) so `getAll()` returns records in true insertion order -- see this
      // file's module docstring (2026-09-29 review fix, finding #1). The event's own `id`
      // (UUIDv7) is only a unique INDEX now, used for `get`/`remove`/dedupe-on-requeue
      // lookups, never for ordering.
      const store = db.objectStoreNames.contains(STORE_NAME)
        ? req.transaction!.objectStore(STORE_NAME)
        : db.createObjectStore(STORE_NAME, { keyPath: 'seq', autoIncrement: true })
      if (!store.indexNames.contains(BY_ID_INDEX)) {
        store.createIndex(BY_ID_INDEX, 'id', { unique: true })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
  })
}

function reqToPromise<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed'))
  })
}

function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
  })
}

/** The real, persisting outbox store (Story 2.11): a single IndexedDB object store, keyed
 * by an auto-incrementing `seq` (true insertion order) with a unique index on the event's
 * own `id`. A tablet closed mid-Session and reopened later still has its queue -- IndexedDB
 * persists across a browser/PWA restart (Boundaries & Constraints). `dbName` is overridable
 * for test isolation (`outboxStore.indexeddb.test.ts`); app code always uses the default. */
export class IndexedDBOutboxStore implements OutboxStore {
  private dbPromise: Promise<IDBDatabase> | null = null
  private readonly dbName: string

  constructor(dbName: string = DB_NAME) {
    this.dbName = dbName
  }

  private db(): Promise<IDBDatabase> {
    this.dbPromise ??= openDb(this.dbName)
    return this.dbPromise
  }

  async add(item: QueuedItem): Promise<void> {
    const db = await this.db()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    // Re-queuing an id already present must overwrite IN PLACE (same `seq`/position), never
    // append a duplicate at the end -- look up its existing `seq` via the `byId` index first.
    const existingSeq = await reqToPromise(store.index(BY_ID_INDEX).getKey(item.id))
    if (existingSeq === undefined) {
      store.add(item)
    } else {
      store.put({ ...item, seq: existingSeq })
    }
    // 2026-09-29 review fix (finding #4): await the transaction's own `oncomplete`/`onerror`
    // (not just a same-transaction `get()`, which can resolve before the write is durably
    // committed) -- consistent with `remove()`'s already-correct pattern below.
    await txDone(tx)
  }

  async listAll(): Promise<QueuedItem[]> {
    const db = await this.db()
    const tx = db.transaction(STORE_NAME, 'readonly')
    const stored = await reqToPromise<(QueuedItem & { seq: number })[]>(tx.objectStore(STORE_NAME).getAll())
    // `getAll()` on a store keyed by an autoIncrement `seq` already returns records in true
    // insertion order -- no sort needed (or safe to add back; see module docstring). Strip
    // the internal `seq` key so callers see the same `QueuedItem` shape as `MemoryOutboxStore`.
    return stored.map((s) => {
      const item: Partial<QueuedItem & { seq: number }> = { ...s }
      delete item.seq
      return item as QueuedItem
    })
  }

  async remove(id: string): Promise<void> {
    const db = await this.db()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const key = await reqToPromise(store.index(BY_ID_INDEX).getKey(id))
    if (key !== undefined) store.delete(key)
    await txDone(tx)
  }

  async count(): Promise<number> {
    const db = await this.db()
    const tx = db.transaction(STORE_NAME, 'readonly')
    return reqToPromise(tx.objectStore(STORE_NAME).count())
  }
}

/** `IndexedDBOutboxStore` when the browser genuinely has `indexedDB` (every real
 * Service-Worker-capable browser); `MemoryOutboxStore` otherwise (private-mode browsers
 * that block it, or this repo's jsdom test environment). */
export function createOutboxStore(): OutboxStore {
  if (typeof indexedDB === 'undefined') return new MemoryOutboxStore()
  return new IndexedDBOutboxStore()
}
