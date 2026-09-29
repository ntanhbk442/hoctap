import { useState } from 'react'
import type { MouseEvent } from 'react'
import AnswerSlot from '../AnswerSlot/AnswerSlot'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type CountImageView = Extract<ChildPart, { type: 'count_image' }>

interface Dot {
  x: number
  y: number
}

/** `count_image`: the Part's image plus the `NumberPad` (rendered by `ProblemPlayer`'s
 * action bar); tapping the image places a small dot -- a counting aid only, NEVER graded,
 * never sent to the server, purely local UI state reset per attempt (Boundaries &
 * Constraints). */
export default function CountImageWidget({
  part,
  values,
  onSlotTap,
  slotState,
  disabled,
  imageUrl,
}: WidgetProps<CountImageView>) {
  const [dots, setDots] = useState<Dot[]>([])
  const url = imageUrl(part.image_key)

  function placeDot(event: MouseEvent<HTMLDivElement>) {
    if (disabled) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width
    const y = (event.clientY - rect.top) / rect.height
    setDots((prev) => [...prev, { x, y }])
  }

  return (
    <div className="widget-count-image">
      <div
        className="widget-count-image-canvas"
        role="button"
        tabIndex={0}
        aria-label="Đếm hình (chạm để đánh dấu, không tính điểm)"
        onClick={placeDot}
      >
        {url && <img src={url} alt="" />}
        {dots.map((dot, i) => (
          <span
            key={i}
            className="widget-count-image-dot"
            style={{ left: `${dot.x * 100}%`, top: `${dot.y * 100}%` }}
            aria-hidden="true"
          />
        ))}
      </div>
      <div className="widget-count-image-slots">
        {part.slots.map((slot) => (
          <div key={slot.slot_key} className="widget-count-image-slot">
            <span className="widget-count-image-label">{slot.label}</span>
            <AnswerSlot
              label={`Ô ${slot.slot_key}`}
              value={values[slot.slot_key] ?? ''}
              state={slotState(slot.slot_key)}
              onClick={disabled ? undefined : () => onSlotTap(slot.slot_key)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
