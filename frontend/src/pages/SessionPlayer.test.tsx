import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { _resetDefaultOutboxStoreForTests } from '../offline/outbox'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'
import SessionPlayer from './SessionPlayer'

// `speechKey` mocked as an identity function (see `ProblemPlayer.test.tsx`'s own
// docstring) so `ProblemPlayer`'s instruction audio wiring doesn't need real `crypto`
// digesting; `speak` mocked to assert the badge fanfare's exact calls deterministically.
vi.mock('../audio/speech', () => ({
  speak: vi.fn(() => Promise.resolve()),
  speechKey: vi.fn((text: string) => Promise.resolve(text)),
}))

const PROFILE_ID = 'profile-1'

const PROBLEM = {
  schema_version: 'v1',
  problem_id: 'toan1-2020-q1.tuan-5.tiet-2.bai-1',
  book_id: 'toan1-2020-q1',
  unit_key: 'tuan-5',
  lesson_key: 'tiet-2',
  problem_label: 'bai-1',
  display_label: 'Bài 1',
  instruction: 'Tính:',
  layout: 'sequence',
  source_pages: [{ page: 12, bbox: [0, 0, 1, 1] }],
  images: [],
  concept_ids: [],
  concept_proposals: [],
  parts: [
    {
      part_key: 'a',
      type: 'number_input',
      prompt: '',
      image_keys: [],
      template: '3 + 2 = [[s1]]',
      slots: [{ slot_key: 's1' }],
    },
  ],
}

function bundle(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    session_id: 'session-1',
    chunk: 1,
    chunk_count: 1,
    chunk_label: 'Phần 1/1',
    problems: [
      {
        problem: PROBLEM,
        crop_urls: ['/assets-data/crops/toan1-2020-q1/x/_problem.jpg'],
        page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
        audio: { abc123: '/assets-data/audio/abc123.mp3' },
        attempted: false,
        done_in_session: false,
      },
    ],
    ...overrides,
  }
}

const ROUTE = '/sessions/session-1'
const PATTERN = '/sessions/:sessionId'

