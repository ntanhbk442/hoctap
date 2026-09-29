import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BundleProblemOut } from '../api/client'
import { phrase } from '../audio/phrases'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'
import ProblemPlayer from './ProblemPlayer'

vi.mock('../audio/speech', () => ({ speak: vi.fn(() => Promise.resolve()) }))

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
  }
}

function renderPlayer(bp: BundleProblemOut, onDone = vi.fn()) {
  return renderAt(
    ROUTE,
    <ProblemPlayer
      sessionId={SESSION_ID}
      profileId={PROFILE_ID}
      bundleProblem={bp}
      stars={0}
      onStarEarned={vi.fn()}
      onDone={onDone}
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

describe('ProblemPlayer: number_input', () => {
  const NUMBER_INPUT_PART = {
    part_key: 'a',
    type: 'number_input',
    prompt: '',
    image_keys: [],
    template: '3 + 2 = [[s1]]',
    slots: [{ slot_key: 's1' }],
  }

  it('disables ✔ until the slot is filled, then enables it', () => {
    mockApi({})
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
  })

  it('posts one `attempt` event with {part_key, value} on ✔, disables ✔ while in flight', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    expect(call).toBeDefined()
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events).toHaveLength(1)
    expect(body.events[0].kind).toBe('attempt')
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: [{ key: 's1', value: '5' }] })
    // A real UUIDv7: the backend's `_is_uuid7()` (`uuid.UUID(value).version == 7`).
    expect(body.events[0].id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
  })

  it('correct attempt: green slot, praise banner, StarBurst earned, then advances', async () => {
    mockApi(eventsReply({ correct: true }))
    const onDone = vi.fn()
    const onStarEarned = vi.fn()
    renderAt(
      ROUTE,
      <ProblemPlayer
        sessionId={SESSION_ID}
        profileId={PROFILE_ID}
        bundleProblem={bundleProblem([NUMBER_INPUT_PART])}
        stars={0}
        onStarEarned={onStarEarned}
        onDone={onDone}
      />,
      PATTERN,
    )
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByLabelText('Ô s1: 5')).toHaveClass('answer-slot-correct')
    expect(onStarEarned).toHaveBeenCalledOnce()
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledOnce(), { timeout: 3000 })
  })

  it('first wrong attempt: shake+orange immediately, HintBubble after a 400ms gap, then re-enabled to retry', async () => {
    mockApi(eventsReply({ correct: false, wrong_keys: ['s1'], hint: 'Đếm lại nhé.' }))
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '9' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByLabelText('Ô s1: 9')).toHaveClass('answer-slot-wrong')
    expect(screen.queryByText('Đếm lại nhé.')).not.toBeInTheDocument()
    expect(await screen.findByText('Đếm lại nhé.', {}, { timeout: 2000 })).toBeInTheDocument()
    // Retrying: tapping the slot again clears the wrong/red state and re-enables input.
    fireEvent.click(screen.getByRole('button', { name: /Ô s1: 9/ }))
    expect(screen.getByLabelText('Ô s1: 9')).toHaveClass('answer-slot-active')
  })

  it('second wrong attempt: SolutionPanel step-through with a "Tiếp ➜" to advance', async () => {
    mockApi(
      eventsReply({
        correct: false,
        hint: 'Đếm lại nhé.',
        solution: { steps: ['3 quả táo', 'thêm 2 quả', 'được 5 quả'], final: '5' },
      }),
    )
    const onDone = vi.fn()
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]), onDone)
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '9' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(
      await screen.findByText('3 quả táo', {}, { timeout: 2000 }),
    ).toBeInTheDocument()
    expect(screen.queryByText('thêm 2 quả')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Xem tiếp ➜' }))
    expect(await screen.findByText('thêm 2 quả')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Xem tiếp ➜' }))
    expect(await screen.findByText('được 5 quả')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tiếp ➜' }))
    expect(onDone).toHaveBeenCalledOnce()
  })

  it('shows an error and re-enables ✔ when the submit fails, keeping local state', async () => {
    mockApi({ 'POST /api/v1/sessions/session-1/events': { status: 502 } })
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
    expect(screen.getByLabelText('Ô s1: 5')).toBeInTheDocument()
  })

  it('a synchronous double-tap on ✔ posts exactly one `attempt` event (finding #3)', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    const checkButton = screen.getByRole('button', { name: 'Kiểm tra' })
    // Two back-to-back taps, neither awaited in between -- the exact race the ref guard
    // (not the React-state-derived `disabled`) must catch.
    fireEvent.click(checkButton)
    fireEvent.click(checkButton)
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const eventCalls = fetchMock.mock.calls.filter(([url]) => (url as string).includes('/events'))
    expect(eventCalls).toHaveLength(1)
  })

  it('pins the displayed praise-banner text to the actually-spoken phrase (finding #6)', async () => {
    mockApi(eventsReply({ correct: true }))
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.99)
    const { speak } = await import('../audio/speech')
    renderPlayer(bundleProblem([NUMBER_INPUT_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const spokenText = (speak as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0] as string
    expect(spokenText).toBe(phrase('praise_6'))
    expect(document.querySelector('.feedback-banner-visible')).toHaveTextContent(spokenText)
    randomSpy.mockRestore()
  })

  it('a multi-Part Problem advances from Part a to Part b, not to onDone, on a correct attempt', async () => {
    mockApi(eventsReply({ correct: true }))
    const onDone = vi.fn()
    const SECOND_PART = {
      part_key: 'b',
      type: 'number_input',
      prompt: '',
      image_keys: [],
      template: '1 + 1 = [[s1]]',
      slots: [{ slot_key: 's1' }],
    }
    renderPlayer(bundleProblem([NUMBER_INPUT_PART, SECOND_PART]), onDone)
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    // Part b's own empty slot re-appears once Part a's correct-feedback pause elapses --
    // proof the player moved to the next Part, not straight to `onDone`.
    expect(await screen.findByLabelText('Ô s1: trống', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledOnce(), { timeout: 3000 })
  })
})

describe('ProblemPlayer: compare', () => {
  const COMPARE_PART = {
    part_key: 'a',
    type: 'compare',
    prompt: '',
    image_keys: [],
    rows: [{ slot_key: 'r1', left: '3', right: '5' }],
  }

  it('tapping a chip fills that row\'s slot', () => {
    mockApi({})
    renderPlayer(bundleProblem([COMPARE_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '<' }))
    expect(screen.getByRole('button', { name: '<' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
  })

  it('a correct attempt grades the tapped chip green (finding #5)', async () => {
    mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([COMPARE_PART]))
    fireEvent.click(screen.getByRole('button', { name: '<' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByRole('button', { name: '<' })).toHaveClass('choice-chip-correct')
  })

  it('a wrong attempt grades the tapped chip orange (finding #5)', async () => {
    mockApi(eventsReply({ correct: false, wrong_keys: ['r1'], hint: 'Xem lại nhé.' }))
    renderPlayer(bundleProblem([COMPARE_PART]))
    fireEvent.click(screen.getByRole('button', { name: '<' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByRole('button', { name: '<' })).toHaveClass('choice-chip-wrong')
  })
})

describe('ProblemPlayer: multiple_choice', () => {
  function part(multi: boolean) {
    return {
      part_key: 'a',
      type: 'multiple_choice',
      prompt: 'Chọn số chẵn:',
      image_keys: [],
      multi,
      options: [
        { option_key: 'A', text: '2' },
        { option_key: 'B', text: '3' },
        { option_key: 'C', text: '4' },
      ],
    }
  }

  it('single-select: tapping B then A leaves only A selected', () => {
    mockApi({})
    renderPlayer(bundleProblem([part(false)]))
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '3' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('multi-select: both tapped options stay selected', () => {
    mockApi({})
    renderPlayer(bundleProblem([part(true)]))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '4' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('a correct attempt grades the selected chip green (finding #5)', async () => {
    mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([part(false)]))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByRole('button', { name: '2' })).toHaveClass('choice-chip-correct')
  })

  it('a wrong attempt grades the selected chip orange (finding #5)', async () => {
    mockApi(eventsReply({ correct: false, hint: 'Xem lại nhé.' }))
    renderPlayer(bundleProblem([part(false)]))
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByRole('button', { name: '3' })).toHaveClass('choice-chip-wrong')
  })
})

describe('ProblemPlayer: count_image', () => {
  const COUNT_IMAGE_PART = {
    part_key: 'a',
    type: 'count_image',
    prompt: 'Đếm quả táo:',
    image_keys: ['img1'],
    image_key: 'img1',
    slots: [{ slot_key: 's1', label: 'Số quả' }],
  }

  it('tapping the image places local dots only; nothing is sent, the NumberPad slot is unaffected', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([COUNT_IMAGE_PART]))
    const canvas = screen.getByRole('button', { name: /Đếm hình/ })
    for (let i = 0; i < 3; i += 1) fireEvent.click(canvas, { clientX: 10, clientY: 10 })
    expect(document.querySelectorAll('.widget-count-image-dot')).toHaveLength(3)
    expect(screen.getByLabelText('Ô s1: trống')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await screen.findByLabelText('Ô s1: 3')
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload.value).toEqual([{ key: 's1', value: '3' }])
    expect(JSON.stringify(body.events[0].payload)).not.toMatch(/dot/i)
  })

  it('resets dots on a retry after a wrong attempt, on the SAME Part (finding #2)', async () => {
    mockApi(eventsReply({ correct: false, wrong_keys: ['s1'], hint: 'Đếm lại nhé.' }))
    renderPlayer(bundleProblem([COUNT_IMAGE_PART]))
    const canvas = screen.getByRole('button', { name: /Đếm hình/ })
    for (let i = 0; i < 3; i += 1) fireEvent.click(canvas, { clientX: 10, clientY: 10 })
    expect(document.querySelectorAll('.widget-count-image-dot')).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: /Ô s1/ }))
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    expect(await screen.findByText('Đếm lại nhé.', {}, { timeout: 2000 })).toBeInTheDocument()
    // Old dots are still visible right up to the point of retrying (not sent, not graded).
    expect(document.querySelectorAll('.widget-count-image-dot')).toHaveLength(3)
    // Retry: tapping the slot begins a new attempt cycle on the same Part -- the dots must
    // be cleared, not merely capped at 3 from the first attempt.
    fireEvent.click(screen.getByRole('button', { name: /Ô s1: 3/ }))
    expect(document.querySelectorAll('.widget-count-image-dot')).toHaveLength(0)
    // The retry remounted `CountImageWidget` (new `key`) -- re-query the canvas, the old
    // node reference is now detached.
    const retryCanvas = screen.getByRole('button', { name: /Đếm hình/ })
    for (let i = 0; i < 2; i += 1) fireEvent.click(retryCanvas, { clientX: 10, clientY: 10 })
    expect(document.querySelectorAll('.widget-count-image-dot')).toHaveLength(2)
  })
})

describe('ProblemPlayer: unsupported Part type', () => {
  it('shows a "chưa hỗ trợ" placeholder and a way forward, never a crash', () => {
    mockApi({})
    const onDone = vi.fn()
    renderPlayer(
      bundleProblem([{ part_key: 'a', type: 'order', prompt: '', image_keys: [], items: [], direction: 'asc' }]),
      onDone,
    )
    expect(screen.getByText(/chưa được hỗ trợ/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tiếp ➜' }))
    expect(onDone).toHaveBeenCalledOnce()
  })
})
