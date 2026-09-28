import { TOUCH_MIN } from '../../styles/dimensions'
import './SpeakerButton.css'

export interface SpeakerButtonProps {
  /** Accessible name — what this button reads aloud, e.g. the instruction text. */
  label: string
  /** True while the clip is playing; shows the pulsing animation (Story 2.9 wires real audio). */
  playing?: boolean
  onClick?: () => void
}

/** A round 🔊 button (`speaker-button` spec). Appears next to every instruction, option,
 * Hint and Solution (EXPERIENCE.md's Audio Behaviour). */
export default function SpeakerButton({ label, playing = false, onClick }: SpeakerButtonProps) {
  return (
    <button
      type="button"
      className={`speaker-button${playing ? ' speaker-button-playing' : ''}`}
      style={{ width: TOUCH_MIN, height: TOUCH_MIN, minWidth: TOUCH_MIN, minHeight: TOUCH_MIN }}
      aria-label={label}
      aria-busy={playing}
      onClick={onClick}
    >
      <span aria-hidden="true">🔊</span>
    </button>
  )
}
