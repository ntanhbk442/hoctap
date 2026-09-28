import type { ReactNode } from 'react'
import { CHOICE_CHIP_MIN_HEIGHT, TOUCH_MIN } from '../../styles/dimensions'
import './ChoiceChip.css'

export interface ChoiceChipProps {
  selected?: boolean
  onClick?: () => void
  /** Accessible name; required when `children` is an image without its own alt text. */
  ariaLabel?: string
  children: ReactNode
}

/** A tappable option for `compare` (`<` `=` `>`), `multiple_choice` and `image_select`
 * (`choice-chip` spec). Turns `primary-soft` when selected. */
export default function ChoiceChip({ selected = false, onClick, ariaLabel, children }: ChoiceChipProps) {
  return (
    <button
      type="button"
      className={`choice-chip${selected ? ' choice-chip-selected' : ''}`}
      style={{ minWidth: TOUCH_MIN, minHeight: CHOICE_CHIP_MIN_HEIGHT }}
      aria-pressed={selected}
      aria-label={ariaLabel}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
