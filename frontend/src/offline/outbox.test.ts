import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventIn } from '../api/client'
import { mockApi } from '../test/render'
import { flushOutbox, postEventsOrQueue, QueuedOfflineError } from './outbox'
import { MemoryOutboxStore } from './outboxStore'

const SESSION_ID = 'session-1'
const PROFILE_ID = 'profile-1'

function attemptEvent(id: string): EventIn {
  return {
    id,
    kind: 'attempt',
    problem_id: 'p1',
    payload: { part_key: 'a', value: { key: 's1', value: '5' } },
    occurred_at: '2026-09-29T00:00:00Z',
  }
}

function eventOut(id: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id,
    session_id: SESSION_ID,
    kind: 'attempt',
    problem_id: 'p1',
    occurred_at: '2026-09-29T00:00:00Z',
    received_at: '2026-09-29T00:00:01Z',
    correct: true,
    wrong_keys: [],
    hint: null,
    solution: null,
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// stubs `fetch` to reject (simulate a genuinely unreachable server -- `NetworkError`,
// never an `ApiError`; see `api/client.ts`'s `request()`).
function stubOffline() {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
  )
}

describe('postEventsOrQueue', () => {
  it('posts normally and returns the server response when the server is reachable', async () => {
    mockApi({
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [eventOut('e1')] },
    })
    const store = new MemoryOutboxStore()
    const result = await postEventsOrQueue(store, SESSION_ID, PROFILE_ID, [attemptEvent('e1')])
    expect(result).toEqual([eventOut('e1')])
    expect(await store.count()).toBe(0)
  })

  it('a 4xx/5xx from a reachable server is rethrown as-is, never queued', async () => {
    mockApi({ 'POST /api/v1/sessions/session-1/events': { status: 502 } })
    const store = new MemoryOutboxStore()
    await expect(
      postEventsOrQueue(store, SESSION_ID, PROFILE_ID, [attemptEvent('e1')]),
    ).rejects.not.toBeInstanceOf(QueuedOfflineError)
    expect(await store.count()).toBe(0)
  })

  it('queues the FULL original request body on a genuine network failure, and throws QueuedOfflineError', async () => {
    stubOffline()
    const store = new MemoryOutboxStore()
    const event = attemptEvent('e1')
    await expect(postEventsOrQueue(store, SESSION_ID, PROFILE_ID, [event])).rejects.toBeInstanceOf(
      QueuedOfflineError,
    )
    const queued = await store.listAll()
    expect(queued).toEqual([{ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event }])
  })

  it('queues every event of a multi-event batch, in order, on a network failure', async () => {
    stubOffline()
    const store = new MemoryOutboxStore()
    await expect(
      postEventsOrQueue(store, SESSION_ID, PROFILE_ID, [attemptEvent('e1'), attemptEvent('e2')]),
    ).rejects.toBeInstanceOf(QueuedOfflineError)
    expect((await store.listAll()).map((i) => i.id)).toEqual(['e1', 'e2'])
  })

  it('never computes a local verdict -- the queued item carries no correct/wrong_keys at all', async () => {
    stubOffline()
    const store = new MemoryOutboxStore()
    await postEventsOrQueue(store, SESSION_ID, PROFILE_ID, [attemptEvent('e1')]).catch(() => {})
    const [queued] = await store.listAll()
    expect(queued.event.payload).not.toHaveProperty('correct')
  })
})

describe('flushOutbox', () => {
  it('drains an empty store as a no-op', async () => {
    const store = new MemoryOutboxStore()
    await expect(flushOutbox(store)).resolves.toBe('drained')
  })

  it('flushes strictly in FIFO order, one event at a time', async () => {
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    await store.add({ id: 'e2', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e2') })

    const order: string[] = []
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse((init?.body as string) ?? '{}')
      order.push(body.events[0].id)
      return new Response(JSON.stringify([eventOut(body.events[0].id)]), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await flushOutbox(store)
    expect(outcome).toBe('drained')
    expect(order).toEqual(['e1', 'e2'])
    expect(await store.count()).toBe(0)
  })

  it('removes an already-applied (idempotent replay) event with no error surfaced', async () => {
    // The backend's idempotency (`post_event()`) returns a normal success response for a
    // resend of an already-stored event id -- indistinguishable, from this module's point
    // of view, from a fresh success. Modelled here the same way: a normal 201.
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    mockApi({
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [eventOut('e1')] },
    })
    await expect(flushOutbox(store)).resolves.toBe('drained')
    expect(await store.count()).toBe(0)
  })

  it('stops at the first failure, leaving that item and later items queued (never reordered)', async () => {
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    await store.add({ id: 'e2', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e2') })
    mockApi({ 'POST /api/v1/sessions/session-1/events': { status: 422 } })

    const outcome = await flushOutbox(store)
    expect(outcome).toBe('stopped')
    expect((await store.listAll()).map((i) => i.id)).toEqual(['e1', 'e2'])
  })

  it('stops (still offline) without removing anything, when the network is unreachable', async () => {
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    stubOffline()

    const outcome = await flushOutbox(store)
    expect(outcome).toBe('stopped')
    expect(await store.count()).toBe(1)
  })

  it('flushes 3+ events queued in the same synchronous tick in the exact order they were added (2026-09-29 review fix, finding #1)', async () => {
    // Models events sharing the same UUIDv7 millisecond (the only guarantee UUIDv7 gives)
    // by using ids that are deliberately NOT lexicographically sorted, and queuing them all
    // via `Promise.all` in one synchronous tick -- if ordering ever regressed to a sort of
    // the event id, this would flush in the wrong ('id1' < 'id2' < 'id3') order instead.
    const store = new MemoryOutboxStore()
    const ids = ['id-charlie', 'id-alpha', 'id-bravo']
    await Promise.all(
      ids.map((id) => store.add({ id, sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent(id) })),
    )

    const order: string[] = []
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse((init?.body as string) ?? '{}')
      order.push(body.events[0].id)
      return new Response(JSON.stringify([eventOut(body.events[0].id)]), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    expect(await flushOutbox(store)).toBe('drained')
    expect(order).toEqual(ids)
  })

  it('partial success: removes a succeeding first event, stops at a failing second, leaving it and later items queued (Story 2.11 review fix, finding #7)', async () => {
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    await store.add({ id: 'e2', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e2') })
    await store.add({ id: 'e3', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e3') })

    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse((init?.body as string) ?? '{}')
      const id = body.events[0].id
      if (id === 'e1') {
        return new Response(JSON.stringify([eventOut('e1')]), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(null, { status: 422 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await flushOutbox(store)
    expect(outcome).toBe('stopped')
    expect((await store.listAll()).map((i) => i.id)).toEqual(['e2', 'e3'])
  })

  it('a later flush resumes from the same (still-queued) spot, never skipping ahead', async () => {
    const store = new MemoryOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    await store.add({ id: 'e2', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e2') })
    mockApi({ 'POST /api/v1/sessions/session-1/events': { status: 502 } })
    expect(await flushOutbox(store)).toBe('stopped')
    expect(await store.count()).toBe(2)

    const order: string[] = []
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse((init?.body as string) ?? '{}')
      order.push(body.events[0].id)
      return new Response(JSON.stringify([eventOut(body.events[0].id)]), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    expect(await flushOutbox(store)).toBe('drained')
    expect(order).toEqual(['e1', 'e2'])
  })
})
