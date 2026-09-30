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

  it('edits, resets and approves a Concept Guide', async () => {
    const concept = {
      concept_id: 'g1.so-sanh-so',
      grade: 1,
      name_vi: 'So sánh số',
      problem_count: 3,
      has_guide: true,
      guide_source: 'problems',
      guide_conflict: false,
      guide_approved: false,
    }
    const generated = {
      explanation: 'Số nào có nhiều chục hơn thì lớn hơn.',
      example: { question: 'So sánh 35 và 28', steps: ['3 chục lớn hơn 2 chục'], answer: '35 > 28' },
    }
    const guide = {
      concept_id: 'g1.so-sanh-so',
      source: 'problems',
      model: 'm',
      generated_at: 't',
      generated,
      effective: generated,
      content_hash: 'h1',
      approved: false,
      conflict: false,
      overrides: [],
    }
    const edited = {
      ...guide,
      effective: { ...generated, explanation: 'Nhìn hàng chục trước.' },
      content_hash: 'h2',
      conflict: true,
      overrides: [
        { field: 'explanation', value: 'Nhìn hàng chục trước.', base_hash: 'b', conflict: true },
      ],
    }
    const base = '/api/v1/parent/review/concepts/g1.so-sanh-so/guide'
    const fetchMock = mockApi({
      'GET /api/v1/parent/review/concepts': {
        status: 200,
        body: { proposals: [], concepts: [concept] },
      },
      [`GET ${base}`]: { status: 200, body: guide },
      [`PUT ${base}`]: { status: 200, body: edited },
      [`POST ${base}/approve`]: { status: 200, body: { ...edited, approved: true, conflict: false } },
    })
    renderAt('/parent/review', <ConceptsTab />)
    expect(await screen.findByText('hướng dẫn chưa duyệt')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hướng dẫn' }))
    const box = await screen.findByLabelText('Giải thích')
    expect(screen.getByText('chưa duyệt')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lưu hướng dẫn' })).toBeDisabled()
    fireEvent.change(box, { target: { value: 'Nhìn hàng chục trước.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu hướng dẫn' }))
    expect(await screen.findByText(/xung đột: bản sinh lại/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Duyệt hướng dẫn' }))
    expect(await screen.findByText('đã duyệt')).toBeInTheDocument()
    const sent = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(sent[0]?.[1]?.body))).toEqual({
      edits: [{ field: 'explanation', value: 'Nhìn hàng chục trước.' }],
    })
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ content_hash: 'h2' })
  })

  it('shows an error when the concepts cannot be loaded', async () => {
    mockApi({ 'GET /api/v1/parent/review/concepts': { status: 502 } })
    renderAt('/parent/review', <ConceptsTab />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
  })
})
