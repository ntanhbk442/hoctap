// Coverage for `cacheBundleAssets()` (Story 2.11 review fix, finding #6 -- previously
// ZERO test coverage despite being pure, easily-testable logic). Asserts it triggers a
// `fetch()` for each of the bundle's crop/page/audio URLs (the mechanism that actually
// warms the Workbox `/assets-data/*` runtime-caching routes -- see `vite.config.ts`), and
// that it's a safe no-op outside a Service-Worker-capable environment.
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BundleOut } from '../api/client'
import { cacheBundleAssets } from './assetCache'

function bundle(): BundleOut {
  return {
    session_id: 'session-1',
    mode: 'practice',
    chunk: 1,
    chunk_count: 1,
    chunk_label: 'Phần 1/1',
    problems: [
      {
        problem: {
          schema_version: 'v1',
          problem_id: 'p1',
          book_id: 'toan1-2020-q1',
          unit_key: 'tuan-5',
          lesson_key: 'tiet-2',
          problem_label: 'bai-1',
          display_label: 'Bài 1',
          instruction: '',
          layout: 'sequence',
          source_pages: [{ page: 12, bbox: [0, 0, 1, 1] }],
          images: [],
          concept_ids: [],
          concept_proposals: [],
          parts: [],
        },
        crop_urls: ['/assets-data/crops/toan1-2020-q1/p1/_problem.jpg'],
        page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
        audio: { abc123: '/assets-data/audio/abc123.mp3' },
        attempted: false,
        done_in_session: false,
      },
      {
        problem: {
          schema_version: 'v1',
          problem_id: 'p2',
          book_id: 'toan1-2020-q1',
          unit_key: 'tuan-5',
          lesson_key: 'tiet-2',
          problem_label: 'bai-2',
          display_label: 'Bài 2',
          instruction: '',
          layout: 'sequence',
          source_pages: [{ page: 13, bbox: [0, 0, 1, 1] }],
          images: [],
          concept_ids: [],
          concept_proposals: [],
          parts: [],
        },
        crop_urls: ['/assets-data/crops/toan1-2020-q1/p2/_problem.jpg'],
        page_urls: ['/assets-data/pages/toan1-2020-q1/p013.jpg'],
        audio: { def456: '/assets-data/audio/def456.mp3' },
        attempted: false,
        done_in_session: false,
      },
      // no more chunk_count than 1, but include a second problem so we cover the "whole
      // chunk, not just the current Problem" requirement (AD-10).
    ],
  } as BundleOut
}

// jsdom's `navigator` has no `serviceWorker` by default -- `cacheBundleAssets()` is
// deliberately a no-op without it (Story 2.11: never something that should throw outside a
// Service-Worker-capable browser).
function stubServiceWorkerSupport(supported: boolean) {
  if (supported) {
    Object.defineProperty(navigator, 'serviceWorker', { value: {}, configurable: true })
  } else {
    // must be genuinely ABSENT (not merely `undefined`-valued) -- `cacheBundleAssets()`
    // checks `'serviceWorker' in navigator`, which is true even for an explicit `undefined`.
    delete (navigator as { serviceWorker?: unknown }).serviceWorker
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  delete (navigator as { serviceWorker?: unknown }).serviceWorker
})

describe('cacheBundleAssets', () => {
  it('fetches every crop/page/audio URL across all of the bundle’s problems, to warm the runtime cache', async () => {
    stubServiceWorkerSupport(true)
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)

    cacheBundleAssets(bundle())
    // the warm is fire-and-forget (`void fetch(url).catch(...)`); flush microtasks.
    await Promise.resolve()
    await Promise.resolve()

    const fetchedUrls = (fetchMock.mock.calls as unknown as [string][]).map((call) => call[0])
    expect(fetchedUrls).toEqual(
      expect.arrayContaining([
        '/assets-data/crops/toan1-2020-q1/p1/_problem.jpg',
        '/assets-data/pages/toan1-2020-q1/p012.jpg',
        '/assets-data/audio/abc123.mp3',
        '/assets-data/crops/toan1-2020-q1/p2/_problem.jpg',
        '/assets-data/pages/toan1-2020-q1/p013.jpg',
        '/assets-data/audio/def456.mp3',
      ]),
    )
    expect(fetchMock).toHaveBeenCalledTimes(6)
  })

  it('is a no-op when the browser has no serviceWorker support', async () => {
    stubServiceWorkerSupport(false)
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)

    cacheBundleAssets(bundle())
    await Promise.resolve()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('swallows a per-URL fetch failure without throwing (best-effort warm)', async () => {
    stubServiceWorkerSupport(true)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )

    expect(() => cacheBundleAssets(bundle())).not.toThrow()
    await Promise.resolve()
    await Promise.resolve()
  })
})
