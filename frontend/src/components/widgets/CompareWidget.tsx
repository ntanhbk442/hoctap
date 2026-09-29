import ChoiceChip from '../ChoiceChip/ChoiceChip'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type CompareView = Extract<ChildPart, { type: 'compare' }>

const SYMBOLS = ['<', '=', '>'] as const

/** `compare`: three `ChoiceChip`s (`<` `=` `>`) per row; tapping one fills that row's slot
 * (UX-DR9). */
export default function CompareWidget({
  part,
  values,
  onSetCompare,
  slotState,
  disabled,
}: WidgetProps<CompareView>) {
  return (
    <div className="widget-compare">
      {part.rows.map((row) => {
        const graded = slotState(row.slot_key)
        const variant =
          graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined
        return (
          <div key={row.slot_key} className="widget-compare-row">
            <span className="widget-compare-side">{row.left}</span>
            <div className="widget-compare-chips" role="group" aria-label={`So sánh ${row.slot_key}`}>
              {SYMBOLS.map((symbol) => (
                <ChoiceChip
                  key={symbol}
                  selected={values[row.slot_key] === symbol}
                  variant={values[row.slot_key] === symbol ? variant : undefined}
                  onClick={disabled ? undefined : () => onSetCompare(row.slot_key, symbol)}
                >
                  {symbol}
                </ChoiceChip>
              ))}
            </div>
            <span className="widget-compare-side">{row.right}</span>
          </div>
        )
      })}
    </div>
  )
}
