import type { ReactNode } from 'react'
import { useMotion } from '../../hooks/useMotion'
import './FeedbackBanner.css'

export interface FeedbackBannerProps {
  /** `neutral` (Story 2.8): a self-marked "chưa đúng" acknowledgement -- deliberately NOT
   * `retry` (that variant's orange border is the graded wrong-Attempt penalty look; a
   * fallback Problem's self-report is never graded, so it must read as neutral, not
   * wrong -- Boundaries & Constraints). */
  variant: 'correct' | 'retry' | 'neutral'
  visible: boolean
  children: ReactNode
}

/** Slides up from the bottom (`feedback-correct` / `feedback-retry` specs). Under reduced
 * motion, shows/hides instantly instead of sliding (UX-DR11). */
export default function FeedbackBanner({ variant, visible, children }: FeedbackBannerProps) {
  const { reduced } = useMotion()
  return (
    <div
      role="status"
      // Hidden means slid fully off-screen and invisible — not just visually empty — so it
      // must not be reachable by assistive tech or by pointer/click while hidden.
      aria-hidden={!visible}
      className={[
        'feedback-banner',
        `feedback-banner-${variant}`,
        visible ? 'feedback-banner-visible' : 'feedback-banner-hidden',
        reduced ? 'feedback-banner-instant' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  )
}
