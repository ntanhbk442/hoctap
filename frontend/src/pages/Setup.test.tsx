import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Setup from './Setup'

const FRESH = { 'GET /api/v1/setup/status': { status: 200, body: { setup_required: true } } }

afterEach(() => {
  vi.unstubAllGlobals()
})

function fill(pin: string, confirm: string, name = 'Bin') {
  fireEvent.change(screen.getByLabelText('Mã PIN (4 chữ số)'), { target: { value: pin } })
  fireEvent.change(screen.getByLabelText('Nhập lại mã PIN'), { target: { value: confirm } })
  fireEvent.change(screen.getByLabelText('Tên'), { target: { value: name } })
  fireEvent.click(screen.getByLabelText(/Mèo/))
  fireEvent.change(screen.getByLabelText('Lớp'), { target: { value: '2' } })
}

describe('Setup', () => {
  it('shows the mismatch message and sends nothing when the PINs differ', async () => {
    const fetchMock = mockApi(FRESH)
    renderAt('/setup', <Setup />)
    fill('1234', '4321')
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Hai mã PIN không khớp')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('rejects a PIN that is not 4 digits', async () => {
    mockApi(FRESH)
    renderAt('/setup', <Setup />)
    fill('12', '12')
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Mã PIN gồm đúng 4 chữ số.')
  })

  it('submits a valid form and goes to the Parent Area', async () => {
    const fetchMock = mockApi({
      ...FRESH,
      'POST /api/v1/setup': {
        status: 201,
        body: { id: 'x', name: 'Bin', avatar: 'cat', grade: 2 },
      },
    })
    renderAt('/setup', <Setup />)
    fill('1234', '1234')
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất' }))
    expect(await screen.findByText('parent screen')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post![1]!.body as string)).toEqual({
      pin: '1234',
      pin_confirm: '1234',
      profile: { name: 'Bin', avatar: 'cat', grade: 2 },
    })
  })

  it('shows a server validation message', async () => {
    mockApi({
      ...FRESH,
      'POST /api/v1/setup': {
        status: 422,
        body: { error: { code: 'VALIDATION_ERROR', message: 'Dữ liệu không hợp lệ.' } },
      },
    })
    renderAt('/setup', <Setup />)
    fill('1234', '1234')
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất' }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Dữ liệu không hợp lệ.'),
    )
  })

  it('redirects to the Parent Area when setup is already done', async () => {
    mockApi({ 'GET /api/v1/setup/status': { status: 200, body: { setup_required: false } } })
    renderAt('/setup', <Setup />)
    expect(await screen.findByText('parent screen')).toBeInTheDocument()
  })

  it('goes to the login screen on 409 SETUP_DONE', async () => {
    mockApi({
      ...FRESH,
      'POST /api/v1/setup': {
        status: 409,
        body: { error: { code: 'SETUP_DONE', message: 'Ứng dụng đã được thiết lập.' } },
      },
    })
    renderAt('/setup', <Setup />)
    fill('1234', '1234')
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất' }))
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })
})
