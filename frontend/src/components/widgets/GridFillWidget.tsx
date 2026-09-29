import AnswerSlot from '../AnswerSlot/AnswerSlot'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type GridFillView = Extract<ChildPart, { type: 'grid_fill' }>

/** `grid_fill`: same tap-a-cell-then-`NumberPad` interaction shape as `number_input`, just
 * laid out as a `rows` x `cols` grid. A cell already printed in the book (`given != null`)
 * is locked -- shown greyed, not tappable (Boundaries & Constraints). Cell keys are
 * `r{i}c{j}` (0-based), matching `content/schema.py`'s `GridFillView.slot_keys()` exactly. */
export default function GridFillWidget({
  part,
  values,
  onSlotTap,
  slotState,
  disabled,
}: WidgetProps<GridFillView>) {
  return (
    <div
      className="widget-grid-fill"
      style={{ gridTemplateColumns: `repeat(${part.cols}, auto)` }}
      aria-label={part.prompt || undefined}
    >
      {part.cells.map((row, i) =>
        row.map((cell, j) => {
          const key = `r${i}c${j}`
          if (cell.given != null) {
            return (
              <span key={key} className="widget-grid-fill-given" aria-label={`Ô ${key}: ${cell.given}`}>
                {cell.given}
              </span>
            )
          }
          return (
            <AnswerSlot
              key={key}
              label={`Ô ${key}`}
              value={values[key] ?? ''}
              state={slotState(key)}
              onClick={disabled ? undefined : () => onSlotTap(key)}
            />
          )
        }),
      )}
    </div>
  )
}
