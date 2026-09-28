import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { spotCheck, spotItem } from '../../test/gateFixtures'
import { mockApi, renderAt } from '../../test/render'
import { PROBLEM_ID, detail, doc } from '../../test/reviewFixtures'
import { answerLines } from './answerText'
import SpotCheckTab from './SpotCheckTab'

const REVIEW = '/api/v1/parent/review'
const SECOND = 'toan1-2020-q1.tuan-5.tiet-2.bai-2'

afterEach(() => {
  vi.unstubAllGlobals()
})

function twoItems(first: Partial<Parameters<typeof spotItem>[0]> = {}) {
  return [
    spotItem(first),
    spotItem({ problem_id: SECOND, position: 2, display_label: 'Bài 2', content_hash: 'h9' }),
  ]
}

describe('SpotCheckTab', () => {
  it('offers to draw the first sample', async () => {
    mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([], { sample_id: null }) },
      [`POST ${REVIEW}/spot-check/draw`]: { status: 200, body: spotCheck(twoItems()) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    expect(await screen.findByText(/Chưa có mẫu kiểm tra/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rút mẫu mới' }))
    expect(await screen.findByLabelText('Tiến độ')).toHaveTextContent('0/2')
  })

  it('shows one Problem with its answer, hint and solution, and records Đúng', async () => {
    const judged = spotCheck(
      twoItems({ verdict: 'correct', verdict_hash: 'h1', checked_at: '2026-09-27T00:00:00Z' }),
    )
    const fetchMock = mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck(twoItems()) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
      [`GET ${REVIEW}/problems/${SECOND}`]: {
        status: 200,
        body: detail({ content_hash: 'h9' }),
      },
      [`PUT ${REVIEW}/spot-check/s1/items/${PROBLEM_ID}`]: { status: 200, body: judged },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    expect(await screen.findByLabelText('Tiến độ')).toHaveTextContent('0/2')
    expect(await screen.findByText('3 + 2 = 5', { selector: '.spot-answer-lines li' })).toBeInTheDocument()
    expect(screen.getByText(/Con đếm thêm 2 bắt đầu từ 3 nhé/)).toBeInTheDocument()
    expect(screen.getByText('Bắt đầu từ 3, đếm thêm 2: bốn, năm.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Ảnh cắt của bài' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sửa' })).toHaveAttribute(
      'href',
      `/parent/review/problems/${PROBLEM_ID}?from=spot-check`,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Đúng' }))
    expect(await screen.findByLabelText('Tiến độ')).toHaveTextContent('1/2')
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      verdict: 'correct',
      note: '',
      content_hash: 'h1',
    })
    // Moves on to the next Problem that needs a verdict.
    expect(await screen.findByRole('article', { name: 'Bài 2 trong mẫu' })).toBeInTheDocument()
  })

  it('records Sai with a note', async () => {
    const fetchMock = mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
      [`PUT ${REVIEW}/spot-check/s1/items/${PROBLEM_ID}`]: {
        status: 200,
        body: spotCheck([spotItem({ verdict: 'wrong', verdict_hash: 'h1', note: 'Đáp án là 6' })]),
      },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    fireEvent.change(await screen.findByLabelText(/Ghi chú/), { target: { value: 'Đáp án là 6' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sai' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Sai' }))
    expect(await screen.findByText('Sai', { selector: '.badge' })).toBeInTheDocument()
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(put?.[1]?.body))).toMatchObject({ verdict: 'wrong', note: 'Đáp án là 6' })
  })

  it('labels a stale verdict "cần kiểm tra lại" and does not count it', async () => {
    const items = [spotItem({ verdict: 'correct', verdict_hash: 'h0', stale: true })]
    mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck(items) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    expect(await screen.findByLabelText('Tiến độ')).toHaveTextContent('0/1')
    expect(screen.getAllByText(/cần kiểm tra lại/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('cần kiểm tra lại', { selector: '.badge' })).toHaveClass('badge-conflict')
  })

  it('renders a region overlay on the crop for an image_select answer', async () => {
    const base = doc()
    const imgDetail = detail({
      effective: {
        ...base,
        images: [{ image_key: 'im1', page: 12, bbox: [0, 0, 1, 1] }],
        parts: [
          {
            part_key: 'a',
            type: 'image_select',
            prompt: '',
            image_keys: [],
            image_key: 'im1',
            regions: [
              { region_key: 'r1', bbox: [0.1, 0.1, 0.4, 0.4] },
              { region_key: 'r2', bbox: [0.5, 0.5, 0.9, 0.9] },
            ],
            multi: false,
            hint: 'h',
            solution: { steps: ['x'], final: 'y' },
            answer: { selected: ['r2'] },
          },
        ],
      },
      crop_urls: [
        `/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/_problem.jpg`,
        `/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/im1.jpg`,
      ],
    })
    mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: imgDetail },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    const overlayImg = await screen.findByRole('img', { name: 'Vùng chọn của phần a' })
    expect(overlayImg).toHaveAttribute(
      'src',
      `/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/im1.jpg`,
    )
    expect(document.querySelectorAll('.answer-region')).toHaveLength(2)
    expect(document.querySelector('.answer-region-selected')).toHaveTextContent('r2')
  })

  it('refetches the problem and the spot-check after a 409 STALE verdict', async () => {
    const fetchMock = mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
      [`PUT ${REVIEW}/spot-check/s1/items/${PROBLEM_ID}`]: {
        status: 409,
        body: { error: { code: 'STALE', message: 'Nội dung đã thay đổi từ khi mở. Hãy xem lại.' } },
      },
    })
    const gets = (url: string) =>
      fetchMock.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === 'GET').length
    renderAt('/parent/review', <SpotCheckTab />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Đúng' })).toBeEnabled())
    expect(gets(`${REVIEW}/spot-check`)).toBe(1)
    expect(gets(`${REVIEW}/problems/${PROBLEM_ID}`)).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: 'Đúng' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nội dung đã thay đổi từ khi mở.')
    await waitFor(() => expect(gets(`${REVIEW}/spot-check`)).toBe(2))
    await waitFor(() => expect(gets(`${REVIEW}/problems/${PROBLEM_ID}`)).toBe(2))
  })

  it('renders the differences on the right image for a spot_difference answer', async () => {
    const base = doc()
    const crops = ['_problem', 'tranh-trai', 'tranh-phai'].map(
      (k) => `/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/${k}.jpg`,
    )
    const diffDetail = detail({
      effective: {
        ...base,
        images: [
          { image_key: 'tranh-trai', page: 12, bbox: [0.05, 0.3, 0.48, 0.7] },
          { image_key: 'tranh-phai', page: 12, bbox: [0.52, 0.3, 0.95, 0.7] },
        ],
        parts: [
          {
            part_key: 'p1',
            type: 'spot_difference',
            prompt: '',
            image_keys: [],
            image_left: 'tranh-trai',
            image_right: 'tranh-phai',
            count: 2,
            answer: {
              regions: [
                { region_key: 'd1', bbox: [0.1, 0.1, 0.3, 0.3] },
                { region_key: 'd2', bbox: [0.5, 0.4, 0.7, 0.6] },
              ],
            },
            hint: 'h',
            solution: { steps: ['x'], final: 'y' },
          },
        ],
      },
      crop_urls: crops,
    })
    mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: diffDetail },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    const left = await screen.findByRole('img', { name: 'Ảnh gốc của phần p1' })
    const right = screen.getByRole('img', { name: 'Ảnh có điểm khác biệt của phần p1' })
    expect(left).toHaveAttribute('src', crops[1])
    expect(right).toHaveAttribute('src', crops[2])
    expect(left.parentElement?.querySelectorAll('.answer-region')).toHaveLength(0)
    const boxes = right.parentElement?.querySelectorAll('.answer-region-selected') ?? []
    expect(Array.from(boxes).map((b) => b.textContent)).toEqual(['d1', 'd2'])
    expect((boxes[1] as HTMLElement).style.left).toBe('50%')
  })

  it('renders numbered dots and their path for a connect_dots answer', async () => {
    const base = doc()
    const crop = `/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/con-ca.jpg`
    const dotsDetail = detail({
      effective: {
        ...base,
        images: [{ image_key: 'con-ca', page: 12, bbox: [0.15, 0.3, 0.85, 0.7] }],
        parts: [
          {
            part_key: 'p1',
            type: 'connect_dots',
            prompt: '',
            image_keys: [],
            image_key: 'con-ca',
            dots: [
              { n: 1, x: 0.1, y: 0.5 },
              { n: 2, x: 0.3, y: 0.2 },
              { n: 3, x: 0.6, y: 0.25 },
            ],
            answer: { sequence: [1, 2, 3] },
            hint: 'h',
            solution: { steps: ['x'], final: 'y' },
          },
        ],
      },
      crop_urls: [`/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/_problem.jpg`, crop],
    })
    mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: dotsDetail },
    })
    renderAt('/parent/review', <SpotCheckTab />)
    const img = await screen.findByRole('img', { name: 'Các điểm nối của phần p1' })
    expect(img).toHaveAttribute('src', crop)
    const dots = Array.from(document.querySelectorAll<HTMLElement>('.answer-dot'))
    expect(dots.map((d) => d.textContent)).toEqual(['1', '2', '3'])
    expect(dots[1].style.left).toBe('30%')
    expect(dots[1].style.top).toBe('20%')
    expect(document.querySelector('.answer-dot-lines polyline')).toHaveAttribute(
      'points',
      '10,50 30,20 60,25',
    )
  })

  it('asks before drawing a new sample over an existing one', async () => {
    const fetchMock = mockApi({
      [`GET ${REVIEW}/spot-check`]: { status: 200, body: spotCheck([spotItem()]) },
      [`GET ${REVIEW}/problems/${PROBLEM_ID}`]: { status: 200, body: detail() },
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderAt('/parent/review', <SpotCheckTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'Rút mẫu mới' }))
    expect(confirm).toHaveBeenCalled()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    confirm.mockRestore()
  })
})

describe('answerLines', () => {
  it('renders each Problem Type readably', () => {
    expect(answerLines(doc('5').parts[0])).toEqual(['3 + 2 = 5'])
    expect(
      answerLines({
        part_key: 'a',
        type: 'compare',
        prompt: '',
        image_keys: [],
        rows: [{ slot_key: 's1', left: '3', right: '5' }],
        answer: [{ key: 's1', value: '<' }],
        hint: 'h',
        solution: { steps: ['x'], final: 'y' },
      }),
    ).toEqual(['3 < 5'])
    expect(
      answerLines({
        part_key: 'a',
        type: 'order',
        prompt: '',
        image_keys: [],
        direction: 'asc',
        items: [
          { item_key: 'i1', text: '7' },
          { item_key: 'i2', text: '2' },
        ],
        answer: { order: ['i2', 'i1'] },
        hint: 'h',
        solution: { steps: ['x'], final: 'y' },
      }),
    ).toEqual(['2 → 7'])
  })
})
