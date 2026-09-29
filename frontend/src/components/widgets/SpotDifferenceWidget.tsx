import { useState } from 'react'
import type { MouseEvent } from 'react'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type SpotDifferenceView = Extract<ChildPart, { type: 'spot_difference' }>

// De-duplicates nearby taps into one "spot" (percent-of-image-sized grid cell). See this
// story's Spec Change Log: `SpotDifferenceView` (the child-facing bundle shape) carries no
// region/bbox data at all -- only `image_left`/`image_right`/`count` -- so, unlike
// `image_select`'s regions, there is no server-given hotspot to hit-test against on the
// client. This widget derives its OWN region key from the tapped point instead; it can
// never match the real `answer.regions` keys `learning/graders.py` compares against
// server-side (those are never sent to the child, by design -- that data doesn't exist on
// this Part type's child View). The full tap/ring/counter/✔-gating UX below is implemented
// per spec regardless; see the Spec Change Log for the follow-up this gap needs.
const BUCKET_PCT = 12
const FLASH_MS = 300

export default function SpotDifferenceWidget({
  part,
  foundRegions,
  onFoundRegion,
  slotState,
  disabled,
  imageUrl,
}: WidgetProps<SpotDifferenceView>) {
  const [flash, setFlash] = useState<{ x: number; y: number } | null>(null)
  const leftUrl = imageUrl(part.image_left)
  const rightUrl = imageUrl(part.image_right)
  const graded = slotState('__all__')
  const variant = graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined

  function regionKeyFor(x: number, y: number): string {
    const bx = Math.floor((x * 100) / BUCKET_PCT)
    const by = Math.floor((y * 100) / BUCKET_PCT)
    return `d_${bx}_${by}`
  }

  function handleTap(event: MouseEvent<HTMLDivElement>) {
    if (disabled || foundRegions.length >= part.count) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width
    const y = (event.clientY - rect.top) / rect.height
    const added = onFoundRegion(regionKeyFor(x, y))
    if (!added) {
      setFlash({ x, y })
      window.setTimeout(() => setFlash(null), FLASH_MS)
    }
  }

  return (
    <div
      className={`widget-spot-difference${variant ? ` widget-spot-difference-${variant}` : ''}`}
      aria-label={part.prompt || undefined}
    >
      <div className="widget-spot-difference-images">
        <div className="widget-spot-difference-image-wrap">{leftUrl && <img src={leftUrl} alt="" />}</div>
        <div
          className="widget-spot-difference-image-wrap"
          role="button"
          tabIndex={0}
          aria-label="Tìm điểm khác nhau"
          onClick={handleTap}
        >
          {rightUrl && <img src={rightUrl} alt="" />}
          {foundRegions.map((key) => {
            const [, bx, by] = key.split('_')
            const left = (Number(bx) + 0.5) * BUCKET_PCT
            const top = (Number(by) + 0.5) * BUCKET_PCT
            return (
              <span
                key={key}
                className="widget-spot-difference-ring"
                style={{ left: `${left}%`, top: `${top}%` }}
                aria-hidden="true"
              />
            )
          })}
          {flash && (
            <span
              className="widget-spot-difference-flash"
              style={{ left: `${flash.x * 100}%`, top: `${flash.y * 100}%` }}
              aria-hidden="true"
            />
          )}
        </div>
      </div>
      <p className="widget-spot-difference-counter">
        {foundRegions.length}/{part.count}
      </p>
    </div>
  )
}