beforeEach(() => {
  setCurrentProfileId(PROFILE_ID)
  _resetDefaultOutboxStoreForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('SessionPlayer', () => {
  it('shows the current chunk label and the current Problem, without its Answer Key', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Phần 1/1')).toBeInTheDocument()
    expect(screen.getByText('Bài 1')).toBeInTheDocument()
    expect(screen.getByText('Tính:')).toBeInTheDocument()
    expect(screen.queryByText(/answer/i)).not.toBeInTheDocument()
  })

  it('mounts the child FlagButton and posts the current Problem id with the profile id', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      [`POST /api/v1/problems/${PROBLEM.problem_id}/flag`]: { status: 200, body: { ok: true } },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: 'Báo cho bố mẹ' }))
    fireEvent.click(screen.getByRole('button', { name: 'Có' }))
    expect(await screen.findByText('Đã báo cho bố mẹ')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        init?.method === 'POST' && url === `/api/v1/problems/${PROBLEM.problem_id}/flag`,
    )
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ profile_id: PROFILE_ID })
  })

  it('opens the Concept Guide from 📖, keeps the typed answer on close, and hides 📖 in quizzes', async () => {
    const withConcept = { ...PROBLEM, concept_ids: ['g1.a'] as never[] }
    const b = bundle()
    b.problems[0].problem = withConcept
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: b },
      'GET /api/v1/library/concepts/g1.a': {
        status: 200,
        body: {
          concept_id: 'g1.a',
          name_vi: 'So sánh số',
          grade: 1,
          problem_count: 3,
          guide: {
            explanation: 'Giải thích ngắn.',
            example: { question: 'Câu hỏi mẫu', steps: ['Bước một'], answer: 'Đáp số' },
          },
        },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    expect(screen.getByRole('button', { name: /Ô s1.*5/ })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Xem hướng dẫn' }))
    expect(await screen.findByText('Giải thích ngắn.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Đóng' }))
    await waitFor(() => expect(screen.queryByText('Giải thích ngắn.')).not.toBeInTheDocument())
    expect(screen.getByText('Bài 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Ô s1.*5/ })).toBeInTheDocument()
  })

  it('shows no 📖 for a Problem without Concepts or in a quiz Session', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    await screen.findByText('Bài 1')
    expect(screen.queryByRole('button', { name: 'Xem hướng dẫn' })).not.toBeInTheDocument()
  })

  it('shows a friendly message, not a crash, when every Problem in the chunk was skipped', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle({ problems: [] }) },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Phần này chưa có bài tập nào để hiển thị.')).toBeInTheDocument()
  })

  it('shows a loading state while the bundle is being fetched', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(screen.getByText('Đang tải…')).toBeInTheDocument()
  })

  it('shows an error with retry when the bundle fetch fails', async () => {
    const fetchMock = mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 502 } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('shows a "go back to Library" message, not an endless retry, for a gone/unknown Session', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 404,
        body: { error: { code: 'SESSION_NOT_FOUND', message: 'Không tìm thấy lượt học.' } },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(
      await screen.findByText('Lượt học này không còn tồn tại. Hãy quay lại Sách để bắt đầu lại.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
  })

  it('reaches the real summary screen, with a link back to the Library, after the only Problem in a single-chunk (true-end) Session', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 1,
          total: 1,
          wrong_problem_ids: [],
          streak: 1,
          stars_earned: 3,
        },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    const slot = screen.getByRole('button', { name: /Ô s1/ })
    fireEvent.click(slot)
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(
      await screen.findByText('Em đã hoàn thành bài! Em được nhiều ngôi sao lắm.', {}, { timeout: 3000 }),
    ).toBeInTheDocument()
    expect(screen.getByText('1/1')).toBeInTheDocument()
    // Story 3.1: `stars_earned` is shown on the summary screen (a different, wider
    // metric than the `first_try_correct` count above -- see `SessionSummary`'s own
    // docstring).
    expect(screen.getByTestId('stars-earned')).toHaveTextContent('3')
    // Zero wrong Problems -- "Luyện lại bài sai" must not be shown.
    expect(screen.queryByRole('button', { name: 'Luyện lại bài sai' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Về Sách').length).toBeGreaterThan(0)
  })

  it('pops a newly earned badge with fanfare + 🔊 on the summary screen (Story 3.2)', async () => {
    const { speak } = await import('../audio/speech')
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 1,
          total: 1,
          wrong_problem_ids: [],
          streak: 1,
          stars_earned: 3,
          new_badges: ['week1'],
        },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(
      await screen.findByTestId('session-new-badges', {}, { timeout: 3000 }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('badge-week1')).toBeInTheDocument()
    expect(screen.getByText('Hoàn thành Tuần 1')).toBeInTheDocument()
    await vi.waitFor(() => expect(speak).toHaveBeenCalledWith('Em vừa nhận được một huy hiệu mới!'))
    await vi.waitFor(() => expect(speak).toHaveBeenCalledWith('Hoàn thành Tuần 1'))
  })

  it('shows no badge fanfare when the summary reports no new badges', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 1,
          total: 1,
          wrong_problem_ids: [],
          streak: 1,
          stars_earned: 3,
          new_badges: [],
        },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await screen.findByTestId('stars-earned', {}, { timeout: 3000 })
    expect(screen.queryByTestId('session-new-badges')).not.toBeInTheDocument()
  })

  it('shows "Luyện lại bài sai" at the summary screen when the summary reports wrong Problems, and starts a replay Session on tap', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 0,
          total: 1,
          wrong_problem_ids: [PROBLEM.problem_id],
          streak: 1,
        },
      },
      'POST /api/v1/sessions': {
        status: 201,
        body: {
          id: 'session-replay',
          profile_id: PROFILE_ID,
          ref_kind: 'replay',
          problem_ids: [PROBLEM.problem_id],
          chunk_size: 10,
          mode: 'replay',
          started_at: 'x',
        },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    const replayButton = await screen.findByRole(
      'button',
      { name: 'Luyện lại bài sai' },
      { timeout: 3000 },
    )
    fireEvent.click(replayButton)
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/sessions',
        expect.objectContaining({ method: 'POST' }),
      )
    })
    const [, init] = fetchMock.mock.calls.find(([url]) => url === '/api/v1/sessions') ?? []
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      profile_id: PROFILE_ID,
      ref: { kind: 'replay', source_session_id: 'session-1' },
      mode: 'replay',
    })
  })

  it('advances from Problem 1 to Problem 2 within one chunk (finding #7)', async () => {
    const problem2 = {
      ...PROBLEM,
      problem_id: 'toan1-2020-q1.tuan-5.tiet-2.bai-2',
      problem_label: 'bai-2',
      display_label: 'Bài 2',
    }
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({
          problems: [
            {
              problem: PROBLEM,
              crop_urls: ['/assets-data/crops/toan1-2020-q1/x/_problem.jpg'],
              page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
              audio: {},
              attempted: false,
              done_in_session: false,
            },
            {
              problem: problem2,
              crop_urls: ['/assets-data/crops/toan1-2020-q1/y/_problem.jpg'],
              page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
              audio: {},
              attempted: false,
              done_in_session: false,
            },
          ],
        }),
      },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByText('Bài 2', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.queryByText('Bài 1')).not.toBeInTheDocument()
  })

  it('offers "Phần tiếp theo" instead of the Library link when a further chunk exists', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ chunk: 1, chunk_count: 2, chunk_label: 'Phần 1/2' }),
      },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ id: 'e1', session_id: 'session-1', kind: 'attempt', problem_id: PROBLEM.problem_id, occurred_at: 'x', received_at: 'x', correct: true }],
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(
      await screen.findByRole('button', { name: 'Phần tiếp theo ➜' }, { timeout: 3000 }),
    ).toBeInTheDocument()
  })

  // --- Story 2.11: offline outbox ---------------------------------------------------

  it('shows the offline screen (no local grading) when submitting an attempt while the network is unreachable', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))

    // Genuinely unreachable server: `fetch()` itself throws (`NetworkError`), not a 4xx/5xx.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))

    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()
    expect(screen.getByText('Máy tính bảng chưa kết nối mạng…')).toBeInTheDocument()
    // No correct/wrong verdict of any kind while offline.
    expect(screen.queryByText('Bài 1')).not.toBeInTheDocument()
    expect(document.querySelector('.feedback-banner-correct')).not.toBeInTheDocument()
  })

  it('retrying once back online flushes the queued attempt and returns to the Session', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))

    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()

    // Back online: the queued `attempt` now flushes successfully.
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [
          {
            id: 'e1',
            session_id: 'session-1',
            kind: 'attempt',
            problem_id: PROBLEM.problem_id,
            occurred_at: 'x',
            received_at: 'x',
            correct: true,
          },
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.queryByTestId('offline-screen')).not.toBeInTheDocument()
  })

  it('auto-clears the offline screen when the background auto-flush (not the manual button) drains the queue (Review Triage Log #10)', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))

    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()

    // Back online: the queued `attempt` now flushes successfully, but this time the
    // reconnect is reported via the app-wide `online` listener (`useOutboxAutoFlush`), not
    // by tapping "Thử lại" -- the exact scenario finding #10 describes (Wi-Fi returns
    // before the child taps anything).
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [
          {
            id: 'e1',
            session_id: 'session-1',
            kind: 'attempt',
            problem_id: PROBLEM.problem_id,
            occurred_at: 'x',
            received_at: 'x',
            correct: true,
          },
        ],
      },
    })
    window.dispatchEvent(new Event('online'))

    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.queryByTestId('offline-screen')).not.toBeInTheDocument()
  })

  it('retry tapped while still offline stays on the offline screen, no crash', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    await vi.waitFor(() => expect(screen.getByTestId('offline-screen')).toBeInTheDocument())
  })

  it('shows the honest "stuck, not a network problem" message when retry hits a genuine server rejection (Review Triage Log #9)', async () => {
    mockApi({ 'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() } })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()
    expect(screen.getByText('Máy tính bảng chưa kết nối mạng…')).toBeInTheDocument()

    // Reconnected (the server IS now reachable), but it rejects the queued event outright
    // (e.g. a `problem_id` invalidated by a content edit after it was queued) -- a 422, not
    // a network failure.
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
      'POST /api/v1/sessions/session-1/events': { status: 422 },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

    expect(await screen.findByTestId('offline-screen')).toBeInTheDocument()
    expect(
      screen.getByText('Có bài chưa gửi được, nhưng máy tính bảng vẫn đang kết nối mạng.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Máy tính bảng chưa kết nối mạng…')).not.toBeInTheDocument()
  })
})

