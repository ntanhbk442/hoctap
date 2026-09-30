import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { gateReport } from '../test/gateFixtures'
import { mockApi, renderAt } from '../test/render'
import ParentHome from './ParentHome'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ParentHome', () => {
  it('shows the Parent Area and logs out', async () => {
    mockApi({
      'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } },
      'GET /api/v1/build/gate': { status: 200, body: gateReport() },
      'POST /api/v1/parent/logout': { status: 204 },
    })
    renderAt('/parent', <ParentHome />)
    expect(screen.getByRole('heading', { name: 'Khu vực phụ huynh' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Chạy thử & đánh giá' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Duyệt chạy toàn bộ' })).toBeDisabled()
    expect(await screen.findByRole('link', { name: 'Giao bài' })).toHaveAttribute('href', '/parent/assignments')
    expect(await screen.findByRole('link', { name: 'Cài đặt' })).toHaveAttribute('href', '/parent/settings')
    expect(await screen.findByRole('heading', { name: 'In phiếu' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })

  it('stays on the page and shows an error when logout fails', async () => {
    mockApi({
      'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } },
      'GET /api/v1/build/gate': { status: 200, body: gateReport() },
      'POST /api/v1/parent/logout': { status: 502 },
    })
    renderAt('/parent', <ParentHome />)
    fireEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    expect(screen.queryByText('login screen')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đăng xuất' })).toBeInTheDocument()
  })

  it('offers a retry for a non-auth session error', async () => {
    mockApi({ 'GET /api/v1/parent/session': { status: 502 } })
    renderAt('/parent', <ParentHome />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } },
      'GET /api/v1/build/gate': { status: 200, body: gateReport() },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('button', { name: 'Đăng xuất' })).toBeInTheDocument()
  })

  it('redirects to the login screen when the session expired', async () => {
    mockApi({
      'GET /api/v1/parent/session': {
        status: 401,
        body: { error: { code: 'UNAUTHORIZED', message: 'Cần nhập mã PIN.' } },
      },
    })
    renderAt('/parent', <ParentHome />)
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })

  it('redirects to setup before the first run', async () => {
    mockApi({
      'GET /api/v1/parent/session': {
        status: 403,
        body: { error: { code: 'SETUP_REQUIRED', message: 'Cần thiết lập mã PIN trước.' } },
      },
    })
    renderAt('/parent', <ParentHome />)
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })
})
