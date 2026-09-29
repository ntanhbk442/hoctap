import type { BadgeKey } from '../../api/client'
import { phrase, type PhraseKey } from '../../audio/phrases'

// Split out of `Badge.tsx` itself so that file only exports the component (react-refresh
// requires this) -- shared by `Badge` and `SessionSummaryScreen` (`SessionPlayer.tsx`),
// which must speak the exact same badge name text the medal itself shows.
export const BADGE_ICON: Record<BadgeKey, string> = {
  week1: '🏁',
  streak7: '🔥',
  stars100: '🌟',
}

const BADGE_NAME_KEY: Record<BadgeKey, PhraseKey> = {
  week1: 'badge_week1_name',
  streak7: 'badge_streak7_name',
  stars100: 'badge_stars100_name',
}

const BADGE_INSTRUCTION_KEY: Record<BadgeKey, PhraseKey> = {
  week1: 'badge_week1_instruction',
  streak7: 'badge_streak7_instruction',
  stars100: 'badge_stars100_instruction',
}

/** This badge's Vietnamese name (`phrases.vi.json`). */
export function badgeName(badgeKey: BadgeKey): string {
  return phrase(BADGE_NAME_KEY[badgeKey])
}

/** This badge's Vietnamese earn-instruction (`phrases.vi.json`) -- what an unearned
 * badge's own 🔊 explains. */
export function badgeInstruction(badgeKey: BadgeKey): string {
  return phrase(BADGE_INSTRUCTION_KEY[badgeKey])
}
