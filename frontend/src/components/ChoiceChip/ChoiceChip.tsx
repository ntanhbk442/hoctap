import type { ReactNode } from 'react'
import { useMotion } from '../../hooks/useMotion'
import { CHOICE_CHIP_MIN_HEIGHT, TOUCH_MIN } from '../../styles/dimensions'
import './ChoiceChip.css'

export interface ChoiceChipProps {
  selected?: boolean
  /** Graded state (Story 2.6): green on a correct verdict, orange+shake on wrong -- same
   * palette as `AnswerSlot`'s `correct`/`wrong` states, added here rather than reimplementing
   * `AnswerSlot`'s own internals (this story's Boundaries & Constraints). `undefined` (the
   * default) means "not graded yet", matching every existing call site unchanged. */
  variant?: 'correct' | 'wrong'
  onClick?: () => void
  /** Accessible name; required when `children` is an image without its own alt text. */
  ariaLabel?: string
  children: ReactNode
}

/** A tappable option for `compare` (`<` `=` `>`), `multiple_choice` and `image_select`
 * (`choice-chip` spec). Turns `primary-soft` when selected. */
export default function ChoiceChip({
  selected = false,
  variant,
  onClick,
  ariaLabel,
  children,
}: ChoiceChipProps) {
  const { reduced } = useMotion()
  const shouldShake = variant === 'wrong' && !reduced
  return (
    <button
      type="button"
      className={[
        'choice-chip',
        selected ? 'choice-chip-selected' : '',
        variant ? `choice-chip-${variant}` : '',
        shouldShake ? 'choice-chip-shake' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ minWidth: TOUCH_MIN, minHeight: CHOICE_CHIP_MIN_HEIGHT }}
      aria-pressed={selected}
      aria-label={ariaLabel}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
