import { useEffect } from 'react'
import { defaultOutboxStore, flushOutbox } from './outbox'

/**
 * App-wide reconnect flush (Story 2.11, AD-10): as soon as the browser fires `online`,
 * attempt to flush whatever the event outbox is holding, in the background -- covers the
 * general case (any queued event, from any Session/screen), independent of whichever
 * specific screen showed the offline UI when the event was first queued. Also flushes
 * once on mount, so a tablet relaunched already-online (the queue survived the restart,
 * per this story's Boundaries & Constraints) doesn't have to wait for an `online` event
 * that will never fire (the browser never WAS offline this session).
 *
 * Screens that show the "Máy tính bảng chưa kết nối…" offline screen (e.g. `SessionPlayer`)
 * still call `flushOutbox()` themselves on a manual retry tap -- this hook is a
 * best-effort background sweep, not the only place a flush can be triggered.
 */
export function useOutboxAutoFlush(): void {
  useEffect(() => {
    const store = defaultOutboxStore()
    const flush = () => void flushOutbox(store)
    flush()
    window.addEventListener('online', flush)
    return () => window.removeEventListener('online', flush)
  }, [])
}
