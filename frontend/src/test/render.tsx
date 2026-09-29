import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'

/**
 * Renders `element` at `path` inside a (data) router with stub screens for redirect
 * targets. `pattern` is the route path (e.g. with `:params`); it defaults to `path`.
 */
export function renderAt(path: string, element: ReactElement, pattern: string = path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const stubs = [
    { path: '/setup', element: <p>setup screen</p> },
    { path: '/parent', element: <p>parent screen</p> },
    { path: '/parent/login', element: <p>login screen</p> },
    { path: '/parent/review', element: <p>review screen</p> },
    { path: '/parent/dashboard', element: <p>dashboard screen</p> },
    { path: '/parent/settings', element: <p>settings screen</p> },
    { path: '/', element: <p>home screen</p> },
    { path: '/library', element: <p>library screen</p> },
    { path: '/library/:bookId/:unitKey/:lessonKey', element: <p>lesson detail screen</p> },
    { path: '/badges', element: <p>badges screen</p> },
    { path: '/sessions/:sessionId', element: <p>session player screen</p> },
  ].filter((s) => s.path !== pattern)
  const router = createMemoryRouter([{ path: pattern, element }, ...stubs], {
    initialEntries: [path],
  })
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, router, client }
}

type Reply = { status: number; body?: unknown }

/**
 * Stubs fetch with a reply per `METHOD /api/v1/path` (the query string is ignored unless
 * the key includes it); unknown requests get a 404.
 */
export function mockApi(replies: Record<string, Reply>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const reply = replies[`${method} ${url}`] ??
      replies[`${method} ${url.split('?')[0]}`] ?? {
        status: 404,
        body: { error: { code: 'NOT_FOUND', message: 'Không tìm thấy.' } },
      }
    if (reply.body === undefined) return new Response(null, { status: reply.status })
    return new Response(JSON.stringify(reply.body), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
