import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../../test/render'
import type { ProblemDetail, ProblemDoc, ProblemPart } from '../../api/client'
import { PROBLEM_ID, detail, doc, summary } from '../../test/reviewFixtures'
import ProblemEditor from './ProblemEditor'

const BASE = `/api/v1/parent/review/problems/${PROBLEM_ID}`
const PATH = `/parent/review/problems/${PROBLEM_ID}`
const PATTERN = '/parent/review/problems/:problemId'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProblemEditor', () => {
  it('shows the source images and the editable fields', async () => {
    mockApi({ [`GET ${BASE}`]: { status: 200, body: detail() } })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    expect(await screen.findByRole('img', { name: 'Trang sách gốc' })).toHaveAttribute(
      'src',
      '/assets-data/pages/toan1-2020-q1/p012.jpg',
    )
    expect(screen.getByRole('img', { name: 'Ảnh cắt của bài' })).toBeInTheDocument()
    expect(screen.getByLabelText('Phần a đáp án s1')).toHaveValue('5')
    expect(screen.getByLabelText('Đề bài')).toHaveValue('Tính:')
  })

  it('shows a refused save inline with the validation messages', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`PUT ${BASE}/overrides`]: {
        status: 422,
        body: {
          error: {
            code: 'INVALID_OVERRIDE',
            message: 'Bản sửa không hợp lệ: Phần a › đáp án: sai định dạng',
            details: ['Phần a › đáp án: sai định dạng'],
          },
        },
      },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a đáp án s1'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Bản sửa không hợp lệ')
    expect(alert).toHaveTextContent('Phần a › đáp án: sai định dạng')
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      edits: [{ part_key: 'a', field: 'answer', value: [{ key: 's1', value: 'x' }] }],
    })
    // The edit stays in the form.
    expect(screen.getByLabelText('Phần a đáp án s1')).toHaveValue('x')
  })

  it('saves an edit and reverts it with Bỏ sửa', async () => {
    const edited = detail({
      effective: doc('6'),
      content_hash: 'h2',
      overrides: [
        { id: 'o1', part_key: 'a', field: 'answer', value: [{ key: 's1', value: '6' }], base_hash: 'b', conflict: null },
      ],
    })
    mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`PUT ${BASE}/overrides`]: { status: 200, body: edited },
      [`DELETE ${BASE}/overrides/o1`]: { status: 200, body: detail() },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a đáp án s1'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đã lưu.')
    expect(screen.getByText('Phần a › đáp án')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Bỏ sửa Phần a › đáp án' }))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Bỏ sửa/ })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('Đã bỏ sửa.')
    expect(screen.getByLabelText('Phần a đáp án s1')).toHaveValue('5')
  })

  it('approves and hides the problem', async () => {
    const approved = detail({
      summary: summary({ approved: true, visible: true }),
      status: { ...detail().status, approved_hash: 'h1', approved: true, visible: true },
    })
    const hidden = detail({
      summary: summary({ approved: true, hidden: true, visible: false }),
      status: { ...approved.status, hidden: true, visible: false },
    })
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`POST ${BASE}/approve`]: { status: 200, body: approved },
      [`POST ${BASE}/hide`]: { status: 200, body: hidden },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    expect(await screen.findByText('cần duyệt')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Duyệt' }))
    expect(await screen.findByText(/Bé đang thấy bài này · đã duyệt/)).toBeInTheDocument()
    expect(screen.queryByText('cần duyệt')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ẩn' }))
    expect(await screen.findByRole('button', { name: 'Hiện' })).toBeInTheDocument()
    expect(screen.getByText('đã ẩn')).toBeInTheDocument()
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts.map(([url]) => url)).toEqual([`${BASE}/approve`, `${BASE}/hide`])
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ content_hash: 'h1' })
  })

  it('unhides a hidden problem', async () => {
    const hidden = detail({
      summary: summary({ hidden: true, visible: false }),
      status: { ...detail().status, hidden: true },
    })
    mockApi({
      [`GET ${BASE}`]: { status: 200, body: hidden },
      [`POST ${BASE}/unhide`]: { status: 200, body: detail() },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: 'Hiện' }))
    expect(await screen.findByRole('button', { name: 'Ẩn' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Đã hiện.')
  })

  it('shows a stale approval and reloads the problem', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`POST ${BASE}/approve`]: {
        status: 409,
        body: { error: { code: 'STALE', message: 'Nội dung đã thay đổi từ khi mở.' } },
      },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: 'Duyệt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nội dung đã thay đổi từ khi mở.')
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url, init]) => url === BASE && !init?.method?.match(/POST/)).length).toBe(2),
    )
  })

  it('disables Duyệt and Ẩn while there are unsaved edits', async () => {
    mockApi({ [`GET ${BASE}`]: { status: 200, body: detail() } })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    const hint = await screen.findByLabelText('Phần a gợi ý')
    expect(screen.getByRole('button', { name: 'Duyệt' })).toBeEnabled()
    fireEvent.change(hint, { target: { value: 'Gợi ý mới' } })
    expect(screen.getByRole('button', { name: 'Duyệt' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Ẩn' })).toBeDisabled()
    expect(screen.getByText('Lưu trước khi duyệt.')).toBeInTheDocument()
    fireEvent.change(hint, { target: { value: 'Con đếm thêm 2 bắt đầu từ 3 nhé.' } })
    expect(screen.getByRole('button', { name: 'Duyệt' })).toBeEnabled()
  })

  it('asks before leaving with unsaved edits', async () => {
    mockApi({ [`GET ${BASE}`]: { status: 200, body: detail() } })
    const confirm = vi.fn(() => false)
    vi.stubGlobal('confirm', confirm)
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a gợi ý'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('link', { name: 'Duyệt nội dung' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(screen.queryByText('review screen')).not.toBeInTheDocument()
    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('link', { name: 'Duyệt nội dung' }))
    expect(await screen.findByText('review screen')).toBeInTheDocument()
  })

  it('resolves an open Error Report', async () => {
    const report = {
      id: 'r1',
      problem_id: PROBLEM_ID,
      kind: 'parent' as const,
      note: 'Sai đáp án',
      status: 'open' as const,
      created_at: '2026-09-27T00:00:00+00:00',
      resolved_at: null,
    }
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail({ reports: [report] }) },
      'POST /api/v1/parent/review/reports/r1/resolve': {
        status: 200,
        body: { ...report, status: 'resolved', resolved_at: '2026-09-27T01:00:00+00:00' },
      },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    expect(await screen.findByText(/Sai đáp án · đang mở/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Đã xử lý' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đã đánh dấu báo lỗi là đã xử lý.')
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/v1/parent/review/reports/r1/resolve')).toBe(true)
  })

  it('lists the overrides of an invalid effective doc and reverts them all', async () => {
    const override = { id: 'o1', part_key: 'a', field: 'answer' as const, value: [], base_hash: 'b', conflict: 'base_changed' as const }
    const invalid = detail({
      effective: null,
      content_hash: null,
      effective_error: ['Phần a: đáp án phải có đúng các ô (thiếu \'s2\')'],
      overrides: [override, { ...override, id: 'o2', part_key: null, field: 'instruction', conflict: null }],
    })
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: invalid },
      [`DELETE ${BASE}/overrides`]: { status: 200, body: detail() },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    expect(await screen.findByText(/thiếu 's2'/)).toBeInTheDocument()
    expect(screen.getByLabelText('Phần a đáp án s1')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Lưu' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Duyệt' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Bỏ sửa Phần a › đáp án' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Bỏ sửa đề bài' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Bỏ tất cả sửa đổi' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đã bỏ sửa.')
    expect(screen.getByLabelText('Phần a đáp án s1')).toBeEnabled()
    expect(fetchMock.mock.calls.some(([url, init]) => url === `${BASE}/overrides` && init?.method === 'DELETE')).toBe(true)
  })
})

