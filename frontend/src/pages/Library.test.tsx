import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Library from './Library'

const ONE_PROFILE = [{ id: 'p1', name: 'Bin', avatar: 'cat', grade: 1 }]

const BOOKS = [
  {
    book_id: 'toan1-2020-q1',
    edition: '2020',
    grade: 1,
    volume: 1,
    title_vi: 'Toán 1 – Quyển 1 (2020)',
    units: [
      {
        unit_key: 'tuan-5',
        label: 'TUẦN 5',
        title: '',
        position: 500,
        lessons: [
          {
            lesson_key: 'tiet-2',
            label: 'Tiết 2',
            title: '',
            position: 501,
            problem_count: 3,
            attempted: 0,
          },
        ],
      },
    ],
  },
  {
    book_id: 'toan1-2024-t1',
    edition: '2024-25',
    grade: 1,
    volume: 1,
    title_vi: 'Toán 1 – Tập 1 (2024–25)',
    units: [],
  },
]

beforeEach(() => {
  sessionStorage.clear()
  sessionStorage.setItem('hoctap.currentProfileId', 'p1')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Library', () => {
  it('shows every Book of the current profile Grade, both Editions, with progress', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByText('Toán 1 – Quyển 1 (2020)')).toBeInTheDocument()
    expect(screen.getByText('Toán 1 – Tập 1 (2024–25)')).toBeInTheDocument()
    expect(screen.getByText('0/3 ✓')).toBeInTheDocument()
  })

  it('shows a real "done at least once" numerator (Story 2.4)', async () => {
    const withProgress = structuredClone(BOOKS)
    withProgress[0].units[0].lessons[0].attempted = 2
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: withProgress },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByText('2/3 ✓')).toBeInTheDocument()
  })

  it('tapping a Lesson opens its Lesson detail route', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
    })
    renderAt('/library', <Library />)
    fireEvent.click(await screen.findByRole('button', { name: /Tiết 2/ }))
    expect(await screen.findByText('lesson detail screen')).toBeInTheDocument()
  })

  it('shows a loading state while the Books are being fetched', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/v1/profiles') {
        return new Response(JSON.stringify(ONE_PROFILE), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Promise<Response>(() => {}) // books: never resolves
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/library', <Library />)
    expect(await screen.findByText('Đang tải…')).toBeInTheDocument()
  })

  it('shows an error with retry when the Books fetch fails', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 502 },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Toán 1 – Quyển 1 (2020)')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('shows a friendly empty state for a Grade with zero Books at all', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: [] },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByText('Chưa có sách nào cho lớp 1.')).toBeInTheDocument()
  })

  it('redirects to /setup when there are zero profiles despite setup_required: false', async () => {
    mockApi({ 'GET /api/v1/profiles': { status: 200, body: [] } })
    renderAt('/library', <Library />)
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })

  it('redirects to Home when no current profile can be resolved (2+ profiles, none picked)', async () => {
    sessionStorage.clear()
    mockApi({
      'GET /api/v1/profiles': {
        status: 200,
        body: [...ONE_PROFILE, { id: 'p2', name: 'An', avatar: 'dog', grade: 2 }],
      },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByText('home screen')).toBeInTheDocument()
  })

  it('marks a quiz-sheet Lesson with the 📝 "Kiểm tra" indicator (Story 3.4)', async () => {
    const quiz = structuredClone(BOOKS)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(quiz[0].units[0].lessons[0] as any).is_quiz_sheet = true
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: quiz },
    })
    renderAt('/library', <Library />)
    expect(await screen.findByTestId('quiz-indicator')).toHaveTextContent('Kiểm tra')
  })

  it('shows no quiz indicator on an ordinary Lesson', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
    })
    renderAt('/library', <Library />)
    await screen.findByText('0/3 ✓')
    expect(screen.queryByTestId('quiz-indicator')).not.toBeInTheDocument()
  })
})
