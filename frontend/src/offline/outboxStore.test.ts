import { describe, expect, it } from 'vitest'
import { createOutboxStore, MemoryOutboxStore, type QueuedItem } from './outboxStore'

// This repo's test environment (jsdom, `frontend/vite.config.ts`'s `test.environment`)
// has no real IndexedDB (confirmed: no `fake-indexeddb` dependency in `package.json`
// either), so these tests exercise `MemoryOutboxStore` -- the SAME store code a
// private-mode browser's `createOutboxStore()` would fall back to, not a mock written only
// for tests (see this file's own module docstring in `outboxStore.ts`). The `OutboxStore`
// interface both implementations share is what `outbox.test.ts` depends on for its own
// injectable-store testing.

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

describe('MemoryOutboxStore', () => {
  it('starts empty', async () => {
    const store = new MemoryOutboxStore()
    expect(await store.count()).toBe(0)
    expect(await store.listAll()).toEqual([])
  })

  it('lists items in true insertion order, never sorted by id', async () => {
    // 2026-09-29 review fix (finding #1): two events can share a UUIDv7 millisecond
    // prefix and still sort "wrong" lexicographically -- ordering must be insertion
    // order, not an `id` sort. Inserting ids that would sort differently than they were
    // added confirms this store never falls back to sorting by `id`.
    const store = new MemoryOutboxStore()
    await store.add(item('b'))
    await store.add(item('a'))
    await store.add(item('c'))
    expect((await store.listAll()).map((i) => i.id)).toEqual(['b', 'a', 'c'])
  })

  it('preserves 3+ events queued in the same synchronous tick in the exact order added', async () => {
    // Simulates three events sharing the same millisecond (UUIDv7's only guaranteed
    // ordering granularity) by using ids that are NOT lexicographically sorted -- if
    // this store ever regresses to sorting by id, this test catches it.
    const store = new MemoryOutboxStore()
    const ids = ['z-third', 'a-first', 'm-second']
    await Promise.all(ids.map((id) => store.add(item(id))))
    // Promise.all preserves call order for synchronously-issued async calls that each
    // resolve immediately (MemoryOutboxStore.add is synchronous under the hood), so the
    // resulting order should match the array literal's order, not a re-sort of the ids.
    expect((await store.listAll()).map((i) => i.id)).toEqual(ids)
  })

  it('add() with an id already present overwrites in place, never duplicating', async () => {
    const store = new MemoryOutboxStore()
    await store.add(item('a', { profileId: 'first' }))
    await store.add(item('a', { profileId: 'second' }))
    const items = await store.listAll()
    expect(items).toHaveLength(1)
    expect(items[0].profileId).toBe('second')
  })

  it('remove() deletes exactly the named item', async () => {
    const store = new MemoryOutboxStore()
    await store.add(item('a'))
    await store.add(item('b'))
    await store.remove('a')
    expect((await store.listAll()).map((i) => i.id)).toEqual(['b'])
    expect(await store.count()).toBe(1)
  })

  it('remove() of an absent id is a no-op, not an error', async () => {
    const store = new MemoryOutboxStore()
    await expect(store.remove('nope')).resolves.toBeUndefined()
  })
})

describe('createOutboxStore', () => {
  it('falls back to MemoryOutboxStore when indexedDB is unavailable (this test env)', () => {
    // jsdom (this repo's test environment) has no real IndexedDB -- asserting this
    // directly documents WHY `outbox.test.ts` injects `MemoryOutboxStore` rather than
    // exercising `IndexedDBOutboxStore`.
    if (typeof indexedDB !== 'undefined') return
    expect(createOutboxStore()).toBeInstanceOf(MemoryOutboxStore)
  })
})
