import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Settings from './Settings'

afterEach(() => {
  vi.unstubAllGlobals()
})

const SESSION = { status: 200, body: { authenticated: true } }
const P1 = { id: 'p1', name: 'Bin', avatar: 'cat', grade: 1, auto_play: true }
const P2 = { id: 'p2', name: 'An', avatar: 'dog', grade: 2, auto_play: true }
const bodyOf = (fetchMock: ReturnType<typeof mockApi>, method: string) => {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === method)
  return JSON.parse(call![1]!.body as string)
}

describe('Settings', () => {
  it('adds a profile', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
      'POST /api/v1/profiles': { status: 201, body: P2 },
    })
    renderAt('/parent/settings', <Settings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Thêm hồ sơ' }))
    fireEvent.change(screen.getByLabelText('Tên'), { target: { value: ' An ' } })
    fireEvent.click(screen.getByLabelText(/Chó/))
    fireEvent.change(screen.getByLabelText('Lớp'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Thêm' }))
    await waitFor(() =>
      expect(bodyOf(fetchMock, 'POST')).toEqual({ name: 'An', avatar: 'dog', grade: 2 }),
    )
  })

  it('hides the add button at 4 profiles and shows the limit error from the server', async () => {
    mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': {
        status: 200,
        body: [1, 2, 3, 4].map((i) => ({ ...P1, id: `p${i}`, name: `C${i}` })),
      },
    })
    renderAt('/parent/settings', <Settings />)
    expect(await screen.findByText('Đã đủ 4 hồ sơ.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thêm hồ sơ' })).not.toBeInTheDocument()
  })

  it('shows a server error when adding fails', async () => {
    mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
      'POST /api/v1/profiles': {
        status: 409,
        body: { error: { code: 'PROFILE_LIMIT', message: 'Chỉ có thể tạo tối đa 4 hồ sơ.' } },
      },
    })
    renderAt('/parent/settings', <Settings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Thêm hồ sơ' }))
    fireEvent.change(screen.getByLabelText('Tên'), { target: { value: 'An' } })
    fireEvent.click(screen.getByRole('button', { name: 'Thêm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Chỉ có thể tạo tối đa 4 hồ sơ.')
  })

  it('edits a profile', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
      'PATCH /api/v1/profiles/p1': { status: 200, body: { ...P1, name: 'Bin B' } },
    })
    renderAt('/parent/settings', <Settings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sửa hồ sơ Bin' }))
    fireEvent.change(screen.getByLabelText('Tên'), { target: { value: 'Bin B' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await waitFor(() =>
      expect(bodyOf(fetchMock, 'PATCH')).toEqual({ name: 'Bin B', avatar: 'cat', grade: 1 }),
    )
  })

  it('toggles auto-play for one child', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1, P2] },
      'PATCH /api/v1/profiles/p2': { status: 200, body: { ...P2, auto_play: false } },
    })
    renderAt('/parent/settings', <Settings />)
    fireEvent.click(await screen.findByLabelText('Tự động đọc đề của An'))
    await waitFor(() => expect(bodyOf(fetchMock, 'PATCH')).toEqual({ auto_play: false }))
  })

  it('names the child in the delete confirmation and removes on confirm', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1, P2] },
      'DELETE /api/v1/profiles/p2': { status: 204 },
    })
    renderAt('/parent/settings', <Settings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Xoá hồ sơ An' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('tiến độ học của An sẽ mất')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Giữ lại' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'DELETE')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Xoá hồ sơ An' }))
    fireEvent.click(screen.getByRole('button', { name: 'Xoá hồ sơ và tiến độ' }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'DELETE')).toBe(true),
    )
  })

  it('offers no delete for the only profile', async () => {
    mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
    })
    renderAt('/parent/settings', <Settings />)
    await screen.findByRole('button', { name: 'Sửa hồ sơ Bin' })
    expect(screen.queryByRole('button', { name: 'Xoá hồ sơ Bin' })).not.toBeInTheDocument()
  })

  it('changes the PIN and rejects a mismatch locally', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
      'POST /api/v1/parent/pin': { status: 204 },
    })
    renderAt('/parent/settings', <Settings />)
    await screen.findByRole('button', { name: 'Đổi mã PIN' })
    fireEvent.change(screen.getByLabelText('Mã PIN hiện tại'), { target: { value: '1234' } })
    fireEvent.change(screen.getByLabelText('Mã PIN mới'), { target: { value: '4321' } })
    fireEvent.change(screen.getByLabelText('Nhập lại mã PIN mới'), { target: { value: '4322' } })
    fireEvent.click(screen.getByRole('button', { name: 'Đổi mã PIN' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Hai mã PIN không khớp')
    fireEvent.change(screen.getByLabelText('Nhập lại mã PIN mới'), { target: { value: '4321' } })
    fireEvent.click(screen.getByRole('button', { name: 'Đổi mã PIN' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đã đổi mã PIN.')
    expect(bodyOf(fetchMock, 'POST')).toEqual({
      current_pin: '1234',
      new_pin: '4321',
      new_pin_confirm: '4321',
    })
  })

  it('shows a wrong-current-PIN error', async () => {
    mockApi({
      'GET /api/v1/parent/session': SESSION,
      'GET /api/v1/profiles': { status: 200, body: [P1] },
      'POST /api/v1/parent/pin': {
        status: 401,
        body: { error: { code: 'PIN_INCORRECT', message: 'Mã PIN chưa đúng' } },
      },
    })
    renderAt('/parent/settings', <Settings />)
    await screen.findByRole('button', { name: 'Đổi mã PIN' })
    fireEvent.change(screen.getByLabelText('Mã PIN hiện tại'), { target: { value: '0000' } })
    fireEvent.change(screen.getByLabelText('Mã PIN mới'), { target: { value: '4321' } })
    fireEvent.change(screen.getByLabelText('Nhập lại mã PIN mới'), { target: { value: '4321' } })
    fireEvent.click(screen.getByRole('button', { name: 'Đổi mã PIN' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Mã PIN chưa đúng')
  })

  it('redirects to login without a session', async () => {
    mockApi({
      'GET /api/v1/parent/session': {
        status: 401,
        body: { error: { code: 'UNAUTHORIZED', message: 'Cần nhập mã PIN.' } },
      },
      'GET /api/v1/profiles': { status: 200, body: [P1] },
    })
    renderAt('/parent/settings', <Settings />)
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })
})
