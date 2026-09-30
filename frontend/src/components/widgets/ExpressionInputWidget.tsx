import type { ReactNode } from 'react'
import AnswerSlot from '../AnswerSlot/AnswerSlot'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type ExpressionInputView = Extract<ChildPart, { type: 'expression_input' }>

// Matches `backend/hoctap/content/schema.py`'s `SLOT_MARKER`.
const SLOT_MARKER = /\[\[([^[\]]*)\]\]/g

/** `expression_input`: the Part's `template` with `[[slot_key]]` markers swapped for tappable
 * `AnswerSlot`s; the child types an expression (digits, + − × : ( ) , /) on the expression
 * pad in `ProblemPlayer`'s bottom bar. Same shape as `NumberInputWidget`. */
export default function ExpressionInputWidget({
  part,
  values,
  onSlotTap,
  slotState,
  disabled,
}: WidgetProps<ExpressionInputView>) {
  const pieces: ReactNode[] = []
  let lastIndex = 0
  for (const match of part.template.matchAll(SLOT_MARKER)) {
    const [full, slotKey] = match
    if (match.index > lastIndex) pieces.push(part.template.slice(lastIndex, match.index))
    if (part.slots.some((s) => s.slot_key === slotKey)) {
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
  if (lastIndex < part.template.length) pieces.push(part.template.slice(lastIndex))

  return (
    <div className="widget-number-input widget-expression-input" aria-label={part.prompt || undefined}>
      {pieces.map((piece, i) =>
        typeof piece === 'string' ? <span key={`t${i}`}>{piece}</span> : piece,
      )}
    </div>
  )
}
