import type { DragEvent } from 'react'
import AnswerSlot from '../AnswerSlot/AnswerSlot'
import ChoiceChip from '../ChoiceChip/ChoiceChip'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type OrderView = Extract<ChildPart, { type: 'order' }>

/** `order`: drag a tile into a position slot (native HTML5 drag-and-drop); tap-a-tile-then-
 * a-slot as the REQUIRED tap-alternative (Boundaries & Constraints -- never drag-only).
 * Position slots are keyed `pos0`..`pos{n-1}` (left to right); the submitted `order` is
 * built from those in `ProblemPlayer.buildValue()`. */
export default function OrderWidget({
  part,
  values,
  pickedItem,
  onPickItem,
  onPlaceItem,
  slotState,
  disabled,
}: WidgetProps<OrderView>) {
  const assigned = new Set(Object.values(values))
  const tray = part.items.filter((item) => !assigned.has(item.item_key))

  function handleDrop(slotKey: string, event: DragEvent<HTMLSpanElement>) {
    event.preventDefault()
    if (disabled) return
    const itemKey = event.dataTransfer.getData('text/plain')
    if (itemKey) onPlaceItem(slotKey, itemKey)
  }

  return (
    <div className="widget-order" aria-label={part.prompt || undefined}>
      <div className="widget-order-tray" role="group" aria-label="Các số cần sắp xếp">
        {tray.map((item) => (
          <span
            key={item.item_key}
            draggable={!disabled}
            onDragStart={(event) => event.dataTransfer.setData('text/plain', item.item_key)}
          >
            <ChoiceChip
              selected={pickedItem === item.item_key}
              ariaLabel={item.text}
              onClick={disabled ? undefined : () => onPickItem(item.item_key)}
            >
              {item.text}
            </ChoiceChip>
          </span>
        ))}
      </div>
      <div className="widget-order-slots" role="group" aria-label="Thứ tự đúng">
        {part.items.map((_, i) => {
          const slotKey = `pos${i}`
          const itemKey = values[slotKey]
          const item = itemKey ? part.items.find((it) => it.item_key === itemKey) : undefined
          return (
            <span
              key={slotKey}
              className="widget-order-slot"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => handleDrop(slotKey, event)}
            >
              <AnswerSlot
                label={`Vị trí ${i + 1}`}
                value={item?.text ?? ''}
                state={slotState(slotKey)}
                onClick={disabled ? undefined : () => onPlaceItem(slotKey)}
              />
            </span>
          )
        })}
      </div>
    </div>
  )
}
