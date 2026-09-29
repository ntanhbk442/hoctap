import { useLayoutEffect, useRef, useState } from 'react'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type MatchView = Extract<ChildPart, { type: 'match' }>

interface Line {
  leftKey: string
  rightKey: string
  x1: number
  y1: number
  x2: number
  y2: number
}

/** `match`: tap a left item, then a right item, draws a line between them (a small new
 * piece, since none of Story 2.1's components draw a line between two tapped items).
 * Tapping EITHER endpoint of an already-drawn pair "taps the line" and un-pairs it -- there
 * is no separate line hit-target, an implementer's-call equivalence for the tap surface
 * (documented in this story's Implementation Notes). */
export default function MatchWidget({
  part,
  pairs,
  pickedItem,
  onPickItem,
  onPairRight,
  onRemovePair,
  slotState,
  disabled,
}: WidgetProps<MatchView>) {
  const containerRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef(new Map<string, HTMLElement>())
  const [lines, setLines] = useState<Line[]>([])

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const next: Line[] = []
    for (const [leftKey, rightKey] of Object.entries(pairs)) {
      const leftEl = itemRefs.current.get(`left:${leftKey}`)
      const rightEl = itemRefs.current.get(`right:${rightKey}`)
      if (!leftEl || !rightEl) continue
      const l = leftEl.getBoundingClientRect()
      const r = rightEl.getBoundingClientRect()
      next.push({
        leftKey,
        rightKey,
        x1: l.right - rect.left,
        y1: l.top + l.height / 2 - rect.top,
        x2: r.left - rect.left,
        y2: r.top + r.height / 2 - rect.top,
      })
    }
    setLines(next)
  }, [pairs])

  const graded = slotState('__all__')
  const variant = graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined
  const pairedRight = new Set(Object.values(pairs))

  function itemRef(key: string) {
    return (el: HTMLElement | null) => {
      if (el) itemRefs.current.set(key, el)
      else itemRefs.current.delete(key)
    }
  }

  return (
    <div
      className={`widget-match${variant ? ` widget-match-${variant}` : ''}`}
      ref={containerRef}
      aria-label={part.prompt || undefined}
    >
      <svg className="widget-match-lines" aria-hidden="true">
        {lines.map((line) => (
          <line
            key={`${line.leftKey}-${line.rightKey}`}
            x1={line.x1}
            y1={line.y1}
            x2={line.x2}
            y2={line.y2}
            className="widget-match-line"
          />
        ))}
      </svg>
      <div className="widget-match-col" role="group" aria-label="Bên trái">
        {part.left.map((item) => {
          const paired = Boolean(pairs[item.item_key])
          return (
            <button
              key={item.item_key}
              type="button"
              ref={itemRef(`left:${item.item_key}`)}
              className={`widget-match-item${pickedItem === item.item_key ? ' widget-match-item-picked' : ''}${paired ? ' widget-match-item-paired' : ''}`}
              aria-pressed={pickedItem === item.item_key || paired}
              disabled={disabled}
              onClick={() => (paired ? onRemovePair(item.item_key) : onPickItem(item.item_key))}
            >
              {item.text ?? (item.image_key && <span aria-hidden="true">{item.item_key}</span>)}
            </button>
          )
        })}
      </div>
      <div className="widget-match-col" role="group" aria-label="Bên phải">
        {part.right.map((item) => {
          const paired = pairedRight.has(item.item_key)
          return (
            <button
              key={item.item_key}
              type="button"
              ref={itemRef(`right:${item.item_key}`)}
              className={`widget-match-item${paired ? ' widget-match-item-paired' : ''}`}
              aria-pressed={paired}
              disabled={disabled}
              onClick={() => {
                if (paired) {
                  const leftKey = Object.entries(pairs).find(([, r]) => r === item.item_key)?.[0]
                  if (leftKey) onRemovePair(leftKey)
                } else {
                  onPairRight(item.item_key)
                }
              }}
            >
              {item.text ?? (item.image_key && <span aria-hidden="true">{item.item_key}</span>)}
            </button>
          )
        })}
      </div>
    </div>
  )
}
