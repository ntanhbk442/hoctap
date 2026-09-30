import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BundleProblemOut } from '../api/client'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'
import ProblemPlayer from './ProblemPlayer'

// `speechKey` is mocked as an identity function (resolves to the input text itself) so the
// rest of this file's tests -- which don't care about `InstructionLine`'s real key/playing
// wiring, only that `speak()` gets called with the right text -- don't need real `crypto`
// digesting to make instruction-key comparisons deterministic.
vi.mock('../audio/speech', () => ({
  speak: vi.fn(() => Promise.resolve()),
  speechKey: vi.fn((text: string) => Promise.resolve(text)),
}))
// Story 2.9's auto-play-on-open gate, and `InstructionLine`'s (finding #1) live
// playing/missing wiring: mocked so tests control unlock/player state deterministically
// instead of depending on real window `pointerdown`/`click` event leakage between tests, or a
// real shared `<audio>` element's async `play()`.
vi.mock('../audio/player', () => ({
  isAudioUnlocked: vi.fn(() => false),
  stop: vi.fn(),
  subscribe: vi.fn(() => () => {}),
  getPlayerState: vi.fn(() => ({ key: null, status: 'idle' })),
  isMissing: vi.fn(() => false),
}))

const PROFILE_ID = 'profile-1'
const SESSION_ID = 'session-1'
const ROUTE = '/sessions/session-1'
const PATTERN = '/sessions/:sessionId'

function header(overrides: Partial<Record<string, unknown>> = {}) {
  return {
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
    ...overrides,
  }
}

function bundleProblem(parts: unknown[]): BundleProblemOut {
  return {
    problem: header({ parts }) as unknown as BundleProblemOut['problem'],
    crop_urls: ['/assets-data/crops/toan1-2020-q1/x/_problem.jpg'],
    page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
    audio: {},
    attempted: false,
    done_in_session: false,
  }
}

function renderPlayer(bp: BundleProblemOut, grade?: number, onDone = vi.fn()) {
  return renderAt(
    ROUTE,
    <ProblemPlayer
      sessionId={SESSION_ID}
      profileId={PROFILE_ID}
      bundleProblem={bp}
      stars={0}
      onStarEarned={vi.fn()}
      onDone={onDone}
      grade={grade}
    />,
    PATTERN,
  )
}

function eventsReply(body: Partial<Record<string, unknown>>) {
  return {
    'POST /api/v1/sessions/session-1/events': {
      status: 201,
      body: [
        {
          id: 'e1',
          session_id: SESSION_ID,
          kind: 'attempt',
          problem_id: header().problem_id,
          occurred_at: 'x',
          received_at: 'x',
          correct: false,
          wrong_keys: [],
          hint: null,
          solution: null,
          ...body,
        },
      ],
    },
  }
}

beforeEach(() => {
  setCurrentProfileId(PROFILE_ID)
})

afterEach(() => {
  vi.unstubAllGlobals()
})


const EXPRESSION_PART = {
  part_key: 'a',
  type: 'expression_input',
  prompt: '',
  image_keys: [],
  template: '12 × 3 = [[s1]]',
  slots: [{ slot_key: 's1' }],
  mode: 'value',
}
const NUMBER_PART = {
  part_key: 'a',
  type: 'number_input',
  prompt: '',
  image_keys: [],
  template: '[[s1]] + 2',
  slots: [{ slot_key: 's1' }],
}

function press(...names: string[]) {
  for (const name of names) fireEvent.click(screen.getByRole('button', { name }))
}

describe('ProblemPlayer: expression_input (Story 6.1)', () => {
  it('renders the widget and the expression keypad with all operator keys', () => {
    mockApi({})
    renderPlayer(bundleProblem([EXPRESSION_PART]))
    expect(screen.getByRole('button', { name: /Ô s1/ })).toBeInTheDocument()
    for (const name of ['Cộng', 'Trừ', 'Nhân', 'Chia', 'Mở ngoặc', 'Đóng ngoặc', 'Dấu phẩy', 'Gạch phân số', 'Xoá']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
  })

  it('types (4×3)×3 and posts the typed text as the slot value', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([EXPRESSION_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    press('Mở ngoặc', '4', 'Nhân', '3', 'Đóng ngoặc', 'Nhân', '3')
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({
      part_key: 'a',
      value: [{ key: 's1', value: '(4×3)×3' }],
    })
  })

  it('backspace removes the last typed character', () => {
    mockApi({})
    renderPlayer(bundleProblem([EXPRESSION_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    press('3', 'Cộng', 'Xoá')
    expect(screen.getByRole('button', { name: /Ô s1/ })).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /Ô s1/ })).not.toHaveTextContent('+')
  })

  it('a malformed expression is just a wrong Attempt: hint, not an error', async () => {
    mockApi(eventsReply({ correct: false, wrong_keys: ['s1'], hint: 'Con thử lại nhé.' }))
    renderPlayer(bundleProblem([EXPRESSION_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    press('3', 'Cộng', 'Kiểm tra')
    await vi.waitFor(() => expect(screen.getByText('Con thử lại nhé.')).toBeInTheDocument(), {
      timeout: 3000,
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('ProblemPlayer: comma key by grade (Story 6.1)', () => {
  it('number_input shows the comma key for grades 4 and 5', () => {
    mockApi({})
    renderPlayer(bundleProblem([NUMBER_PART]), 4)
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    press('3', 'Dấu phẩy', '5')
    expect(screen.getByRole('button', { name: /Ô s1/ })).toHaveTextContent('3,5')
  })

  it('number_input has no comma key for grades 1-3 or an unknown grade', () => {
    mockApi({})
    const { unmount } = renderPlayer(bundleProblem([NUMBER_PART]), 3)
    expect(screen.queryByRole('button', { name: 'Dấu phẩy' })).not.toBeInTheDocument()
    unmount()
    renderPlayer(bundleProblem([NUMBER_PART]))
    expect(screen.queryByRole('button', { name: 'Dấu phẩy' })).not.toBeInTheDocument()
  })
})
