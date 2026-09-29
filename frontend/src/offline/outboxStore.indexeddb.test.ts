// Direct tests against `IndexedDBOutboxStore` -- the actual, real persistence mechanism
// this story exists to deliver (Story 2.11 review fix, finding #2: this store previously
// had ZERO test coverage; every prior outbox test exercised `MemoryOutboxStore` only, which
// would NOT survive a real page reload). `fake-indexeddb/auto` polyfills a real, spec-
// compliant `indexedDB` global into this file's jsdom environment ONLY (imported here, not
// in `src/test/setup.ts`, so every other test file's `typeof indexedDB === 'undefined'`
// assumption -- e.g. `outboxStore.test.ts`'s `createOutboxStore` fallback test -- is
// unaffected).
import 'fake-indexeddb/auto'
import { describe, expect, it } from 'vitest'
import { IndexedDBOutboxStore, type QueuedItem } from './outboxStore'

function item(id: string, overrides: Partial<QueuedItem> = {}): QueuedItem {
  return {
    id,
    sessionId: 'session-1',
    profileId: 'profile-1',
    event: {
      id,
      kind: 'attempt',
      problem_id: 'p1',
      payload: {},
      occurred_at: '2026-09-29T00:00:00Z',
    },
    ...overrides,
  }
}

// Each test gets its own IndexedDB database name so tests never see each other's data --
// `fake-indexeddb`'s global `indexedDB` persists databases for the lifetime of the module,
// same as a real browser would across store instances within one page session.
let dbCounter = 0
function freshDbName(): string {
  dbCounter += 1
  return `hoctap-outbox-test-${dbCounter}`
}

describe('IndexedDBOutboxStore', () => {
  it('starts empty', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    expect(await store.count()).toBe(0)
    expect(await store.listAll()).toEqual([])
  })

  it('add() then listAll()/count() reflect the added item', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    await store.add(item('a'))
    expect(await store.count()).toBe(1)
    expect(await store.listAll()).toEqual([item('a')])
  })

  it('remove() deletes exactly the named item', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    await store.add(item('a'))
    await store.add(item('b'))
    await store.remove('a')
    expect((await store.listAll()).map((i) => i.id)).toEqual(['b'])
    expect(await store.count()).toBe(1)
  })

  it('remove() of an absent id is a no-op, not an error', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    await expect(store.remove('nope')).resolves.toBeUndefined()
  })

  it('add() with an id already present overwrites in place, never duplicating', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    await store.add(item('a', { profileId: 'first' }))
    await store.add(item('a', { profileId: 'second' }))
    const items = await store.listAll()
    expect(items).toHaveLength(1)
    expect(items[0].profileId).toBe('second')
  })

  it('lists items in true insertion order, never sorted by id (2026-09-29 review fix, finding #1)', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    // Ids deliberately NOT in sorted order -- confirms ordering is by insertion (the
    // auto-incrementing `seq` key), never a lexicographic sort of `id`/UUIDv7.
    await store.add(item('z-third'))
    await store.add(item('a-first'))
    await store.add(item('m-second'))
    expect((await store.listAll()).map((i) => i.id)).toEqual(['z-third', 'a-first', 'm-second'])
  })

  it('preserves insertion order when 3+ events are queued in the same synchronous tick', async () => {
    // Models events queued within the same UUIDv7 millisecond -- `Promise.all` fires each
    // `add()` synchronously in array order, so the resulting order must match the array
    // literal, not a re-sort of the ids.
    const store = new IndexedDBOutboxStore(freshDbName())
    const ids = ['q1', 'q2', 'q3', 'q4']
    await Promise.all(ids.map((id) => store.add(item(id))))
    expect((await store.listAll()).map((i) => i.id)).toEqual(ids)
  })

  it('re-queuing an existing id overwrites its value WITHOUT moving its position', async () => {
    const store = new IndexedDBOutboxStore(freshDbName())
    await store.add(item('a'))
    await store.add(item('b'))
    await store.add(item('c'))
    await store.add(item('a', { profileId: 'updated' })) // re-queue 'a'
    const items = await store.listAll()
    expect(items.map((i) => i.id)).toEqual(['a', 'b', 'c'])
    expect(items[0].profileId).toBe('updated')
  })

  it('a FRESH store instance reads items a DIFFERENT prior instance wrote -- survives a close/reopen', async () => {
    // This is the actual "survives a browser/PWA close and reopen" behavior the story
    // requires: the app closing and reopening constructs a brand-new `IndexedDBOutboxStore`
    // instance (see `outbox.ts`'s `defaultOutboxStore()` singleton, reset on each app
    // launch), so persistence across store INSTANCES -- not just across calls on the same
    // instance -- is what actually matters here.
    const dbName = freshDbName()
    const writer = new IndexedDBOutboxStore(dbName)
    await writer.add(item('a'))
    await writer.add(item('b'))

    const reader = new IndexedDBOutboxStore(dbName)
    expect(await reader.count()).toBe(2)
    expect((await reader.listAll()).map((i) => i.id)).toEqual(['a', 'b'])

    // And a write from the fresh instance is itself visible from yet another fresh one,
    // confirming the persistence isn't a one-way/one-shot artifact of the first reopen.
    await reader.remove('a')
    const thirdInstance = new IndexedDBOutboxStore(dbName)
    expect((await thirdInstance.listAll()).map((i) => i.id)).toEqual(['b'])
  })
})
