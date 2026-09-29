import { useLongPress } from '../hooks/useLongPress'

export const PARENT_LOCK_MS = 2000

/**
 * The 🔒 on the child's Home (Story 4.1, UX-DR6). Only a 2-second hold opens the PIN gate;
 * a tap or click does nothing, so a child cannot wander into the Parent Area. The button has
 * no click handler, so the click that follows a completed press has nothing to trigger.
 */
export default function ParentLock({ onOpen }: { onOpen: () => void }) {
  const press = useLongPress(onOpen, PARENT_LOCK_MS)
  return (
    <button
      type="button"
      className="parent-lock"
      aria-label="Khu vực phụ huynh (giữ 2 giây)"
      title="Giữ 2 giây"
      {...press}
    >
      <span aria-hidden="true">🔒</span>
    </button>
  )
}
