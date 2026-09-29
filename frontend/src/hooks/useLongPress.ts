import { useEffect, useRef } from 'react'

/**
 * Pointer handlers that fire `onLongPress` once the pointer has been held for `ms`.
 * Releasing or leaving earlier does nothing. `HomeCard` keeps its own 500 ms press for the
 * audio label; this one is the 2-second Parent Area lock.
 */
export function useLongPress(onLongPress: () => void, ms: number) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const callback = useRef(onLongPress)
  useEffect(() => {
    callback.current = onLongPress
  })
  useEffect(() => () => clearTimeout(timer.current), [])

  const cancel = () => clearTimeout(timer.current)
  return {
    onPointerDown: () => {
      clearTimeout(timer.current)
      timer.current = setTimeout(() => callback.current(), ms)
    },
    onPointerUp: cancel,
    onPointerLeave: cancel,
    onPointerCancel: cancel,
    onContextMenu: (event: { preventDefault: () => void }) => event.preventDefault(),
  }
}
