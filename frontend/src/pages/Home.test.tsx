import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Home from './Home'

vi.mock('../audio/speech', () => ({ speak: vi.fn(() => Promise.resolve()) }))

const SETUP_OK = { status: 200, body: { setup_required: false } }
const ONE_PROFILE = [{ id: 'p1', name: 'Bin', avatar: 'cat', grade: 1 }]
const TWO_PROFILES = [
  { id: 'p1', name: 'Bin', avatar: 'cat', grade: 1 },
  { id: 'p2', name: 'An', avatar: 'dog', grade: 2 },
]
const HOME_WITH_LESSON = {
  status: 200,
  body: {
    profile_id: 'p1',
    grade: 1,
    lesson: {
      book_id: 'toan1-2020-q1',
      book_title_vi: 'Toán 1 – Quyển 1 (2020)',
      unit_key: 'tuan-5',
      lesson_key: 'tiet-2',
      lesson_label: 'Tiết 2',
      lesson_title: '',
    },
  },
}
const HOME_EMPTY = { status: 200, body: { profile_id: 'p1', grade: 1, lesson: null } }
const HOME_EMPTY_P2 = { status: 200, body: { profile_id: 'p2', grade: 2, lesson: null } }

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Home', () => {
  it('redirects to /setup when setup is required', async () => {
    mockApi({ 'GET /api/v1/setup/status': { status: 200, body: { setup_required: true } } })
    renderAt('/', <Home />)
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })

  it('shows a loading state before setup status is known', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderAt('/', <Home />)
    expect(screen.getByText('Đang tải…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Học Tập' })).not.toBeInTheDocument()
  })

  it('shows an error with retry when the setup status fails', async () => {
    const fetchMock = mockApi({ 'GET /api/v1/setup/status': { status: 502 } })
    renderAt('/', <Home />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('heading', { name: 'Học Tập' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('skips the picker and sets the only profile current, for exactly one profile', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
    })
    renderAt('/', <Home />)
    expect(await screen.findByRole('heading', { name: 'Học Tập' })).toBeInTheDocument()
    expect(screen.queryByText('Ai đang học vậy?')).not.toBeInTheDocument()
    await waitFor(() => expect(sessionStorage.getItem('hoctap.currentProfileId')).toBe('p1'))
  })

  it('shows the picker for 2+ profiles; selecting one persists it for the session', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: TWO_PROFILES },
      'GET /api/v1/library/home/p2': HOME_EMPTY_P2,
    })
    renderAt('/', <Home />)
    expect(await screen.findByText('Ai đang học vậy?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /An/ }))
    expect(await screen.findByRole('heading', { name: 'Học Tập' })).toBeInTheDocument()
    expect(sessionStorage.getItem('hoctap.currentProfileId')).toBe('p2')
  })

  it('a profile already chosen this session skips the picker on the next render', async () => {
    sessionStorage.setItem('hoctap.currentProfileId', 'p2')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: TWO_PROFILES },
      'GET /api/v1/library/home/p2': HOME_EMPTY_P2,
    })
    renderAt('/', <Home />)
    expect(await screen.findByRole('heading', { name: 'Học Tập' })).toBeInTheDocument()
    expect(screen.queryByText('Ai đang học vậy?')).not.toBeInTheDocument()
  })

  it('shows a friendly empty state, not a crash, when nothing is visible yet', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    expect(await screen.findByTestId('home-empty')).toHaveTextContent('Chưa có bài nào để học')
    expect(screen.queryByRole('button', { name: /Học tiếp/ })).not.toBeInTheDocument()
  })

  it('"Học tiếp" navigates to the resolved Lesson; "Sách" navigates to the Library', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Học tiếp' }))
    expect(await screen.findByText('lesson detail screen')).toBeInTheDocument()
  })

  it('the Library card navigates to /library', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sách' }))
    expect(await screen.findByText('library screen')).toBeInTheDocument()
  })

  it('tapping the 🔊 speaks the label without opening the card', async () => {
    const { speak } = await import('../audio/speech')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
    })
    renderAt('/', <Home />)
    const speaker = await screen.findByRole('button', { name: 'Nghe: Học tiếp' })
    fireEvent.click(speaker)
    expect(speak).toHaveBeenCalledWith('Học tiếp')
    expect(screen.queryByText('lesson detail screen')).not.toBeInTheDocument()
  })

  it('a long-press on "Học tiếp" speaks the label and does not open the card', async () => {
    const { speak } = await import('../audio/speech')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
    })
    renderAt('/', <Home />)
    const card = await screen.findByRole('button', { name: 'Học tiếp' })
    vi.useFakeTimers()
    fireEvent.pointerDown(card)
    vi.advanceTimersByTime(600)
    fireEvent.pointerUp(card)
    fireEvent.click(card) // browsers still fire a click after a long-press pointerup
    expect(speak).toHaveBeenCalledWith('Học tiếp')
    expect(screen.queryByText('lesson detail screen')).not.toBeInTheDocument()
    vi.useRealTimers()
  })

  it('links to the Parent Area', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('link', { name: 'Khu vực phụ huynh' }))
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })
})
