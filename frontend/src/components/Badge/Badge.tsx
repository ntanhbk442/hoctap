import type { BadgeKey } from '../../api/client'
import { useMotion } from '../../hooks/useMotion'
import SpeakerButton from '../SpeakerButton/SpeakerButton'
import { BADGE_ICON, badgeInstruction, badgeName } from './badgeCopy'
import './Badge.css'

export interface BadgeProps {
  badgeKey: BadgeKey
  earned: boolean
  /** Small variant for Home's latest-3 row; the default is the full 96px medal (the
   * "badge" DESIGN.md spec) used on the Session summary pop and "Huy hiệu của em". */
  small?: boolean
  /** Plays this badge's name (earned) or earn-instruction (unearned) aloud. Omit to
   * render no 🔊 at all (e.g. a purely decorative Home mini-badge). */
  onSpeak?: (text: string) => void
  /** Plays the pop-in animation once, for a badge that was JUST earned (the Session
   * summary's fanfare) -- unless reduced motion is on, matching `StarBurst`'s own
   * `justEarned`/`useMotion()` posture. */
  pop?: boolean
}

/** The 96px round medal (`badge` DESIGN.md spec): a gold ring around its icon and short
 * label when earned; greyed out, with its own 🔊 explaining how to earn it, when not. */
export default function Badge({ badgeKey, earned, small = false, onSpeak, pop = false }: BadgeProps) {
  const { reduced } = useMotion()
  const name = badgeName(badgeKey)
  const instruction = badgeInstruction(badgeKey)
  const spokenText = earned ? name : instruction
  const popping = pop && !reduced
  return (
    <div
      className={`badge${earned ? ' badge-earned' : ' badge-unearned'}${small ? ' badge-small' : ''}${popping ? ' badge-pop' : ''}`}
      data-testid={`badge-${badgeKey}`}
    >
      <div className="badge-medal" role="img" aria-label={earned ? name : `${name} (chưa đạt)`}>
        <span aria-hidden="true">{BADGE_ICON[badgeKey]}</span>
      </div>
      <span className="badge-label">{name}</span>
      {onSpeak && (
        <SpeakerButton label={`Nghe: ${spokenText}`} onClick={() => onSpeak(spokenText)} />
      )}
    </div>
  )
}
