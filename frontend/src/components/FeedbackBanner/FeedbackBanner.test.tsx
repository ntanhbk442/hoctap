import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useMotion } from '../../hooks/useMotion'
import FeedbackBanner from './FeedbackBanner'

vi.mock('../../hooks/useMotion')

const mockMotion = vi.mocked(useMotion)

describe('FeedbackBanner', () => {
  it('shows the correct variant with its message', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(
      <FeedbackBanner variant="correct" visible>
        Đúng rồi! Giỏi quá!
      </FeedbackBanner>,
    )
    const banner = screen.getByRole('status')
    expect(banner).toHaveClass('feedback-banner-correct')
    expect(banner).toHaveTextContent('Đúng rồi! Giỏi quá!')
  })

  it('shows the retry variant with its message', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(
      <FeedbackBanner variant="retry" visible>
        Chưa đúng, thử lại nhé!
      </FeedbackBanner>,
    )
    expect(screen.getByRole('status')).toHaveClass('feedback-banner-retry')
  })

  it('shows the neutral variant with its message (Story 2.8 self-marked "chưa đúng" -- must not look like the retry/wrong-answer penalty)', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(
      <FeedbackBanner variant="neutral" visible>
        Đã thêm vào danh sách ôn lại.
      </FeedbackBanner>,
    )
    const banner = screen.getByRole('status')
    expect(banner).toHaveClass('feedback-banner-neutral')
    expect(banner).not.toHaveClass('feedback-banner-retry')
    expect(banner).toHaveTextContent('Đã thêm vào danh sách ôn lại.')
  })

  it('toggles the visible/hidden transition classes', () => {
    mockMotion.mockReturnValue({ reduced: false })
    const { rerender } = render(
      <FeedbackBanner variant="correct" visible={false}>
        x
      </FeedbackBanner>,
    )
    // Hidden and aria-hidden, so query it via text rather than role (getByRole excludes
    // aria-hidden elements by default, which is exactly the behaviour under test).
    expect(screen.getByText('x')).toHaveClass('feedback-banner-hidden')
    rerender(
      <FeedbackBanner variant="correct" visible>
        x
      </FeedbackBanner>,
    )
    expect(screen.getByRole('status')).toHaveClass('feedback-banner-visible')
  })

  it('is aria-hidden while hidden (not just visually offscreen) and not while visible', () => {
    mockMotion.mockReturnValue({ reduced: false })
    const { rerender } = render(
      <FeedbackBanner variant="correct" visible={false}>
        x
      </FeedbackBanner>,
    )
    expect(screen.getByText('x')).toHaveAttribute('aria-hidden', 'true')
    rerender(
      <FeedbackBanner variant="correct" visible>
        x
      </FeedbackBanner>,
    )
    expect(screen.getByText('x')).toHaveAttribute('aria-hidden', 'false')
  })

  it('shows/hides instantly (no transition class effect) under reduced motion', () => {
    mockMotion.mockReturnValue({ reduced: true })
    render(
      <FeedbackBanner variant="correct" visible>
        x
      </FeedbackBanner>,
    )
    expect(screen.getByRole('status')).toHaveClass('feedback-banner-instant')
  })
})
