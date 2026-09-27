import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../../test/render'
import { spotCheck } from '../../test/gateFixtures'
import { summary } from '../../test/reviewFixtures'
import ReviewPage from './ReviewPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ReviewPage', () => {
  it('lists the review queue with badges', async () => {
    mockApi({
      'GET /api/v1/parent/review/queue': {
        status: 200,
        body: [
          summary({ awaiting_approval: true, conflict: true }),
          summary({
            problem_id: 'toan1-2020-q1.tuan-5.tiet-2.bai-2',
            display_label: 'Bài 2',
            report: true,
            hidden: true,
            duplicate: true,
          }),
        ],
      },
    })
    renderAt('/parent/review', <ReviewPage />)
    expect(screen.getByRole('heading', { name: 'Duyệt nội dung' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Cần duyệt' })).toHaveAttribute('aria-selected', 'true')
    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]).getByText('cần duyệt')).toBeInTheDocument()
    expect(within(items[0]).getByText('xung đột')).toBeInTheDocument()
    expect(within(items[0]).queryByText('đã ẩn')).not.toBeInTheDocument()
    for (const badge of ['báo lỗi', 'đã ẩn', 'trùng']) {
      expect(within(items[1]).getByText(badge)).toBeInTheDocument()
    }
    expect(within(items[0]).getByRole('link')).toHaveAttribute(
      'href',
      '/parent/review/problems/toan1-2020-q1.tuan-5.tiet-2.bai-1',
    )
  })

  it('shows the empty queue message', async () => {
    mockApi({ 'GET /api/v1/parent/review/queue': { status: 200, body: [] } })
    renderAt('/parent/review', <ReviewPage />)
    expect(await screen.findByText('Không có bài cần duyệt.')).toBeInTheDocument()
  })

  it('lists all problems by book on the Tất cả tab', async () => {
    mockApi({
      'GET /api/v1/parent/review/queue': { status: 200, body: [] },
      'GET /api/v1/parent/review/books': {
        status: 200,
        body: [
          {
            book_id: 'toan1-2020-q1',
            title_vi: 'Toán 1 – Quyển 1 (2020)',
            problem_count: 1,
            units: [{ unit_key: 'tuan-5', label: 'TUẦN 5', lessons: [{ lesson_key: 'tiet-2', label: 'Tiết 2' }] }],
          },
        ],
      },
      'GET /api/v1/parent/review/problems': {
        status: 200,
        body: { items: [summary()], total: 1, page: 1, page_size: 50 },
      },
    })
    renderAt('/parent/review', <ReviewPage />)
    fireEvent.click(screen.getByRole('tab', { name: 'Tất cả' }))
    expect(await screen.findByText('1 bài')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Bài 1/ })).toBeInTheDocument()
    expect(await screen.findByRole('option', { name: 'Toán 1 – Quyển 1 (2020) (1)' })).toBeInTheDocument()
  })

  it('filters by book, unit and lesson and pages through the list', async () => {
    const items = (n: number) =>
      Array.from({ length: n }, (_, i) =>
        summary({ problem_id: `toan1-2020-q1.tuan-5.tiet-2.bai-${i}`, display_label: `Bài ${i}` }),
      )
    const fetchMock = mockApi({
      'GET /api/v1/parent/review/books': {
        status: 200,
        body: [
          {
            book_id: 'toan1-2020-q1',
            title_vi: 'Toán 1',
            problem_count: 55,
            units: [{ unit_key: 'tuan-5', label: 'TUẦN 5', lessons: [{ lesson_key: 'tiet-2', label: 'Tiết 2' }] }],
          },
        ],
      },
      'GET /api/v1/parent/review/problems': {
        status: 200,
        body: { items: items(50), total: 55, page: 1, page_size: 50 },
      },
      'GET /api/v1/parent/review/problems?book_id=toan1-2020-q1&unit_key=tuan-5&lesson_key=tiet-2&page=2': {
        status: 200,
        body: { items: items(5), total: 55, page: 2, page_size: 50 },
      },
    })
    const { router } = renderAt('/parent/review?tab=all', <ReviewPage />, '/parent/review')
    expect(await screen.findByText('Trang 1/2')).toBeInTheDocument()
    fireEvent.change(await screen.findByLabelText(/Sách/), { target: { value: 'toan1-2020-q1' } })
    fireEvent.change(await screen.findByLabelText(/Tuần\/Chương/), { target: { value: 'tuan-5' } })
    fireEvent.change(await screen.findByLabelText(/Bài học/), { target: { value: 'tiet-2' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Trang sau' }))
    expect(await screen.findByText('Trang 2/2')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(5)
    expect(router.state.location.search).toBe('?tab=all&book=toan1-2020-q1&unit=tuan-5&lesson=tiet-2&page=2')
    expect(fetchMock.mock.calls.map(([url]) => url)).toContain(
      '/api/v1/parent/review/problems?book_id=toan1-2020-q1&unit_key=tuan-5&lesson_key=tiet-2&page=2',
    )
  })

  it('goes back to the last page when the list shrank', async () => {
    mockApi({
      'GET /api/v1/parent/review/books': { status: 200, body: [] },
      'GET /api/v1/parent/review/problems?page=3': {
        status: 200,
        body: { items: [], total: 10, page: 3, page_size: 50 },
      },
      'GET /api/v1/parent/review/problems': {
        status: 200,
        body: { items: [summary()], total: 10, page: 1, page_size: 50 },
      },
    })
    const { router } = renderAt('/parent/review?tab=all&page=3', <ReviewPage />, '/parent/review')
    await waitFor(() => expect(router.state.location.search).toBe('?tab=all'))
    expect(await screen.findByRole('link', { name: /Bài 1/ })).toBeInTheDocument()
  })

  it('shows a books error', async () => {
    mockApi({
      'GET /api/v1/parent/review/books': { status: 502 },
      'GET /api/v1/parent/review/problems': {
        status: 200,
        body: { items: [], total: 0, page: 1, page_size: 50 },
      },
    })
    renderAt('/parent/review?tab=all', <ReviewPage />, '/parent/review')
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tải được danh sách sách')
  })

  it('opens the Kiểm tra ngẫu nhiên tab', async () => {
    mockApi({
      'GET /api/v1/parent/review/queue': { status: 200, body: [] },
      'GET /api/v1/parent/review/spot-check': { status: 200, body: spotCheck([], { sample_id: null }) },
    })
    const { router } = renderAt('/parent/review', <ReviewPage />)
    fireEvent.click(screen.getByRole('tab', { name: 'Kiểm tra ngẫu nhiên' }))
    expect(await screen.findByText(/Chưa có mẫu kiểm tra/)).toBeInTheDocument()
    expect(router.state.location.search).toBe('?tab=spot-check')
  })
})
