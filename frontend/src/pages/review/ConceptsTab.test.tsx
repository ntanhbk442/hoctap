import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../../test/render'
import ConceptsTab from './ConceptsTab'

afterEach(() => {
  vi.unstubAllGlobals()
})

const PROPOSAL = {
  proposal_key: 'so sánh số',
  grade: 1,
  text: 'So sánh số',
  problem_count: 3,
  status: 'proposed',
  target_concept_id: null,
}

describe('ConceptsTab', () => {
  it('accepts a proposal', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/parent/review/concepts': {
        status: 200,
        body: { proposals: [PROPOSAL], concepts: [] },
      },
      'POST /api/v1/parent/review/concepts/accept': {
        status: 200,
        body: {
          proposals: [{ ...PROPOSAL, status: 'accepted', target_concept_id: 'g1.so-sanh-so' }],
          concepts: [{ concept_id: 'g1.so-sanh-so', grade: 1, name_vi: 'So sánh số', problem_count: 3 }],
        },
      },
    })
    renderAt('/parent/review', <ConceptsTab />)
    expect(await screen.findByRole('heading', { name: 'Lớp 1' })).toBeInTheDocument()
    expect(screen.getByText(/3 bài · đề xuất/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Nhận' }))
    expect(await screen.findByText('g1.so-sanh-so')).toBeInTheDocument()
    expect(screen.getByText(/đã nhận/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nhận' })).not.toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ grade: 1, proposal_key: 'so sánh số' })
  })

  it('merges a proposal into an existing concept and renames a concept', async () => {
    const other = { ...PROPOSAL, proposal_key: 'so sánh các số', text: 'So sánh các số', problem_count: 1 }
    const concept = { concept_id: 'g1.so-sanh-so', grade: 1, name_vi: 'So sánh số', problem_count: 3 }
    const fetchMock = mockApi({
      'GET /api/v1/parent/review/concepts': {
        status: 200,
        body: { proposals: [other], concepts: [concept] },
      },
      'POST /api/v1/parent/review/concepts/merge': {
        status: 200,
        body: {
          proposals: [{ ...other, status: 'merged', target_concept_id: 'g1.so-sanh-so' }],
          concepts: [{ ...concept, problem_count: 4 }],
        },
      },
      'POST /api/v1/parent/review/concepts/rename': {
        status: 200,
        body: {
          proposals: [{ ...other, status: 'merged', target_concept_id: 'g1.so-sanh-so' }],
          concepts: [{ ...concept, name_vi: 'So sánh hai số', problem_count: 4 }],
        },
      },
    })
    renderAt('/parent/review', <ConceptsTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'Gộp vào…' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'g1.so-sanh-so' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gộp' }))
    expect(await screen.findByText(/đã gộp/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Đổi tên' }))
    fireEvent.change(screen.getByLabelText('Tên mới cho g1.so-sanh-so'), {
      target: { value: 'So sánh hai số' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    expect(await screen.findByText('So sánh hai số')).toBeInTheDocument()
    const bodies = fetchMock.mock.calls
      .filter(([, init]) => init?.method === 'POST')
      .map(([, init]) => JSON.parse(String(init?.body)))
    expect(bodies).toEqual([
      { grade: 1, proposal_key: 'so sánh các số', concept_id: 'g1.so-sanh-so' },
      { concept_id: 'g1.so-sanh-so', name_vi: 'So sánh hai số' },
    ])
  })

  it('shows an error when the concepts cannot be loaded', async () => {
    mockApi({ 'GET /api/v1/parent/review/concepts': { status: 502 } })
    renderAt('/parent/review', <ConceptsTab />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
  })
})
