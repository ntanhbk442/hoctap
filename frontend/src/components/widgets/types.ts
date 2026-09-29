import type { AnswerSlotState } from '../AnswerSlot/AnswerSlot'
import type { ChildProblemView } from '../../api/client'

export type ChildPart = ChildProblemView['parts'][number]

/**
 * Shared props for every Part-type widget (Story 2.6's widget-per-type switcher). Each
 * widget is a controlled, presentation-only composition of Story 2.1's components -- ALL
 * answer state lives in `ProblemPlayer`, so a widget never calls the grading API or knows
 * about the network request in flight; it only reads `disabled` for that.
 */
export interface WidgetProps<P extends ChildPart> {
  part: P
  /** Keyed slot values (`number_input`/`number_tree`/`compare`/`count_image`). */
  values: Record<string, string>
  /** Selected option keys (`multiple_choice`). */
  selected: string[]
  /** The slot currently receiving `NumberPad` digits, if any -- the `NumberPad` itself is
   * rendered once, in `ProblemPlayer`'s bottom action bar (UX-DR12), not by each widget. */
  activeSlot: string | null
  onSlotTap: (key: string) => void
  onToggleOption: (key: string) => void
  onSetCompare: (key: string, value: '<' | '=' | '>') => void
  /** This key's graded visual state, once an attempt has been submitted; `default`/`active`
   * otherwise (see `ProblemPlayer`'s `slotState()`). */
  slotState: (key: string) => AnswerSlotState
  /** True while a submitted attempt is in flight, or while feedback for the last one is
   * still settling -- every input is inert then (no double-submit, Boundaries & Constraints). */
  disabled: boolean
  /** Resolves a Part's `image_key` to its served crop URL (`ProblemPlayer`'s mapping of the
   * bundle's `crop_urls` against `problem.images`), or `undefined` if not found. */
  imageUrl: (imageKey: string) => string | undefined
}
