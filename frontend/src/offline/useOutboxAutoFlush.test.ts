// Coverage for `useOutboxAutoFlush()`'s reconnect trigger (Story 2.11 review fix, finding
// #6 -- previously ZERO test anywhere dispatched a real `online` event, despite it being
// AD-10's headline reconnect mechanism).
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EventIn } from '../api/client'
import { _resetDefaultOutboxStoreForTests, defaultOutboxStore } from './outbox'
import { useOutboxAutoFlush } from './useOutboxAutoFlush'

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

function okResponse() {
  return Promise.resolve(
    new Response(JSON.stringify([]), { status: 201, headers: { 'Content-Type': 'application/json' } }),
  )
}

beforeEach(() => {
  _resetDefaultOutboxStoreForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
  _resetDefaultOutboxStoreForTests()
})

describe('useOutboxAutoFlush', () => {
  it('flushes the default outbox store when a real `online` event fires', async () => {
    const fetchMock = vi.fn(okResponse)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useOutboxAutoFlush())
    await Promise.resolve()
    // mount flush ran against an empty store -- nothing to send yet.
    expect(fetchMock).not.toHaveBeenCalled()

    const store = defaultOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    expect(await store.count()).toBe(1)

    window.dispatchEvent(new Event('online'))
    // let the async flush triggered by the event listener settle.
    await waitFor(async () => expect(await store.count()).toBe(0))

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('also flushes once on mount (e.g. a tablet relaunched already online)', async () => {
    const store = defaultOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })

    const fetchMock = vi.fn(okResponse)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useOutboxAutoFlush())
    await waitFor(async () => expect(await store.count()).toBe(0))

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('removes its `online` listener on unmount', async () => {
    const fetchMock = vi.fn(okResponse)
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = renderHook(() => useOutboxAutoFlush())
    await Promise.resolve()
    unmount()

    const store = defaultOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })
    window.dispatchEvent(new Event('online'))
    await Promise.resolve()
    await Promise.resolve()

    // no listener left to react to the event, so nothing was sent.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('calls onDrained with the flush outcome after every mount/online flush (Review Triage Log #10)', async () => {
    const store = defaultOutboxStore()
    await store.add({ id: 'e1', sessionId: SESSION_ID, profileId: PROFILE_ID, event: attemptEvent('e1') })

    const fetchMock = vi.fn(okResponse)
    vi.stubGlobal('fetch', fetchMock)
    const onDrained = vi.fn()

    renderHook(() => useOutboxAutoFlush(onDrained))
    await waitFor(() => expect(onDrained).toHaveBeenCalledWith('drained'))

    onDrained.mockClear()
    window.dispatchEvent(new Event('online'))
    await waitFor(() => expect(onDrained).toHaveBeenCalledWith('drained'))
  })
})
