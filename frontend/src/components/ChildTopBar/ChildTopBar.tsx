import ProgressDots, { type DotState } from '../ProgressDots/ProgressDots'
import SpeakerButton from '../SpeakerButton/SpeakerButton'
import './ChildTopBar.css'

export interface ChildTopBarProps {
  /** Always required -- every child screen has somewhere to go back to (spec-9-1's frozen
   * Boundaries). The caller decides the target; this component only renders the button. */
  onBack: () => void
  /** One dot per Problem in the current Session chunk (`done`/`current`/`todo`). Only
   * Sessions pass this, and only when there's more than one Problem to show progress
   * through -- an empty/absent array renders no dots at all. */
  dots?: DotState[]
  /** Plays the screen's own title/instruction aloud. Omit where a screen has nothing of its
   * own worth reading (e.g. Library, LessonDetail -- their content already has its own 🔊s). */
  onSpeak?: () => void
}

/**
 * The shared top bar every child screen now uses instead of a bottom-of-page text link
 * (Story 9.1): ⬅ back in the top-left corner, progress dots, and 🔊 -- `EXPERIENCE.md`'s
 * Layout & Spacing section's literal "top bar (back, progress dots, 🔊)" for the Problem
 * screen, now applied to every child screen's top bar, not just the Problem screen's.
 *
 * Deliberately thin and dumb: no routing or data-fetching of its own (spec-9-1's Design
 * Notes) -- every page passes exactly what it needs and nothing more, so this stays
 * trivially reusable and testable in isolation, the same shape as `HomeCard`/`SpeakerButton`.
 */
export default function ChildTopBar({ onBack, dots, onSpeak }: ChildTopBarProps) {
  return (
    <div className="child-top-bar">
      <button type="button" className="child-top-bar-back" aria-label="Quay lại" onClick={onBack}>
        <span aria-hidden="true">⬅</span>
      </button>
      {dots && dots.length > 0 && (
        <div className="child-top-bar-dots">
          <ProgressDots dots={dots} />
        </div>
      )}
      {onSpeak && <SpeakerButton label="Nghe lại" onClick={onSpeak} />}
    </div>
  )
}