function withPart(part: object, solutionSteps?: string[]): ProblemDetail {
  const d = doc()
  const base = d.parts[0]
  const replaced = { ...base, ...part } as unknown as ProblemPart
  if (solutionSteps) replaced.solution = { ...replaced.solution, steps: solutionSteps }
  const effective: ProblemDoc = { ...d, parts: [replaced] }
  return detail({ effective, extracted: effective as unknown as ProblemDetail['extracted'] })
}

async function saveAndGetBody(fetchMock: ReturnType<typeof mockApi>) {
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true))
  const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
  return JSON.parse(String(put?.[1]?.body))
}

describe('ProblemEditor edits', () => {
  const choice = {
    type: 'multiple_choice',
    options: [
      { option_key: 'o1', text: '1' },
      { option_key: 'o2', text: '2' },
    ],
    multi: true,
    answer: { selected: ['o1'] },
  }

  it('sends a list-type answer edit', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: withPart(choice) },
      [`PUT ${BASE}/overrides`]: { status: 200, body: withPart(choice) },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a đáp án'), { target: { value: 'o1, o2' } })
    expect(await saveAndGetBody(fetchMock)).toEqual({
      edits: [{ part_key: 'a', field: 'answer', value: { selected: ['o1', 'o2'] } }],
    })
  })

  it('sends only the part edit for a Part JSON replacement', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`PUT ${BASE}/overrides`]: { status: 200, body: detail() },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a gợi ý'), { target: { value: 'khác' } })
    const part = { ...doc().parts[0], hint: 'Gợi ý trong JSON' }
    fireEvent.change(screen.getByLabelText('Phần a JSON'), { target: { value: JSON.stringify(part) } })
    expect(await saveAndGetBody(fetchMock)).toEqual({ edits: [{ part_key: 'a', field: 'part', value: part }] })
  })

  it('shows invalid JSON inline without saving', async () => {
    const fetchMock = mockApi({ [`GET ${BASE}`]: { status: 200, body: detail() } })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a JSON'), { target: { value: '{oops' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Phần a: JSON không hợp lệ.')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })

  it('sends a solution steps edit', async () => {
    const fetchMock = mockApi({
      [`GET ${BASE}`]: { status: 200, body: detail() },
      [`PUT ${BASE}/overrides`]: { status: 200, body: detail() },
    })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.change(await screen.findByLabelText('Phần a lời giải'), {
      target: { value: 'Bước một\n\n  Bước hai  ' },
    })
    expect(await saveAndGetBody(fetchMock)).toEqual({
      edits: [
        { part_key: 'a', field: 'solution', value: { steps: ['Bước một', 'Bước hai'], final: '3 + 2 = 5' } },
      ],
    })
  })

  it('sends nothing for untouched fields, even untrimmed ones', async () => {
    const untrimmed = withPart({ answer: [{ key: 's1', value: ' 5' }] }, ['  Bước có khoảng trắng  ', ''])
    const fetchMock = mockApi({ [`GET ${BASE}`]: { status: 200, body: untrimmed } })
    renderAt(PATH, <ProblemEditor />, PATTERN)
    fireEvent.click(await screen.findByRole('button', { name: 'Lưu' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Không có thay đổi.')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })
})
