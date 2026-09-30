import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PROBLEM_ID, detail } from '../test/reviewFixtures'
import { mockApi, renderAt } from '../test/render'
import ProblemPreview from './ProblemPreview'

afterEach(() => {
  vi.unstubAllGlobals()
})

const BASE = `/api/v1/parent/review/problems/${PROBLEM_ID}`
const PATH = `/parent/problems/${PROBLEM_ID}`
const PATTERN = '/parent/problems/:problemId'

describe('ProblemPreview', () => {
  it('shows the Problem read-only and reports it with a note', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`POST ${BASE}/reports`]: {
        status: 200,
        body: {
          id: 'r1',
          problem_id: PROBLEM_ID,
          kind: 'parent',
          note: 'sai',
          status: 'open',
          created_at: 'x',
          resolved_at: null,
        },
      },
    })
    renderAt(PATH, <ProblemPreview />, PATTERN)
    expect(await screen.findByText(/Đáp án:/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Ảnh cắt của bài' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Đề bài' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ghi chú (không bắt buộc)'), {
      target: { value: 'sai' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Báo lỗi' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đã báo lỗi')
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ note: 'sai' })
  })

  it('shows a not-found state for an unknown Problem', async () => {
    mockApi({
      [`GET ${BASE}`]: {
        status: 404,
        body: { error: { code: 'PROBLEM_NOT_FOUND', message: 'Không tìm thấy bài.' } },
      },
    })
    renderAt(PATH, <ProblemPreview />, PATTERN)
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tìm thấy bài.')
  })

  it('sends a missing cookie to the PIN gate', async () => {
    mockApi({
      [`GET ${BASE}`]: {
        status: 401,
        body: { error: { code: 'UNAUTHORIZED', message: 'x' } },
      },
    })
    renderAt(PATH, <ProblemPreview />, PATTERN)
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })
})
