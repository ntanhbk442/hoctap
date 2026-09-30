import { useState } from 'react'
import type { MouseEvent } from 'react'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type DotDrawView = Extract<ChildPart, { type: 'dot_draw' }>

interface PlacedDot {
  x: number
  y: number
}

// De-duplicates a tap that lands near an already-placed dot into a remove instead of a new,
// overlapping dot -- same proximity-bucket quantization `SpotDifferenceWidget` uses (see that
// file's `regionKeyFor`), applied here client-side-only since `dot_draw`'s dots are local
// render state, not the lifted/graded value (only the resulting count is).
const BUCKET_PCT = 12

function bucketKey(x: number, y: number): string {
  const bx = Math.floor((x * 100) / BUCKET_PCT)
  const by = Math.floor((y * 100) / BUCKET_PCT)
  return `${bx}_${by}`
}

/** `dot_draw`: tap inside the box to add a dot; tap an existing dot to remove it; a visible
 * counter shows how many are placed, counted against the box's own `given` (already-printed)
 * count. Unlike `count_image`'s dots (a non-graded counting AID), a `dot_draw` box's dot
 * COUNT is the actual answer -- `given + placed.length` is pushed into `values[slot_key]`
 * (via the new `onSetValue`) on every add/remove, so it survives a retry exactly like every
 * other keyed type's `values` (no `attemptSeq` remount here, deliberately unlike
 * `CountImageWidget`). */
export default function DotDrawWidget({
  part,
  onSetValue,
  slotState,
  disabled,
}: WidgetProps<DotDrawView>) {
  const [dotsByBox, setDotsByBox] = useState<Record<string, PlacedDot[]>>({})

  function addDot(boxKey: string, given: number, event: MouseEvent<HTMLDivElement>) {
    if (disabled) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width
    const y = (event.clientY - rect.top) / rect.height
    // The parent's `onSetValue` is a side effect: never call it inside a state updater
    // (StrictMode double-invokes updaters).
    const existing = dotsByBox[boxKey] ?? []
    const tapKey = bucketKey(x, y)
    const matchIndex = existing.findIndex((dot) => bucketKey(dot.x, dot.y) === tapKey)
    const dots = matchIndex === -1 ? [...existing, { x, y }] : existing.filter((_, i) => i !== matchIndex)
    setDotsByBox((prev) => ({ ...prev, [boxKey]: dots }))
    onSetValue(boxKey, String(given + dots.length))
  }

  function removeDot(boxKey: string, given: number, index: number, event: MouseEvent) {
    event.stopPropagation()
    if (disabled) return
    const dots = (dotsByBox[boxKey] ?? []).filter((_, i) => i !== index)
    setDotsByBox((prev) => ({ ...prev, [boxKey]: dots }))
    onSetValue(boxKey, String(given + dots.length))
  }

  return (
    <div className="widget-dot-draw" aria-label={part.prompt || undefined}>
      {part.boxes.map((box) => {
        const dots = dotsByBox[box.slot_key] ?? []
        const count = box.given + dots.length
        const graded = slotState(box.slot_key)
        return (
          <div key={box.slot_key} className="widget-dot-draw-box-wrap">
            <div
              className={`widget-dot-draw-box widget-dot-draw-box-${graded}`}
              role="button"
              tabIndex={0}
              aria-label={`${box.label}: chạm để thêm điểm, đã có ${count} điểm`}
              onClick={(event) => addDot(box.slot_key, box.given, event)}
            >
              {Array.from({ length: box.given }).map((_, i) => (
                <span key={`given-${i}`} className="widget-dot-draw-dot widget-dot-draw-dot-given" aria-hidden="true" />
              ))}
              {dots.map((dot, i) => (
                <span
                  key={i}
                  className="widget-dot-draw-dot widget-dot-draw-dot-added"
                  style={{ left: `${dot.x * 100}%`, top: `${dot.y * 100}%` }}
                  onClick={(event) => removeDot(box.slot_key, box.given, i, event)}
                  aria-hidden="true"
                />
              ))}
            </div>
            <span className="widget-dot-draw-label">{box.label}</span>
            <span className="widget-dot-draw-counter" role="status">
              {count}
            </span>
          </div>
        )
      })}
    </div>
  )
}
