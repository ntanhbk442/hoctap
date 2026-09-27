import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { gateReport } from '../test/gateFixtures'
import { mockApi, renderAt } from '../test/render'
import GateCard from './GateCard'

const GATE = '/api/v1/build/gate'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GateCard', () => {
  it('shows "chưa chạy thử" without a pilot', async () => {
    mockApi({ [`GET ${GATE}`]: { status: 200, body: gateReport({ has_pilot: false, pilot_pages: 0 }) } })
    renderAt('/parent', <GateCard />)
    expect(await screen.findByText('Chưa chạy thử.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Duyệt chạy toàn bộ' })).not.toBeInTheDocument()
  })

  it('shows the checks and cost; approve is enabled only after ticking the checkbox', async () => {
    const approved = gateReport({
      approved: true,
      approval: {
        id: 'g1',
        approved_at: '2026-09-27T10:00:00+00:00',
        est_cost: 424.8,
        sample_id: 's1',
        valid: true,
        invalid_reasons: [],
      },
    })
    const fetchMock = mockApi({
      [`GET ${GATE}`]: { status: 200, body: gateReport() },
      [`POST ${GATE}/approve`]: { status: 200, body: approved },
    })
    renderAt('/parent', <GateCard />)
    const checks = await screen.findByRole('list', { name: 'Tiêu chí' })
    const items = within(checks).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveClass('check-pass')
    expect(items[0]).toHaveTextContent('5.0% (2/40), tối đa 15.0%')
    expect(items[1]).toHaveTextContent('100.0% (30/30), tối thiểu 98.0%')
    expect(screen.getByText('$424.80')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Duyệt chạy toàn bộ' })
    expect(button).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Tôi chấp nhận chi phí ước tính $424.80'))
    expect(button).toBeEnabled()
    fireEvent.click(button)
    expect(await screen.findByText('Đã duyệt')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ accept_cost: true, est_cost_seen: 424.8 })
    expect(screen.getByRole('button', { name: 'Thu hồi' })).toBeInTheDocument()
  })

  it('keeps approve disabled while a check fails, even with the checkbox', async () => {
    mockApi({
      [`GET ${GATE}`]: {
        status: 200,
        body: gateReport({
          checks_passed: false,
          accuracy: {
            passed: false,
            value: 1,
            correct: 12,
            sample_size: 12,
            enough_sample: false,
            stale: 1,
          },
          fallback: { passed: false, value: 0.175, with_fallback: 7 },
          cost: { unknown_cost_calls: 2 },
        }),
      },
    })
    renderAt('/parent', <GateCard />)
    const checks = await screen.findByRole('list', { name: 'Tiêu chí' })
    const items = within(checks).getAllByRole('listitem')
    expect(items[0]).toHaveClass('check-fail')
    expect(items[0]).toHaveTextContent('17.5% (7/40)')
    expect(items[1]).toHaveClass('check-fail')
    expect(items[1]).toHaveTextContent('chưa đủ mẫu (12/30)')
    expect(items[1]).toHaveTextContent('1 bài cần kiểm tra lại')
    expect(screen.getByText(/2 lượt gọi chưa rõ chi phí/)).toBeInTheDocument()
    const box = screen.getByLabelText('Tôi chấp nhận chi phí ước tính $424.80')
    expect(box).toBeDisabled()
    fireEvent.click(box)
    expect(screen.getByRole('button', { name: 'Duyệt chạy toàn bộ' })).toBeDisabled()
  })

  it('shows a changed estimate and asks again', async () => {
    mockApi({
      [`GET ${GATE}`]: { status: 200, body: gateReport() },
      [`POST ${GATE}/approve`]: {
        status: 409,
        body: { error: { code: 'ESTIMATE_CHANGED', message: 'Chi phí ước tính đã thay đổi thành $430.00.' } },
      },
    })
    renderAt('/parent', <GateCard />)
    fireEvent.click(await screen.findByLabelText('Tôi chấp nhận chi phí ước tính $424.80'))
    fireEvent.click(screen.getByRole('button', { name: 'Duyệt chạy toàn bộ' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('đã thay đổi')
    expect(screen.getByLabelText('Tôi chấp nhận chi phí ước tính $424.80')).not.toBeChecked()
  })

  it('revokes an approval', async () => {
    const approval = {
      id: 'g1',
      approved_at: '2026-09-27T10:00:00+00:00',
      est_cost: 424.8,
      sample_id: 's1',
      valid: true,
      invalid_reasons: [],
    }
    mockApi({
      [`GET ${GATE}`]: { status: 200, body: gateReport({ approved: true, approval }) },
      [`POST ${GATE}/revoke`]: { status: 200, body: gateReport() },
    })
    renderAt('/parent', <GateCard />)
    fireEvent.click(await screen.findByRole('button', { name: 'Thu hồi' }))
    expect(await screen.findByRole('button', { name: 'Duyệt chạy toàn bộ' })).toBeDisabled()
    expect(screen.queryByText('Đã duyệt')).not.toBeInTheDocument()
  })

  it('explains an approval that no longer holds', async () => {
    mockApi({
      [`GET ${GATE}`]: {
        status: 200,
        body: gateReport({
          approval: {
            id: 'g1',
            approved_at: '2026-09-27T10:00:00+00:00',
            est_cost: 424.8,
            sample_id: 's1',
            valid: false,
            invalid_reasons: ['Phạm vi chạy thử đã thay đổi (có trang mới).'],
          },
        }),
      },
    })
    renderAt('/parent', <GateCard />)
    expect(await screen.findByText(/Lần duyệt trước không còn hiệu lực/)).toHaveTextContent(
      'có trang mới',
    )
  })
})
