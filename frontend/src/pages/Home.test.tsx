import { act, fireEvent, screen, waitFor } from '@testing-library/react'
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
const HOME_WITH_CONTINUE = {
  status: 200,
  body: {
    profile_id: 'p1',
    grade: 1,
    lesson: null,
    continue_session: { session_id: 'session-9' },
  },
}
const HOME_WITH_STARS_STREAK = {
  status: 200,
  body: { profile_id: 'p1', grade: 1, lesson: null, total_stars: 12, streak: 3 },
}

const HOME_WITH_RETRY_DUE = {
  status: 200,
  body: { profile_id: 'p1', grade: 1, lesson: null, retry_due_count: 2 },
}

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

  it('shows an error with retry when the Home lesson fetch fails', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': { status: 502 },
    })
    renderAt('/', <Home />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('button', { name: 'Học tiếp' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('redirects to /setup when there are zero profiles despite setup_required: false', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: [] },
    })
    renderAt('/', <Home />)
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })

  it('"Học tiếp" starts a Session and navigates to it; "Sách" navigates to the Library', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
      'POST /api/v1/sessions': {
        status: 201,
        body: {
          id: 'session-1',
          profile_id: 'p1',
          ref_kind: 'lesson',
          problem_ids: ['toan1-2020-q1.tuan-5.tiet-2.bai-1'],
          chunk_size: 10,
          mode: 'practice',
          started_at: '2026-09-28T10:00:00+00:00',
        },
      },
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Học tiếp' }))
    expect(await screen.findByText('session player screen')).toBeInTheDocument()
  })

  it('shows an error when starting a Session fails', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
      'POST /api/v1/sessions': { status: 502 },
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Học tiếp' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
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

  it('shows "Tiếp tục" when an unfinished Session exists, navigating straight to it', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_CONTINUE,
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Tiếp tục' }))
    expect(await screen.findByText('session player screen')).toBeInTheDocument()
  })

  it('a long-press on "Tiếp tục" speaks the label and does not navigate (Story 2.11 review fix, finding #7)', async () => {
    const { speak } = await import('../audio/speech')
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_CONTINUE,
    })
    renderAt('/', <Home />)
    const card = await screen.findByRole('button', { name: 'Tiếp tục' })
    vi.useFakeTimers()
    fireEvent.pointerDown(card)
    vi.advanceTimersByTime(600)
    fireEvent.pointerUp(card)
    fireEvent.click(card) // browsers still fire a click after a long-press pointerup
    expect(speak).toHaveBeenCalledWith('Tiếp tục')
    expect(screen.queryByText('session player screen')).not.toBeInTheDocument()
    vi.useRealTimers()
  })

  it('shows "Luyện lại" only when retry items are due, and starts a retry Session (Story 3.3)', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_RETRY_DUE,
      'POST /api/v1/sessions': {
        status: 201,
        body: {
          id: 'session-r',
          profile_id: 'p1',
          ref_kind: 'retry',
          problem_ids: ['a', 'b'],
          chunk_size: 10,
          mode: 'retry',
          started_at: '2026-09-29T10:00:00+00:00',
        },
      },
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Luyện lại' }))
    expect(await screen.findByText('session player screen')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      ref: { kind: 'retry' },
      mode: 'retry',
    })
  })

  it('does not show "Luyện lại" when nothing is due', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    await screen.findByTestId('home-empty')
    expect(screen.queryByRole('button', { name: 'Luyện lại' })).not.toBeInTheDocument()
  })

  it('does not show "Tiếp tục" when there is no unfinished Session', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    await screen.findByTestId('home-empty')
    expect(screen.queryByRole('button', { name: 'Tiếp tục' })).not.toBeInTheDocument()
  })

  it('shows the total Stars and Streak (Story 3.1) when either is non-zero', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_WITH_STARS_STREAK,
    })
    renderAt('/', <Home />)
    const banner = await screen.findByTestId('home-stars-streak')
    expect(banner).toHaveTextContent('12')
    expect(banner).toHaveTextContent('3')
  })

  it('shows the latest 3 earned badges (Story 3.2) as small medals on Home', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': {
        status: 200,
        body: { profile_id: 'p1', grade: 1, lesson: null, recent_badges: ['stars100', 'week1'] },
      },
    })
    renderAt('/', <Home />)
    const row = await screen.findByTestId('home-recent-badges')
    expect(row).toBeInTheDocument()
    expect(screen.getByTestId('badge-stars100')).toBeInTheDocument()
    expect(screen.getByTestId('badge-week1')).toBeInTheDocument()
  })

  it('shows no recent-badges row when none are earned', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    await screen.findByTestId('home-empty')
    expect(screen.queryByTestId('home-recent-badges')).not.toBeInTheDocument()
  })

  it('"Huy hiệu của em" card navigates to /badges', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    fireEvent.click(await screen.findByRole('button', { name: 'Huy hiệu của em' }))
    expect(await screen.findByText('badges screen')).toBeInTheDocument()
  })

  it('shows no Star/Streak banner when both are zero', async () => {
    mockApi({
      'GET /api/v1/setup/status': SETUP_OK,
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/home/p1': HOME_EMPTY,
    })
    renderAt('/', <Home />)
    await screen.findByTestId('home-empty')
    expect(screen.queryByTestId('home-stars-streak')).not.toBeInTheDocument()
  })

  describe('parent lock', () => {
    async function renderHome() {
      mockApi({
        'GET /api/v1/setup/status': SETUP_OK,
        'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
        'GET /api/v1/library/home/p1': HOME_EMPTY,
      })
      renderAt('/', <Home />)
      return screen.findByRole('button', { name: /Khu vực phụ huynh/ })
    }

    it('opens the PIN gate only after a 2 second hold', async () => {
      const lock = await renderHome()
      vi.useFakeTimers()
      try {
        fireEvent.pointerDown(lock)
        act(() => void vi.advanceTimersByTime(1900))
        expect(screen.queryByText('login screen')).not.toBeInTheDocument()
        act(() => void vi.advanceTimersByTime(200))
      } finally {
        vi.useRealTimers()
      }
      expect(await screen.findByText('login screen')).toBeInTheDocument()
    })

    it('does nothing on a short tap or a click', async () => {
      const lock = await renderHome()
      vi.useFakeTimers()
      try {
        fireEvent.pointerDown(lock)
        act(() => void vi.advanceTimersByTime(1000))
        fireEvent.pointerUp(lock)
        fireEvent.click(lock)
        act(() => void vi.advanceTimersByTime(3000))
      } finally {
        vi.useRealTimers()
      }
      expect(screen.queryByText('login screen')).not.toBeInTheDocument()
    })
  })

  describe('Bài hôm nay card', () => {
    const CARD = {
      id: 'as1',
      book_id: 'toan1-2020-q1',
      book_title_vi: 'Toán 1',
      unit_key: 'tuan-5',
      lesson_key: 'tiet-2',
      lesson_label: 'Tiết 2',
      lesson_title: '',
      assigned_date: '2026-09-30',
      status: 'todo',
      carried_over: false,
    }
    const homeWith = (assignment: unknown) => ({
      status: 200,
      body: { ...HOME_WITH_LESSON.body, assignment },
    })
    const sessionReply = {
      status: 201,
      body: {
        id: 'session-a',
        profile_id: 'p1',
        ref_kind: 'lesson',
        problem_ids: ['x'],
        chunk_size: 10,
        mode: 'practice',
        started_at: '2026-09-30T05:00:00+00:00',
      },
    }

    it('comes before Học tiếp and starts a Session linked to the Assignment', async () => {
      const fetchMock = mockApi({
        'GET /api/v1/setup/status': SETUP_OK,
        'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
        'GET /api/v1/library/home/p1': homeWith(CARD),
        'POST /api/v1/sessions': sessionReply,
      })
      renderAt('/', <Home />)
      const card = await screen.findByRole('button', { name: /^⭐?\s*Bài hôm nay/ })
      const keep = screen.getByRole('button', { name: 'Học tiếp' })
      expect(card.compareDocumentPosition(keep) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(screen.queryByTestId('home-assignment-ribbon')).not.toBeInTheDocument()
      fireEvent.click(card)
      expect(await screen.findByText('session player screen')).toBeInTheDocument()
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post?.[1]?.body as string).assignment_id).toBe('as1')
    })

    it('shows the Hôm qua ribbon and resumes the linked Session with Phần i/n', async () => {
      mockApi({
        'GET /api/v1/setup/status': SETUP_OK,
        'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
        'GET /api/v1/library/home/p1': homeWith({
          ...CARD,
          assigned_date: '2026-09-29',
          carried_over: true,
          status: 'doing',
          part: 2,
          part_count: 2,
          session_id: 'session-9',
        }),
      })
      renderAt('/', <Home />)
      expect(await screen.findByTestId('home-assignment-ribbon')).toHaveTextContent('Hôm qua')
      const card = screen.getByRole('button', { name: /^⭐?\s*Bài hôm nay/ })
      expect(card).toHaveTextContent('Phần 2/2')
      fireEvent.click(card)
      expect(await screen.findByText('session player screen')).toBeInTheDocument()
    })

    it('is absent when nothing is assigned', async () => {
      mockApi({
        'GET /api/v1/setup/status': SETUP_OK,
        'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
        'GET /api/v1/library/home/p1': HOME_WITH_LESSON,
      })
      renderAt('/', <Home />)
      expect(await screen.findByRole('button', { name: 'Học tiếp' })).toBeInTheDocument()
      expect(screen.queryByTestId('home-assignment')).not.toBeInTheDocument()
    })
  })
})
