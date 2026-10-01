import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, apiGet, apiPost } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubFetch(impl: () => Promise<Response>) {
  const fetchMock = vi.fn(impl)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('apiGet', () => {
  it('maps a JSON error body without `error` to HTTP_ERROR', async () => {
    stubFetch(async () =>
      new Response(JSON.stringify({ detail: 'nope' }), {
        status: 400,
        statusText: 'Bad Request',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const err = await apiGet('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 400, code: 'HTTP_ERROR', message: 'Bad Request' })
  })

  it('maps the error envelope', async () => {
    stubFetch(async () =>
      new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Không tìm thấy.' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await expect(apiGet('/x')).rejects.toMatchObject({ code: 'NOT_FOUND', status: 404 })
  })

  it('wraps a genuine network failure (fetch throwing) in NetworkError, distinct from ApiError', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })
    const err = await apiGet('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(NetworkError)
    expect(err).not.toBeInstanceOf(ApiError)
    expect((err as NetworkError).cause).toBeInstanceOf(TypeError)
  })

  it('wraps a stalled/never-resolving fetch in NetworkError once the request signal aborts (Review Triage Log #8)', async () => {
    // `AbortSignal.timeout()` is implemented via Node/browser internals that vitest's fake
    // timers cannot advance (it never goes through the patched global `setTimeout`), so this
    // test can't simulate the real 12s wait directly. Instead it spies on
    // `AbortSignal.timeout()` itself to substitute a signal this test fully controls,
    // proving `request()` really wires ITS timeout signal into `fetch()` -- aborting that
    // exact signal is what must turn a hung `fetch()` into a `NetworkError`, not just that
    // SOME promise eventually rejects.
    const controller = new AbortController()
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal)
    try {
      let capturedSignal: AbortSignal | undefined
      const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          capturedSignal = init?.signal ?? undefined
          capturedSignal?.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted.', 'TimeoutError'))
          })
        })
      })
      vi.stubGlobal('fetch', fetchMock)
      const pending = apiGet('/x').catch((e: unknown) => e)
      controller.abort(new DOMException('The operation timed out.', 'TimeoutError'))
      const err = await pending
      expect(err).toBeInstanceOf(NetworkError)
      expect(err).not.toBeInstanceOf(ApiError)
      expect(capturedSignal?.aborted).toBe(true)
    } finally {
      timeoutSpy.mockRestore()
    }
  })

  it('returns undefined for 204 and non-JSON success', async () => {
    stubFetch(async () => new Response(null, { status: 204 }))
    await expect(apiGet('/x')).resolves.toBeUndefined()
    stubFetch(async () => new Response('hi', { status: 200, headers: { 'Content-Type': 'text/plain' } }))
    await expect(apiGet('/x')).resolves.toBeUndefined()
  })

  it('keeps caller headers passed as a Headers instance', async () => {
    const fetchMock = stubFetch(async () =>
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    await apiGet('/x', { headers: new Headers({ 'X-Test': '1' }) })
    const headers = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Headers
    expect(headers.get('X-Test')).toBe('1')
    expect(headers.get('Accept')).toBe('application/json')
  })
})

describe('apiPost', () => {
  it('sends POST with a JSON body and Content-Type', async () => {
    const fetchMock = stubFetch(async () => new Response(null, { status: 204 }))
    await apiPost('/parent/login', { pin: '1234' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/parent/login')
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe('{"pin":"1234"}')
  })

  it('sends no Content-Type and no body without a body', async () => {
    const fetchMock = stubFetch(async () => new Response(null, { status: 204 }))
    await apiPost('/parent/logout')
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).has('Content-Type')).toBe(false)
    expect(init.body).toBeUndefined()
  })
})
