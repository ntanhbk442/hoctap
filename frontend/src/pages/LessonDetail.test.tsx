import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import LessonDetail from './LessonDetail'

const PROBLEMS = [
  {
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
  },
]

const ROUTE = '/library/toan1-2020-q1/tuan-5/tiet-2'
const PATTERN = '/library/:bookId/:unitKey/:lessonKey'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LessonDetail', () => {
  it('lists the visible Problems, numbered, without their Answer Key', async () => {
    mockApi({
      'GET /api/v1/library/lessons/toan1-2020-q1/tuan-5/tiet-2': { status: 200, body: PROBLEMS },
    })
    renderAt(ROUTE, <LessonDetail />, PATTERN)
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(screen.getByText('Tính:')).toBeInTheDocument()
    expect(screen.queryByText(/answer/i)).not.toBeInTheDocument()
  })

  it('shows a friendly empty state for a Lesson with no visible Problems', async () => {
    mockApi({
      'GET /api/v1/library/lessons/toan1-2020-q1/tuan-5/tiet-2': { status: 200, body: [] },
    })
    renderAt(ROUTE, <LessonDetail />, PATTERN)
    expect(await screen.findByText('Chưa có bài tập nào ở đây.')).toBeInTheDocument()
  })

  it('shows a loading state while the Problems are being fetched', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )
    renderAt(ROUTE, <LessonDetail />, PATTERN)
    expect(screen.getByText('Đang tải…')).toBeInTheDocument()
  })

  it('shows an error with retry when the Problems fetch fails', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/library/lessons/toan1-2020-q1/tuan-5/tiet-2': { status: 502 },
    })
    renderAt(ROUTE, <LessonDetail />, PATTERN)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/library/lessons/toan1-2020-q1/tuan-5/tiet-2': { status: 200, body: PROBLEMS },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Bài 1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })
})
