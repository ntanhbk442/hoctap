import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import './ZoomableImage.css'

const MIN_SCALE = 1
const MAX_SCALE = 4

/** Two active pointers, keyed by `pointerId`. */
type PointerMap = Map<number, { x: number; y: number }>

export interface ZoomableImageProps {
  src: string
  alt: string
}

/** A pinch-zoomable, pannable crop viewer (Story 2.8: the fallback Problem's printed page
 * crop, "pinch-zoomable" per Boundaries & Constraints). No existing crop-viewing primitive
 * covers this (Story 2.1-2.7's widgets only ever show a crop at native size -- see e.g.
 * `SpotDifferenceWidget`'s plain `<img>`), so this is a new, from-scratch, dependency-free
 * component: two-pointer pinch computes a scale delta from the change in inter-pointer
 * distance, one-pointer drag pans (only once zoomed in, so a single-finger scroll of the
 * page still works at scale 1), and a double-tap/double-click resets to scale 1. Bounded to
 * `[MIN_SCALE, MAX_SCALE]` so the image can never shrink below native size or zoom absurdly
 * far in on a small crop. */
export default function ZoomableImage({ src, alt }: ZoomableImageProps) {
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const pointers = useRef<PointerMap>(new Map())
  const lastDistance = useRef<number | null>(null)
  const lastPan = useRef<{ x: number; y: number } | null>(null)
  const lastTapAt = useRef(0)

  function distance(map: PointerMap): number {
    const [a, b] = [...map.values()]
    return Math.hypot(a.x - b.x, a.y - b.y)
  }

  function clampScale(next: number): number {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, next))
  }

  function reset() {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId)
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointers.current.size === 2) {
      // Always re-baseline on reaching exactly 2 pointers -- including a 3rd+ pointer
      // joining an existing pinch then leaving back down to 2 (Review Triage Log #3):
      // without this, `lastDistance` would stay stale from before the 3rd pointer
      // joined, and the next 2-pointer move would compute its delta against a
      // long-outdated distance, causing a sudden unintended zoom jump.
      lastDistance.current = distance(pointers.current)
      lastPan.current = null
    } else if (pointers.current.size === 1) {
      lastPan.current = { x: event.clientX, y: event.clientY }
      const now = Date.now()
      if (now - lastTapAt.current < 300) {
        reset()
      }
      lastTapAt.current = now
    }
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!pointers.current.has(event.pointerId)) return
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointers.current.size === 2 && lastDistance.current != null) {
      const nextDistance = distance(pointers.current)
      const delta = nextDistance / lastDistance.current
      lastDistance.current = nextDistance
      setScale((prev) => clampScale(prev * delta))
    } else if (pointers.current.size === 1 && scale > 1 && lastPan.current) {
      const dx = event.clientX - lastPan.current.x
      const dy = event.clientY - lastPan.current.y
      lastPan.current = { x: event.clientX, y: event.clientY }
      setOffset((prev) => ({ x: prev.x + dx, y: prev.y + dy }))
    }
  }

  function endPointer(event: ReactPointerEvent<HTMLDivElement>) {
    pointers.current.delete(event.pointerId)
    if (pointers.current.size === 2) {
      // A 3rd+ pointer that joined mid-pinch just left, back down to 2 (Review Triage
      // Log #3) -- re-baseline against the two pointers that remain, rather than
      // leaving a stale pre-3rd-pointer distance (or `null`, which would silently stop
      // pinch-zoom from working again until the next pointer-down).
      lastDistance.current = distance(pointers.current)
    } else if (pointers.current.size < 2) {
      lastDistance.current = null
    }
    if (pointers.current.size === 0) lastPan.current = null
  }

  return (
    <div
      className="zoomable-image"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endPointer}
      onPointerCancel={endPointer}
      onPointerLeave={endPointer}
    >
      <img
        src={src}
        alt={alt}
        className="zoomable-image-img"
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
        draggable={false}
      />
      {scale > 1 && (
        <button type="button" className="zoomable-image-reset" onClick={reset}>
          ↺
        </button>
      )}
    </div>
  )
}
