import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'
import Badges from './Badges'

vi.mock('../audio/speech', () => ({ speak: vi.fn(() => Promise.resolve()) }))

const PROFILE_ID = 'p1'
const ONE_PROFILE = [{ id: PROFILE_ID, name: 'Bin', avatar: 'cat', grade: 1 }]

const TWO_EARNED = {
  status: 200,
  body: [
    { badge_key: 'week1', earned: true, earned_at: '2026-09-01T00:00:00+00:00' },
    { badge_key: 'streak7', earned: false, earned_at: null },
    { badge_key: 'stars100', earned: true, earned_at: '2026-09-02T00:00:00+00:00' },
  ],
}

const ALL_UNEARNED = {
  status: 200,
  body: [
    { badge_key: 'week1', earned: false, earned_at: null },
    { badge_key: 'streak7', earned: false, earned_at: null },
    { badge_key: 'stars100', earned: false, earned_at: null },
  ],
}

beforeEach(() => {
  sessionStorage.clear()
  setCurrentProfileId(PROFILE_ID)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Badges ("Huy hiệu của em")', () => {
  it('shows all 3 badges, earned ones normal, unearned ones greyed with their own 🔊', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/profiles/p1/badges': TWO_EARNED,
    })
    renderAt('/badges', <Badges />, '/badges')
    const grid = await screen.findByTestId('badges-grid')
    expect(grid).toBeInTheDocument()

    const week1 = screen.getByTestId('badge-week1')
    expect(week1.className).toContain('badge-earned')

    const stars100 = screen.getByTestId('badge-stars100')
    expect(stars100.className).toContain('badge-earned')

    const streak7 = screen.getByTestId('badge-streak7')
    expect(streak7.className).toContain('badge-unearned')

    // The unearned badge has its own 🔊 explaining how to earn it.
    const speaker = screen.getByRole('button', {
      name: 'Nghe: Học liên tiếp 7 ngày để nhận huy hiệu này.',
    })
    const { speak } = await import('../audio/speech')
    fireEvent.click(speaker)
    expect(speak).toHaveBeenCalledWith('Học liên tiếp 7 ngày để nhận huy hiệu này.')
  })

  it('shows all 3 greyed out for a fresh Profile with 0 badges earned', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/profiles/p1/badges': ALL_UNEARNED,
    })
    renderAt('/badges', <Badges />, '/badges')
    await screen.findByTestId('badges-grid')
    for (const key of ['week1', 'streak7', 'stars100']) {
      expect(screen.getByTestId(`badge-${key}`).className).toContain('badge-unearned')
    }
  })

  it('shows an error with retry when the badges fetch fails', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/profiles/p1/badges': { status: 502 },
    })
    renderAt('/badges', <Badges />, '/badges')
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã xảy ra lỗi. Vui lòng thử lại.')
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/profiles/p1/badges': TWO_EARNED,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('badges-grid')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalled()
  })

  it('goes back to Home via the ChildTopBar back button', async () => {
    mockApi({
      'GET /api/v1/profiles': { status: 200, body: ONE_PROFILE },
      'GET /api/v1/profiles/p1/badges': TWO_EARNED,
    })
    renderAt('/badges', <Badges />, '/badges')
    await screen.findByTestId('badges-grid')
    fireEvent.click(screen.getByRole('button', { name: 'Quay lại' }))
    expect(await screen.findByText('home screen')).toBeInTheDocument()
  })
})