describe('SessionPlayer quiz mode (Story 3.4)', () => {
  const QUIZ_EVENT = {
    id: 'e1',
    session_id: 'session-1',
    kind: 'attempt',
    problem_id: PROBLEM.problem_id,
    occurred_at: 'x',
    received_at: 'x',
    quiz_stars_awarded: true,
    quiz_results: [
      {
        problem_id: PROBLEM.problem_id,
        display_label: 'Bài 1',
        correct: false,
        stars: 0,
        solutions: [{ part_key: 'a', solution: { steps: ['3 + 2 = 5'] } }],
      },
    ],
  }

  function mockQuiz() {
    return mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ mode: 'quiz' }),
      },
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [QUIZ_EVENT] },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 0,
          total: 1,
          wrong_problem_ids: [PROBLEM.problem_id],
          streak: 1,
          stars_earned: 0,
          new_badges: [],
        },
      },
    })
  }

  it('shows only "Đã lưu" after a check, then the server results with the Solution for a ↻', async () => {
    const fetchMock = mockQuiz()
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.getAllByRole('list', { name: 'Tiến độ' }).length).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument()
    expect(screen.queryByText(/Đúng rồi|Chưa đúng|Sai/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /gợi ý|💡/i })).not.toBeInTheDocument()

    expect(await screen.findByTestId('quiz-results', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByTestId('quiz-result-retry')).toHaveTextContent('↻')
    expect(screen.getByText('3 + 2 = 5')).toBeInTheDocument()
    const kinds = fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      .flatMap(([, init]) => JSON.parse((init as RequestInit).body as string).events)
      .map((e: { kind: string }) => e.kind)
    expect(kinds).toEqual(['attempt', 'quiz_submitted', 'session_completed'])
  })

  it('resumes at the first unanswered Problem, and submits when all are answered', async () => {
    const answered = { ...bundle().problems[0], attempted: true, done_in_session: true }
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ mode: 'quiz', problems: [answered] }),
      },
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [QUIZ_EVENT] },
      'GET /api/v1/sessions/session-1/summary': { status: 404 },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByTestId('quiz-results', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  function postedKinds(fetchMock: ReturnType<typeof mockApi>): string[] {
    return fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      .flatMap(([, init]) => JSON.parse((init as RequestInit).body as string).events)
      .map((e: { kind: string }) => e.kind)
  }

  it('plays a fallback Part with only a plain continue button, posting no self-check events', async () => {
    const fallbackProblem = {
      ...PROBLEM,
      parts: [{ part_key: 'p1', type: 'fallback', prompt: '', image_keys: [], image_key: 'img1' }],
    }
    const fetchMock = mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({
          mode: 'quiz',
          problems: [{ ...bundle().problems[0], problem: fallbackProblem }],
        }),
      },
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [QUIZ_EVENT] },
      'GET /api/v1/sessions/session-1/summary': { status: 404 },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Xem đáp án/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Tiếp/ }))
    expect(await screen.findByTestId('quiz-results', {}, { timeout: 3000 })).toBeInTheDocument()
    const kinds = postedKinds(fetchMock)
    expect(kinds).not.toContain('self_marked')
    expect(kinds).not.toContain('fallback_revealed')
  })

  it('tells the child a retake earns no Stars', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ mode: 'quiz', problems: [{ ...bundle().problems[0], attempted: true, done_in_session: true }] }),
      },
      'POST /api/v1/sessions/session-1/events': {
        status: 201,
        body: [{ ...QUIZ_EVENT, quiz_stars_awarded: false }],
      },
      'GET /api/v1/sessions/session-1/summary': { status: 404 },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(
      await screen.findByText(/không có thêm ngôi sao/, {}, { timeout: 3000 }),
    ).toBeInTheDocument()
  })

  it('shows an error with retry when session_completed fails after a successful submit', async () => {
    let posts = 0
    const json = { 'Content-Type': 'application/json' }
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (method === 'GET' && url.startsWith('/api/v1/sessions/session-1/bundle')) {
        const b = bundle({ mode: 'quiz', problems: [{ ...bundle().problems[0], attempted: true, done_in_session: true }] })
        return new Response(JSON.stringify(b), { status: 200, headers: json })
      }
      if (method === 'POST') {
        posts += 1
        const kind = JSON.parse(init?.body as string).events[0].kind
        if (kind === 'session_completed' && posts <= 2) {
          return new Response(
            JSON.stringify({ error: { code: 'BOOM', message: 'Có lỗi xảy ra.' } }),
            { status: 500, headers: json },
          )
        }
        return new Response(JSON.stringify([QUIZ_EVENT]), { status: 201, headers: json })
      }
      return new Response(null, { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByTestId('quiz-results', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent(/\S/)
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
  })

  // --- Epic 2 review patches -----------------------------------------------------------

  const json = { 'Content-Type': 'application/json' }

  function twoProblems(firstDone: boolean, secondDone = false) {
    const problem2 = {
      ...PROBLEM,
      problem_id: 'toan1-2020-q1.tuan-5.tiet-2.bai-2',
      problem_label: 'bai-2',
      display_label: 'Bài 2',
    }
    const base = bundle().problems[0]
    return [
      { ...base, done_in_session: firstDone },
      { ...base, problem: problem2, done_in_session: secondDone },
    ]
  }

  it('resumes a practice Session at the first Problem not finished in THIS Session', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ problems: twoProblems(true) }),
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 2')).toBeInTheDocument()
    expect(screen.queryByText('Bài 1')).not.toBeInTheDocument()
  })

  it('skips a whole finished chunk and resumes in the next one', async () => {
    const requestedChunks: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const chunk = new URL(url, 'http://x').searchParams.get('chunk') ?? '1'
        if (url.includes('/bundle')) {
          requestedChunks.push(chunk)
          const b =
            chunk === '1'
              ? bundle({ chunk: 1, chunk_count: 2, chunk_label: 'Phần 1/2', problems: twoProblems(true, true) })
              : bundle({ chunk: 2, chunk_count: 2, chunk_label: 'Phần 2/2', problems: twoProblems(false) })
          return new Response(JSON.stringify(b), { status: 200, headers: json })
        }
        return new Response(null, { status: 404 })
      }),
    )
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Phần 2/2')).toBeInTheDocument()
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(requestedChunks).toEqual(['1', '2'])
  })

  it('shows an error with retry when session_completed fails in a practice Session', async () => {
    let completedPosts = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? 'GET'
        if (method === 'GET' && url.includes('/bundle')) {
          const b = bundle({ problems: [{ ...bundle().problems[0], done_in_session: true }] })
          return new Response(JSON.stringify(b), { status: 200, headers: json })
        }
        if (method === 'POST') {
          completedPosts += 1
          if (completedPosts === 1) {
            return new Response(
              JSON.stringify({ error: { code: 'BOOM', message: 'Có lỗi xảy ra.' } }),
              { status: 500, headers: json },
            )
          }
          return new Response(JSON.stringify([QUIZ_EVENT]), { status: 201, headers: json })
        }
        return new Response(null, { status: 404 })
      }),
    )
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByRole('alert')).toHaveTextContent(/\S/)
    // Not stuck on the summary's "Đang tải…".
    expect(screen.queryByText('Đang tải…')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    await vi.waitFor(() => expect(completedPosts).toBe(2))
  })

  it('shows an error when starting "Luyện lại bài sai" fails', async () => {
    mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({ problems: [{ ...bundle().problems[0], done_in_session: true }] }),
      },
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [QUIZ_EVENT] },
      'GET /api/v1/sessions/session-1/summary': {
        status: 200,
        body: {
          session_id: 'session-1',
          first_try_correct: 0,
          total: 1,
          wrong_problem_ids: [PROBLEM.problem_id],
          streak: 1,
          stars_earned: 0,
          new_badges: [],
        },
      },
      'POST /api/v1/sessions': {
        status: 422,
        body: { error: { code: 'REPLAY_NO_WRONG_PROBLEMS', message: 'Không có bài nào để luyện lại.' } },
      },
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: 'Luyện lại bài sai' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Không có bài nào để luyện lại.')
  })

  describe('auto-play follows the Profile setting', () => {
    function profilesReply(autoPlay: boolean) {
      return {
        status: 200,
        body: [{ id: PROFILE_ID, name: 'Bin', avatar: 'cat', grade: 1, auto_play: autoPlay }],
      }
    }

    it('plays the instruction when auto_play is true', async () => {
      const { speak } = await import('../audio/speech')
      ;(speak as ReturnType<typeof vi.fn>).mockClear()
      window.dispatchEvent(new Event('click')) // unlock audio
      mockApi({
        'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
        'GET /api/v1/profiles': profilesReply(true),
      })
      renderAt(ROUTE, <SessionPlayer />, PATTERN)
      expect(await screen.findByText('Bài 1')).toBeInTheDocument()
      await vi.waitFor(() => expect(speak).toHaveBeenCalledWith('Tính:'))
    })

    it('does not play it when auto_play is false', async () => {
      const { speak } = await import('../audio/speech')
      ;(speak as ReturnType<typeof vi.fn>).mockClear()
      window.dispatchEvent(new Event('click'))
      mockApi({
        'GET /api/v1/sessions/session-1/bundle': { status: 200, body: bundle() },
        'GET /api/v1/profiles': profilesReply(false),
      })
      renderAt(ROUTE, <SessionPlayer />, PATTERN)
      await screen.findByText('Bài 1')
      await new Promise((r) => setTimeout(r, 50))
      expect(speak).not.toHaveBeenCalledWith('Tính:')
    })
  })
})

