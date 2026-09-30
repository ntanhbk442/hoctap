import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import Assignments from './Assignments'
import { tomorrowLocal } from './assignmentUtils'

afterEach(() => {
  vi.unstubAllGlobals()
})

const PROFILES = [{ id: 'p1', name: 'Bin', avatar: 'cat', grade: 1, auto_play: true }]
const BOOKS = [
  {
    book_id: 'b1',
    edition: '2020',
    grade: 1,
    volume: 1,
    title_vi: 'Toán 1',
    units: [
      {
        unit_key: 'u1',
        label: 'TUẦN 5',
        title: '',
        position: 1,
        lessons: [
          { lesson_key: 'l1', label: 'Tiết 2', title: '', position: 1, problem_count: 3, attempted: 0 },
          { lesson_key: 'l2', label: 'Tiết 3', title: '', position: 2, problem_count: 0, attempted: 0 },
        ],
      },
    ],
  },
]
const ASSIGNED = {
  id: 'a1',
  profile_id: 'p1',
  book_id: 'b1',
  unit_key: 'u1',
  lesson_key: 'l1',
  assigned_date: '2026-10-01',
  status: 'todo',
  carried_over: false,
  book_title_vi: 'Toán 1',
  unit_label: 'TUẦN 5',
  lesson_label: 'Tiết 2',
  lesson_title: '',
}

describe('tomorrowLocal', () => {
  it('is the next Ho Chi Minh calendar day', () => {
    expect(tomorrowLocal(new Date('2026-09-30T05:00:00Z'))).toBe('2026-10-01')
    // 20:00 UTC is already the next local day.
    expect(tomorrowLocal(new Date('2026-09-30T20:00:00Z'))).toBe('2026-10-02')
  })
})

describe('Assignments page', () => {
  it('assigns a Lesson and deletes a not-done Assignment', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } },
      'GET /api/v1/profiles': { status: 200, body: PROFILES },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
      'GET /api/v1/parent/assignments': { status: 200, body: [ASSIGNED] },
      'POST /api/v1/parent/assignments': { status: 201, body: ASSIGNED },
      'DELETE /api/v1/parent/assignments/a1': { status: 204 },
    })
    renderAt('/parent/assignments', <Assignments />)
    expect(await screen.findByTestId('assignment-a1')).toHaveTextContent('Chưa làm')

    const submit = screen.getByRole('button', { name: 'Giao bài' })
    expect(submit).toBeDisabled()
    fireEvent.change(await screen.findByLabelText('Sách'), { target: { value: 'b1' } })
    fireEvent.change(screen.getByLabelText('Tuần / bài'), { target: { value: 'u1' } })
    // A Lesson with no Problems is not offered.
    expect(screen.queryByRole('option', { name: /Tiết 3/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tiết'), { target: { value: 'l1' } })
    expect(screen.getByLabelText('Ngày')).toHaveValue(tomorrowLocal())
    fireEvent.click(submit)
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post?.[1]?.body as string)).toMatchObject({
        profile_id: 'p1',
        book_id: 'b1',
        unit_key: 'u1',
        lesson_key: 'l1',
      })
    })

    fireEvent.click(screen.getByRole('button', { name: 'Xóa' }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true),
    )
  })

  it('offers no delete for a done Assignment', async () => {
    mockApi({
      'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } },
      'GET /api/v1/profiles': { status: 200, body: PROFILES },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
      'GET /api/v1/parent/assignments': { status: 200, body: [{ ...ASSIGNED, status: 'done' }] },
    })
    renderAt('/parent/assignments', <Assignments />)
    expect(await screen.findByTestId('assignment-a1')).toHaveTextContent('Đã xong')
    expect(screen.queryByRole('button', { name: 'Xóa' })).not.toBeInTheDocument()
  })
})
