import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import ExamStart from './ExamStart'

const ENABLED_PROFILE = { id: 'p1', name: 'Bin', avatar: 'cat', grade: 1, exams_enabled: true }
const DISABLED_PROFILE = { ...ENABLED_PROFILE, exams_enabled: false }

const BOOKS = [
  {
    book_id: 'toan1-2020-q1',
    edition: '2020',
    grade: 1,
    volume: 1,
    title_vi: 'Toán 1 – Quyển 1 (2020)',
    units: [{ unit_key: 'tuan-5', label: 'TUẦN 5', title: '', position: 500, lessons: [] }],
  },
]

describe('ExamStart', () => {
  it('redirects to Library when exams_enabled is off', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: [DISABLED_PROFILE] },
    })
    renderAt('/exam/new', <ExamStart />)
    expect(await screen.findByText('library screen')).toBeInTheDocument()
  })

  it('starts a grade-scope exam and navigates to the Session', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: [ENABLED_PROFILE] },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
      'GET /api/v1/library/grades/1/concepts': { status: 200, body: [] },
      'POST /api/v1/sessions': {
        status: 201,
        body: {
          id: 'session-1',
          profile_id: 'p1',
          ref_kind: 'exam',
          problem_ids: ['a', 'b'],
          chunk_size: 10,
          mode: 'exam',
          started_at: '2026-10-02T10:00:00.000000+00:00',
          time_limit_s: 600,
        },
      },
    })
    renderAt('/exam/new', <ExamStart />)
    expect(await screen.findByText('Chọn đề kiểm tra')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu làm bài' }))
    expect(await screen.findByText('session player screen')).toBeInTheDocument()
  })

  it('requires a Book before submitting a book_unit-scope exam', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: [ENABLED_PROFILE] },
      'GET /api/v1/library/grades/1/books': { status: 200, body: BOOKS },
      'GET /api/v1/library/grades/1/concepts': { status: 200, body: [] },
    })
    renderAt('/exam/new', <ExamStart />)
    await screen.findByText('Chọn đề kiểm tra')
    fireEvent.click(screen.getByLabelText('Theo sách/tuần'))
    expect(screen.getByRole('button', { name: 'Bắt đầu làm bài' })).toBeDisabled()
  })
})
