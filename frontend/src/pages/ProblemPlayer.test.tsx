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
    // `fallback` (the cropped-Problem-as-printed type, solution-only, never graded) is the
    // one Part type this player deliberately never gets a widget for -- Story 2.7 gave
    // every OTHER remaining type (including `order`, this test's fixture before Story 2.7)
    // its own widget, so `order` can no longer stand in as "the unsupported one".
    renderPlayer(
      bundleProblem([{ part_key: 'a', type: 'fallback', prompt: '', image_keys: ['img1'], image_key: 'img1' }]),
      onDone,
    )
    expect(screen.getByText(/chưa được hỗ trợ/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tiếp ➜' }))
    expect(onDone).toHaveBeenCalledOnce()
  })
})

describe('ProblemPlayer: order', () => {
  const ORDER_PART = {
    part_key: 'a',
    type: 'order',
    prompt: 'Sắp xếp từ bé đến lớn:',
    image_keys: [],
    items: [
      { item_key: 'i1', text: '3' },
      { item_key: 'i2', text: '1' },
      { item_key: 'i3', text: '2' },
    ],
    direction: 'asc',
  }

  it('tap-alternative: tap a tile then a slot fills it; ✔ enables once every slot is filled', () => {
    mockApi({})
    renderPlayer(bundleProblem([ORDER_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 1/ }))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 2/ }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 3/ }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
  })

  it('tapping a filled slot with nothing picked picks that tile back up', () => {
    mockApi({})
    renderPlayer(bundleProblem([ORDER_PART]))
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 1/ }))
    expect(screen.getByLabelText('Vị trí 1: 1')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Vị trí 1: 1'))
    // The tile is back in the tray (picked), the slot is empty again.
    expect(screen.getByLabelText('Vị trí 1: trống')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('posts {order: [item_key, ...]} in slot order on ✔', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([ORDER_PART]))
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 1/ }))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 2/ }))
    fireEvent.click(screen.getByRole('button', { name: '3' }))
    fireEvent.click(screen.getByRole('button', { name: /Vị trí 3/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: { order: ['i2', 'i3', 'i1'] } })
  })
})

describe('ProblemPlayer: grid_fill', () => {
  const GRID_FILL_PART = {
    part_key: 'a',
    type: 'grid_fill',
    prompt: '',
    image_keys: [],
    rows: 1,
    cols: 2,
    cells: [[{ given: '5' }, { given: null }]],
  }

  it('a locked (given) cell is not tappable; the empty cell fills via the shared NumberPad', () => {
    mockApi({})
    renderPlayer(bundleProblem([GRID_FILL_PART]))
    expect(screen.queryByRole('button', { name: /Ô r0c0/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Ô r0c0: 5')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Ô r0c1/ }))
    fireEvent.click(screen.getByRole('button', { name: '7' }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
  })

  it('posts [{key, value}] for the empty cell only, matching number_input\'s shape', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([GRID_FILL_PART]))
    fireEvent.click(screen.getByRole('button', { name: /Ô r0c1/ }))
    fireEvent.click(screen.getByRole('button', { name: '7' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: [{ key: 'r0c1', value: '7' }] })
  })
})

describe('ProblemPlayer: match', () => {
  const MATCH_PART = {
    part_key: 'a',
    type: 'match',
    prompt: '',
    image_keys: [],
    left: [
      { item_key: 'l1', text: '1' },
      { item_key: 'l2', text: '2' },
    ],
    right: [
      { item_key: 'r1', text: 'một' },
      { item_key: 'r2', text: 'hai' },
    ],
  }

  it('tap left then right draws a pair; ✔ enables once every left item is paired', () => {
    mockApi({})
    renderPlayer(bundleProblem([MATCH_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: 'một' }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: 'hai' }))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
  })

  it('tapping either paired endpoint un-pairs (tapping "the line")', () => {
    mockApi({})
    renderPlayer(bundleProblem([MATCH_PART]))
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: 'một' }))
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'một' }))
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'một' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('tapping a second left item before any right tap switches the pick, not corrupting state', () => {
    mockApi({})
    renderPlayer(bundleProblem([MATCH_PART]))
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'một' }))
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '1' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'một' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('posts {pairs: [[left_key, right_key], ...]} on ✔', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([MATCH_PART]))
    fireEvent.click(screen.getByRole('button', { name: '1' }))
    fireEvent.click(screen.getByRole('button', { name: 'một' }))
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    fireEvent.click(screen.getByRole('button', { name: 'hai' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({
      part_key: 'a',
      value: { pairs: [['l1', 'r1'], ['l2', 'r2']] },
    })
  })
})

