import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Home from './Home'

const HEALTH = { status: 200, body: { status: 'ok', version: '0.1.0' } }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Home', () => {
  it('shows the title and the health status from /api/v1/health', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/health': HEALTH,
      'GET /api/v1/setup/status': { status: 200, body: { setup_required: false } },
    })
    renderAt('/', <Home />)
    expect(await screen.findByRole('heading', { name: 'Học Tập' })).toBeInTheDocument()
    expect(await screen.findByText('ok')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.anything())
    expect(screen.queryByText('setup screen')).not.toBeInTheDocument()
  })

  it('shows an error when the server is unreachable', async () => {
    mockApi({
      'GET /api/v1/health': {
        status: 503,
        body: { error: { code: 'SERVICE_UNAVAILABLE', message: 'x' } },
      },
      'GET /api/v1/setup/status': { status: 200, body: { setup_required: false } },
    })
    renderAt('/', <Home />)
    expect(await screen.findByText('không kết nối được máy chủ')).toBeInTheDocument()
  })

  it('shows a loading state, not the content, until the setup status is known', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderAt('/', <Home />)
    expect(screen.getByText('Đang tải…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Học Tập' })).not.toBeInTheDocument()
  })

  it('shows an error with retry when the setup status fails', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/health': HEALTH,
      'GET /api/v1/setup/status': { status: 502 },
    })
    renderAt('/', <Home />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/health': HEALTH,
      'GET /api/v1/setup/status': { status: 200, body: { setup_required: true } },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('links to the Parent Area', async () => {
    mockApi({
      'GET /api/v1/health': HEALTH,
      'GET /api/v1/setup/status': { status: 200, body: { setup_required: false } },
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('link', { name: 'Khu vực phụ huynh' }))
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })

  it('redirects to /setup when setup is required', async () => {
    mockApi({
      'GET /api/v1/health': HEALTH,
      'GET /api/v1/setup/status': { status: 200, body: { setup_required: true } },
    })
    renderAt('/', <Home />)
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })
})
