import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildRun, catalogueBook } from '../test/runFixtures'
import { mockApi, renderAt } from '../test/render'
import ExtractionPage from './ExtractionPage'

const RUNS = '/api/v1/build/runs'
const BOOKS = '/api/v1/build/books'
const CURRENT = `${RUNS}/current`

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ExtractionPage', () => {
  it('shows the picker when there is no run, and starts one', async () => {
    mockApi({
      [`GET ${CURRENT}`]: { status: 200, body: null },
      [`GET ${BOOKS}`]: { status: 200, body: [catalogueBook()] },
      [`POST ${RUNS}`]: {
        status: 202,
        body: buildRun({ status: 'running', pages_done: 0, first_page: 6, last_page: 7 }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    expect(screen.getByRole('heading', { name: 'Chạy thử (pilot)' })).toBeInTheDocument()
    const select = await screen.findByLabelText('Sách')
    fireEvent.change(select, { target: { value: 'toan1-2020-q1' } })
    fireEvent.change(screen.getByLabelText('Từ trang'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Đến trang'), { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Chạy thử' }))
    expect(await screen.findByText(/toan1-2020-q1: trang 6-7/)).toBeInTheDocument()
  })

  it('asks to confirm the spend, then starts on confirm', async () => {
    mockApi({
      [`GET ${CURRENT}`]: { status: 200, body: null },
      [`GET ${BOOKS}`]: { status: 200, body: [catalogueBook()] },
      [`POST ${RUNS}`]: {
        status: 422,
        body: { error: { code: 'SPEND_NOT_CONFIRMED', message: 'Ước tính: 2 trang, ~$0.20.' } },
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    fireEvent.change(await screen.findByLabelText('Sách'), { target: { value: 'toan1-2020-q1' } })
    fireEvent.change(screen.getByLabelText('Từ trang'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Chạy thử' }))
    expect(await screen.findByText(/Ước tính: 2 trang/)).toBeInTheDocument()
    mockApi({
      [`GET ${CURRENT}`]: { status: 200, body: null },
      [`GET ${BOOKS}`]: { status: 200, body: [catalogueBook()] },
      [`POST ${RUNS}`]: { status: 202, body: buildRun({ pages_done: 0 }) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận & chạy' }))
    expect(await screen.findByText(/toan1-2020-q1: trang 5-7/)).toBeInTheDocument()
  })

  it('shows an active run instead of the picker on mount', async () => {
    mockApi({ [`GET ${CURRENT}`]: { status: 200, body: buildRun() } })
    renderAt('/parent/extraction', <ExtractionPage />)
    expect(await screen.findByText(/toan1-2020-q1: trang 5-7/)).toBeInTheDocument()
    expect(screen.getByText(/Đang trích xuất trang 6\/7/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Sách')).not.toBeInTheDocument()
  })

  it('pauses a running run', async () => {
    mockApi({
      [`GET ${CURRENT}`]: { status: 200, body: buildRun() },
      [`POST ${RUNS}/run1/pause`]: {
        status: 200,
        body: buildRun({ status: 'pausing', activity: 'Đang dừng…' }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Tạm dừng' }))
    expect(await screen.findByRole('button', { name: 'Đang dừng…' })).toBeDisabled()
  })

  it('resumes a paused run', async () => {
    mockApi({
      [`GET ${CURRENT}`]: {
        status: 200,
        body: buildRun({ status: 'paused', activity: 'Đã tạm dừng' }),
      },
      [`POST ${RUNS}/run1/resume`]: {
        status: 200,
        body: buildRun({ id: 'run2', resumed_from: 'run1', status: 'running' }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Tiếp tục' }))
    expect(await screen.findByText(/Đang trích xuất trang 6\/7/)).toBeInTheDocument()
  })

  it('cancels a run', async () => {
    mockApi({
      [`GET ${CURRENT}`]: { status: 200, body: buildRun() },
      [`POST ${RUNS}/run1/cancel`]: {
        status: 200,
        body: buildRun({ status: 'cancelled', activity: 'Đã hủy' }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Hủy' }))
    expect(await screen.findByText('Đã hủy')).toBeInTheDocument()
  })

  it('lists failed pages and offers picking again once the run settles', async () => {
    mockApi({
      [`GET ${CURRENT}`]: {
        status: 200,
        body: buildRun({
          status: 'done',
          activity: 'Đã xong',
          pages_done: 2,
          failed_pages: [{ page: 6, stage: 'extract', reason: 'refusal: cannot read the page' }],
        }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    expect(await screen.findByText('1 trang lỗi:')).toBeInTheDocument()
    expect(screen.getByText(/Trang 6 \(extract\): refusal/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chọn sách và trang khác' }))
    expect(await screen.findByLabelText('Sách')).toBeInTheDocument()
  })

  it('offers Tiếp tục for a stale running row', async () => {
    mockApi({
      [`GET ${CURRENT}`]: {
        status: 200,
        body: buildRun({ status: 'running', stale: true }),
      },
      [`POST ${RUNS}/run1/resume`]: {
        status: 200,
        body: buildRun({ id: 'run2', resumed_from: 'run1' }),
      },
    })
    renderAt('/parent/extraction', <ExtractionPage />)
    expect(await screen.findByText(/Không thấy tiến triển/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tiếp tục' })).toBeInTheDocument()
  })
})
