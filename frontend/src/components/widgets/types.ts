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

  // --- Story 2.7 additions (order/grid_fill/match/image_select/dot_draw/connect_dots/
  // spot_difference) -- unused by the basic-5 widgets, following the same "every widget
  // gets the full shared prop set, reads only what it needs" convention as `onSetCompare`
  // etc. above.

  /** `match`: left_key -> right_key pairs already drawn. */
  pairs: Record<string, string>
  /** The item/tile currently "picked up" -- `order`'s tap-alternative to a drag, and
   * `match`'s "tap a left item" step -- or `null`. Reuses the same lifted-state shape as
   * `activeSlot` (a single pending key), kept separate since `order`/`match` never touch
   * the `NumberPad`. */
  pickedItem: string | null
  /** `order`/`match`: pick up (or, tapped again, put back down) an item/tile. */
  onPickItem: (itemKey: string) => void
  /** `order`: place the picked item (tap-alternative) -- or an explicitly given `itemKey`
   * (a native drag-and-drop drop) -- into a position slot. Tapping a FILLED slot with
   * nothing picked instead picks that slot's item back up. */
  onPlaceItem: (slotKey: string, itemKey?: string) => void
  /** `match`: pair the currently picked left item with this right item. No-op if nothing
   * is picked. */
  onPairRight: (rightKey: string) => void
  /** `match`: un-pair (tapping either endpoint of an existing pair counts as "tapping the
   * line" -- there is no separate line hit-target). */
  onRemovePair: (leftKey: string) => void
  /** `dot_draw`: directly set a keyed value (the box's resulting dot count as a string) --
   * this type drives `values` from taps, not the shared `NumberPad`. */
  onSetValue: (key: string, value: string) => void
  /** `connect_dots`: the dot numbers tapped so far, in order. */
  sequence: number[]
  /** `connect_dots`: tap dot `n`. Returns `true` if it was the correct next dot (accepted,
   * appended to `sequence`) or `false` if out of sequence (rejected, no state change --
   * the widget itself renders the "wiggle" purely locally). */
  onTapDot: (n: number) => boolean
  /** `spot_difference`: region keys already found. */
  foundRegions: string[]
  /** `spot_difference`: report a tapped spot's (client-derived) region key. Returns `true`
   * if it was a NEW spot (accepted) or `false` if already found (the widget renders a
   * transient flash locally, no permanent ring, no state change). */
  onFoundRegion: (key: string) => boolean
}
