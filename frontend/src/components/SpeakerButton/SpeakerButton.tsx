import { TOUCH_MIN } from '../../styles/dimensions'
import './SpeakerButton.css'

export interface SpeakerButtonProps {
  /** Accessible name — what this button reads aloud, e.g. the instruction text. */
  label: string
  /** True while the clip is playing; shows the pulsing animation. Story 2.9: the caller
   * derives this from `audio/player.ts`'s shared player state for this button's own key. */
  playing?: boolean
  /** Story 2.9: true once the shared player's `error` event has confirmed this button's clip
   * is missing (never synthesised, or genuinely absent). Greys the button out (visually
   * disabled, `aria-disabled`, no `onClick`) -- the instruction/option/hint TEXT next to it
   * (rendered by the caller, not this component) always stays fully visible regardless. */
  missing?: boolean
  onClick?: () => void
}

/** A round 🔊 button (`speaker-button` spec). Appears next to every instruction, option,
 * Hint and Solution (EXPERIENCE.md's Audio Behaviour). */
export default function SpeakerButton({
  label,
  playing = false,
  missing = false,
  onClick,
}: SpeakerButtonProps) {
  return (
    <button
      type="button"
      className={`speaker-button${playing ? ' speaker-button-playing' : ''}${missing ? ' speaker-button-missing' : ''}`}
      style={{ width: TOUCH_MIN, height: TOUCH_MIN, minWidth: TOUCH_MIN, minHeight: TOUCH_MIN }}
      aria-label={label}
      aria-busy={playing}
      aria-disabled={missing}
      disabled={missing}
      onClick={missing ? undefined : onClick}
    >
      <span aria-hidden="true">🔊</span>
    </button>
  )
}
