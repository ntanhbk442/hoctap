import { useEffect, useRef, useState } from 'react'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type ConnectDotsView = Extract<ChildPart, { type: 'connect_dots' }>

const WIGGLE_MS = 400

/** `connect_dots`: tap numbered dots in order; a line follows the taps. Tapping the WRONG
 * next dot makes it wiggle and does NOT count as an Attempt -- `onTapDot()` rejects it
 * (returns `false`, no state change in `ProblemPlayer`) and this widget renders the wiggle
 * purely locally, exactly as the Boundaries & Constraints require. Only tapping ✔ once the
 * full sequence is drawn submits an Attempt (`ProblemPlayer`'s existing ✔-gated submit flow
 * -- unchanged for this type, see this story's Implementation Notes). */
export default function ConnectDotsWidget({
  part,
  sequence,
  onTapDot,
  slotState,
  disabled,
  imageUrl,
}: WidgetProps<ConnectDotsView>) {
  const [wiggling, setWiggling] = useState<number | null>(null)
  const wiggleTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(wiggleTimer.current), [])
  const url = imageUrl(part.image_key)
  const graded = slotState('__all__')
  const variant = graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined

  function handleTap(n: number) {
    if (disabled) return
    const accepted = onTapDot(n)
    if (!accepted) {
      setWiggling(n)
      window.clearTimeout(wiggleTimer.current)
      wiggleTimer.current = window.setTimeout(() => setWiggling((current) => (current === n ? null : current)), WIGGLE_MS)
    }
  }

  const points = sequence
    .map((n) => part.dots.find((d) => d.n === n))
    .filter((d): d is NonNullable<typeof d> => d != null)
    .map((d) => `${d.x * 100},${d.y * 100}`)
    .join(' ')

  return (
    <div
      className={`widget-connect-dots${variant ? ` widget-connect-dots-${variant}` : ''}`}
      aria-label={part.prompt || undefined}
    >
      <div className="widget-connect-dots-canvas">
        {url && <img src={url} alt="" />}
        <svg className="widget-connect-dots-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {points && <polyline points={points} />}
        </svg>
        {part.dots.map((dot) => {
          const done = sequence.includes(dot.n)
          return (
            <button
              key={dot.n}
              type="button"
              className={`widget-connect-dots-dot${done ? ' widget-connect-dots-dot-done' : ''}${wiggling === dot.n ? ' widget-connect-dots-dot-wiggle' : ''}`}
              style={{ left: `${dot.x * 100}%`, top: `${dot.y * 100}%` }}
              aria-label={`Chấm số ${dot.n}`}
              disabled={disabled}
              onClick={() => handleTap(dot.n)}
            >
              {dot.n}
            </button>
          )
        })}
      </div>
      <p className="widget-connect-dots-counter">
        {sequence.length}/{part.dots.length}
      </p>
    </div>
  )
}
