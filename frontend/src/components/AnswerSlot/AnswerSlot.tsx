import { useMotion } from '../../hooks/useMotion'
import { KEY_SIZE } from '../../styles/dimensions'
import './AnswerSlot.css'

export type AnswerSlotState = 'default' | 'active' | 'correct' | 'wrong'

export interface AnswerSlotProps {
  value?: string
  state: AnswerSlotState
  onClick?: () => void
  /** Accessible name, e.g. "Ô số 1". */
  label?: string
}

// EXPERIENCE.md's exact praise/retry lines (State Patterns / Voice and Tone), used here as the
// aria-live announcement so state is never carried by colour alone (UX Accessibility Floor).
const ANNOUNCE: Record<AnswerSlotState, string> = {
  default: '',
  active: '',
  correct: 'Đúng rồi!',
  wrong: 'Chưa đúng, em thử lại nhé!',
}

/** A white answer box (`answer-slot` spec): grey border, blue when active, green + ✔ when
 * correct, orange + shake when wrong (shake skipped under reduced motion, per UX-DR11). */
export default function AnswerSlot({ value, state, onClick, label }: AnswerSlotProps) {
  const { reduced } = useMotion()
  const shouldShake = state === 'wrong' && !reduced
  // The accessible name must expose what the child actually typed, not just the slot's
  // static label — otherwise a screen reader never learns the digit(s) in the box, since
  // aria-label overrides the <span>{value}</span> text content entirely.
  const accessibleName = label ? `${label}: ${value || 'trống'}` : undefined
  return (
    <button
      type="button"
      className={`answer-slot answer-slot-${state}${shouldShake ? ' answer-slot-shake' : ''}`}
      style={{ width: KEY_SIZE, height: KEY_SIZE, minWidth: KEY_SIZE, minHeight: KEY_SIZE }}
      aria-label={accessibleName}
      onClick={onClick}
    >
      <span>{value}</span>
      {state === 'correct' && <span aria-hidden="true">✔</span>}
      {state === 'wrong' && <span aria-hidden="true">↻</span>}
      <span role="status" className="answer-slot-announce">
        {ANNOUNCE[state]}
      </span>
    </button>
  )
}