describe('SessionPlayer exam mode (Story 8.1)', () => {
  const EXAM_EVENT = {
    id: 'e1',
    session_id: 'session-1',
    kind: 'attempt',
    problem_id: PROBLEM.problem_id,
    occurred_at: 'x',
    received_at: 'x',
    exam_results: [
      {
        problem_id: PROBLEM.problem_id,
        display_label: 'Bài 1',
        correct: false,
        solutions: [{ part_key: 'a', solution: { steps: ['3 + 2 = 5'] } }],
      },
    ],
  }

  function mockExam(overrides: Partial<Record<string, unknown>> = {}) {
    return mockApi({
      'GET /api/v1/sessions/session-1/bundle': {
        status: 200,
        body: bundle({
          mode: 'exam',
          // Started "now" (not a fixed past date) so the countdown has real time left --
          // this test is about mid-play behaviour, not the timeout itself (see the
          // dedicated "auto-submits when the countdown reaches zero" test below).
          started_at: new Date().toISOString(),
          time_limit_s: 600,
          ...overrides,
        }),
      },
      'POST /api/v1/sessions/session-1/events': { status: 201, body: [EXAM_EVENT] },
    })
  }

  it('shows only "Đã lưu" during play, then the exam results -- never the Stars/Streak summary', async () => {
    const fetchMock = mockExam()
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.getByTestId('exam-countdown')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument()
    expect(screen.queryByText(/Đúng rồi|Chưa đúng|Sai/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /gợi ý|💡/i })).not.toBeInTheDocument()

    expect(await screen.findByTestId('exam-results', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByTestId('exam-result-retry')).toHaveTextContent('↻')
    expect(screen.getByText('3 + 2 = 5')).toBeInTheDocument()
    // Story 8.1: zero Stars, zero Streak -- the generic summary screen never shows for exam.
    expect(screen.queryByTestId('stars-earned')).not.toBeInTheDocument()
    expect(screen.queryByText(/liên tiếp!/)).not.toBeInTheDocument()

    const kinds = fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      .flatMap(([, init]) => JSON.parse((init as RequestInit).body as string).events)
      .map((e: { kind: string }) => e.kind)
    expect(kinds).toEqual(['attempt', 'exam_submitted', 'session_completed'])
  })

  it('auto-submits when the countdown reaches zero, even with Problems unanswered', async () => {
    const fetchMock = mockExam({
      // Already overdue at mount -- the countdown's very first tick fires `onExpire()`.
      started_at: '2020-01-01T00:00:00.000000+00:00',
      time_limit_s: 1,
    })
    renderAt(ROUTE, <SessionPlayer />, PATTERN)
    expect(await screen.findByTestId('exam-results', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByTestId('exam-result-retry')).toBeInTheDocument()
    const kinds = fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      .flatMap(([, init]) => JSON.parse((init as RequestInit).body as string).events)
      .map((e: { kind: string }) => e.kind)
    // No `attempt` at all -- the child never answered before time ran out.
    expect(kinds).toEqual(['exam_submitted', 'session_completed'])
  })
})
