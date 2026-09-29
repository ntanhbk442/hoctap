import type { ReactNode } from 'react'
import AnswerSlot from '../AnswerSlot/AnswerSlot'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type NumberInputView = Extract<ChildPart, { type: 'number_input' }>

// Matches `backend/hoctap/content/schema.py`'s own `SLOT_MARKER` exactly (any non-`[`/`]`
// content between double brackets), not a narrower alphanumeric guess.
const SLOT_MARKER = /\[\[([^[\]]*)\]\]/g

/** `number_input`: the Part's `template` text with `[[slot_key]]` markers swapped for a
 * tappable `AnswerSlot` (UX-DR9: "tap a slot, then type on the number pad"). */
export default function NumberInputWidget({
  part,
  values,
  onSlotTap,
  slotState,
  disabled,
}: WidgetProps<NumberInputView>) {
  const pieces: ReactNode[] = []
  let lastIndex = 0
  // `String.matchAll()` (not `exec()` + a shared `lastIndex`) -- mutating a module-level
  // regex's `lastIndex` across renders/instances is exactly the kind of external mutable
  // state this repo's lint rule (`react-hooks/immutability`) flags; `matchAll()` needs no
  // such state, even with a `g`-flagged pattern.
  for (const match of part.template.matchAll(SLOT_MARKER)) {
    const [full, slotKey] = match
    if (match.index > lastIndex) {
      pieces.push(part.template.slice(lastIndex, match.index))
    }
    const slot = part.slots.find((s) => s.slot_key === slotKey)
    if (slot) {
      pieces.push(
        <AnswerSlot
          key={slotKey}
          label={`Ô ${slotKey}`}
          value={values[slotKey] ?? ''}
          state={slotState(slotKey)}
          onClick={disabled ? undefined : () => onSlotTap(slotKey)}
        />,
      )
    }
    lastIndex = match.index + full.length
  }
  if (lastIndex < part.template.length) {
    pieces.push(part.template.slice(lastIndex))
  }

  return (
    <div className="widget-number-input" aria-label={part.prompt || undefined}>
      {pieces.map((piece, i) =>
        typeof piece === 'string' ? <span key={`t${i}`}>{piece}</span> : piece,
      )}
    </div>
  )
}
