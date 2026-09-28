import { useRef, type ReactNode } from 'react'
import './HomeCard.css'

export interface HomeCardProps {
  title: string
  icon?: ReactNode
  /** Double-width variant with a `primary-pressed` bottom edge, for "Bài hôm nay". */
  wide?: boolean
  onClick?: () => void
  /** Plays the card's 🔊 label without opening it (EXPERIENCE.md's Home card rule). */
  onLongPress?: () => void
  children?: ReactNode
}

const LONG_PRESS_MS = 500

/** The large white "Bài hôm nay" / Library-entry card on Home (`card-home` spec). */
export default function HomeCard({ title, icon, wide = false, onClick, onLongPress, children }: HomeCardProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  // Set by a completed long-press, to suppress the click a real browser still sends on
  // pointerup; consumed (reset to false) the moment a click is handled, so it never lingers
  // to swallow a later, unrelated activation (e.g. a keyboard Enter/Space).
  const longPressed = useRef(false)

  const startPress = () => {
    clearTimeout(timer.current)
    longPressed.current = false
    if (!onLongPress) return
    timer.current = setTimeout(() => {
      longPressed.current = true
      onLongPress()
    }, LONG_PRESS_MS)
  }
  const endPress = () => {
    clearTimeout(timer.current)
  }

  return (
    <button
      type="button"
      className={`home-card${wide ? ' home-card-wide' : ''}`}
      onClick={() => {
        const suppressed = longPressed.current
        longPressed.current = false
        if (!suppressed) onClick?.()
      }}
      onPointerDown={startPress}
      onPointerUp={endPress}
      onPointerLeave={endPress}
      onPointerCancel={endPress}
    >
      {icon && (
        <span className="home-card-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="home-card-title">{title}</span>
      {children}
    </button>
  )
}