describe('ProblemPlayer: image_select', () => {
  const IMAGE_SELECT_PART = {
    part_key: 'a',
    type: 'image_select',
    prompt: 'Chọn hình tròn:',
    image_keys: ['img1'],
    image_key: 'img1',
    regions: [
      { region_key: 'reg1', bbox: [0, 0, 0.5, 0.5] },
      { region_key: 'reg2', bbox: [0.5, 0.5, 1, 1] },
    ],
    multi: false,
  }

  it('tap a region hotspot selects it (not submitted until ✔), single-select by default', () => {
    mockApi({})
    renderPlayer(bundleProblem([IMAGE_SELECT_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Vùng reg1' }))
    expect(screen.getByRole('button', { name: 'Vùng reg1' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Vùng reg2' }))
    expect(screen.getByRole('button', { name: 'Vùng reg1' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('multi: true allows several regions selected at once, posted as {selected: [...]}', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([{ ...IMAGE_SELECT_PART, multi: true }]))
    fireEvent.click(screen.getByRole('button', { name: 'Vùng reg1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Vùng reg2' }))
    expect(screen.getByRole('button', { name: 'Vùng reg1' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Vùng reg2' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: { selected: ['reg1', 'reg2'] } })
  })
})

describe('ProblemPlayer: dot_draw', () => {
  const DOT_DRAW_PART = {
    part_key: 'a',
    type: 'dot_draw',
    prompt: 'Vẽ thêm 2 chấm:',
    image_keys: [],
    boxes: [{ slot_key: 'b1', label: 'Ô 1', given: 1 }],
  }

  // Same reasoning as `spot_difference`'s test: jsdom's default all-zero
  // `getBoundingClientRect()` would make every tap's normalised (x, y) resolve to the same
  // `Infinity`, indistinguishable from any other tap under the proximity-bucket dedup --
  // a fixed, non-zero rect is needed for "two distinct taps" to be meaningful here.
  let rectSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 300,
      height: 300,
      top: 0,
      left: 0,
      right: 300,
      bottom: 300,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect)
  })
  afterEach(() => {
    rectSpy.mockRestore()
  })

  it('tapping the box adds a dot, updates the counter; tapping a dot removes it', () => {
    mockApi({})
    renderPlayer(bundleProblem([DOT_DRAW_PART]))
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    const box = screen.getByRole('button', { name: /Ô 1/ })
    fireEvent.click(box, { clientX: 10, clientY: 10 })
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeEnabled()
    const addedDot = document.querySelector('.widget-dot-draw-dot-added')
    expect(addedDot).not.toBeNull()
    fireEvent.click(addedDot as Element)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('a tap near an existing dot (not exactly on it) removes it instead of adding a second, overlapping dot', () => {
    mockApi({})
    renderPlayer(bundleProblem([DOT_DRAW_PART]))
    const box = screen.getByRole('button', { name: /Ô 1/ })
    fireEvent.click(box, { clientX: 10, clientY: 10 })
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(document.querySelectorAll('.widget-dot-draw-dot-added')).toHaveLength(1)
    // A near, but not pixel-identical, re-tap -- same proximity bucket as the first dot.
    fireEvent.click(box, { clientX: 15, clientY: 15 })
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(document.querySelectorAll('.widget-dot-draw-dot-added')).toHaveLength(0)
  })

  it('posts [{key, value: count-as-string}] on ✔', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([DOT_DRAW_PART]))
    const box = screen.getByRole('button', { name: /Ô 1/ })
    fireEvent.click(box, { clientX: 10, clientY: 10 })
    fireEvent.click(box, { clientX: 200, clientY: 200 })
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const call = fetchMock.mock.calls.find(([url]) => url.includes('/events'))
    const body = JSON.parse((call![1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: [{ key: 'b1', value: '3' }] })
  })
})

describe('ProblemPlayer: connect_dots', () => {
  const CONNECT_DOTS_PART = {
    part_key: 'a',
    type: 'connect_dots',
    prompt: '',
    image_keys: ['img1'],
    image_key: 'img1',
    dots: [
      { n: 1, x: 0.1, y: 0.1 },
      { n: 2, x: 0.5, y: 0.5 },
      { n: 3, x: 0.9, y: 0.9 },
    ],
  }

  it('tapping the wrong next dot does not advance the sequence and does not post an Attempt', () => {
    const fetchMock = mockApi({})
    renderPlayer(bundleProblem([CONNECT_DOTS_PART]))
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 2' }))
    expect(screen.getByText('0/3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    expect(fetchMock.mock.calls.some(([url]) => (url as string).includes('/events'))).toBe(false)
  })

  it('a backward tap after partial progress (1→2→1) is rejected like a genuinely wrong dot', () => {
    const fetchMock = mockApi({})
    renderPlayer(bundleProblem([CONNECT_DOTS_PART]))
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 2' }))
    expect(screen.getByText('2/3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 1' }))
    expect(screen.getByText('2/3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra' })).toBeDisabled()
    expect(fetchMock.mock.calls.some(([url]) => (url as string).includes('/events'))).toBe(false)
  })

  it('tapping dots in order enables ✔; only tapping ✔ posts one Attempt with {sequence}', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([CONNECT_DOTS_PART]))
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 1' }))
    expect(screen.getByText('1/3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Chấm số 3' }))
    expect(screen.getByText('3/3')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => (url as string).includes('/events'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const eventCalls = fetchMock.mock.calls.filter(([url]) => (url as string).includes('/events'))
    expect(eventCalls).toHaveLength(1)
    const body = JSON.parse((eventCalls[0][1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({ part_key: 'a', value: { sequence: [1, 2, 3] } })
  })
})

describe('ProblemPlayer: spot_difference', () => {
  const SPOT_DIFFERENCE_PART = {
    part_key: 'a',
    type: 'spot_difference',
    prompt: '',
    image_keys: ['img1', 'img2'],
    image_left: 'img1',
    image_right: 'img2',
    count: 2,
  }

  // jsdom's `getBoundingClientRect()` returns an all-zero rect by default, which would
  // make every tap's normalised (x, y) resolve to `Infinity`/`NaN` (division by a 0
  // width/height) -- indistinguishable from any other tap, so the widget's bucket-based
  // de-dup would (wrongly, only in this test environment) treat every second tap as a
  // repeat of the first. A fixed, non-zero rect here is what makes "two distinct taps"
  // meaningful at all under jsdom.
  let rectSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 300,
      height: 300,
      top: 0,
      left: 0,
      right: 300,
      bottom: 300,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect)
  })
  afterEach(() => {
    rectSpy.mockRestore()
  })

  it('a duplicate tap in an already-found spot does not increase the counter or post an Attempt', () => {
    const fetchMock = mockApi({})
    renderPlayer(bundleProblem([SPOT_DIFFERENCE_PART]))
    const rightImage = screen.getByRole('button', { name: 'Tìm điểm khác nhau' })
    fireEvent.click(rightImage, { clientX: 10, clientY: 10 })
    expect(screen.getByText('1/2')).toBeInTheDocument()
    fireEvent.click(rightImage, { clientX: 11, clientY: 11 })
    expect(screen.getByText('1/2')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => (url as string).includes('/events'))).toBe(false)
  })

  it('finding `count` distinct spots enables ✔; only ✔ posts one Attempt with {region_keys}', async () => {
    const fetchMock = mockApi(eventsReply({ correct: true }))
    renderPlayer(bundleProblem([SPOT_DIFFERENCE_PART]))
    const rightImage = screen.getByRole('button', { name: 'Tìm điểm khác nhau' })
    fireEvent.click(rightImage, { clientX: 10, clientY: 10 })
    fireEvent.click(rightImage, { clientX: 200, clientY: 200 })
    expect(screen.getByText('2/2')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => (url as string).includes('/events'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra' }))
    await vi.waitFor(() =>
      expect(document.querySelector('.feedback-banner-visible')).toHaveClass('feedback-banner-correct'),
    )
    const eventCalls = fetchMock.mock.calls.filter(([url]) => (url as string).includes('/events'))
    expect(eventCalls).toHaveLength(1)
    const body = JSON.parse((eventCalls[0][1] as RequestInit).body as string)
    expect(body.events[0].payload).toEqual({
      part_key: 'a',
      value: { region_keys: ['d_0_0', 'd_5_5'] },
    })
  })
})
