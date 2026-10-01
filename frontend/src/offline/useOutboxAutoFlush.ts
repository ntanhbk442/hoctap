import { useEffect } from 'react'
import { defaultOutboxStore, flushOutbox, type FlushOutcome } from './outbox'

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
 *
 * `onDrained` (Review Triage Log #10, 2026-10-01, medium): called with the outcome every
 * time this hook's OWN background flush (mount or `online`) finishes. Previously, only a
 * screen's own manual "Thử lại" button ever cleared its `offline` state -- if THIS
 * background sweep (not the manual retry) drained the exact queue that caused the offline
 * screen to show, the child was left staring at "chưa kết nối mạng" even though the data
 * was already safely on the server, with no way forward except tapping a button that was
 * never actually needed. `SessionPlayer` passes a callback here that clears its own
 * `offline` flag once `outcome === 'drained'`.
 */
export function useOutboxAutoFlush(onDrained?: (outcome: FlushOutcome) => void): void {
  useEffect(() => {
    const store = defaultOutboxStore()
    const flush = () => {
      // Review Triage Log #11: `flushOutbox()` itself never rejects (`drain()` catches its
      // own store failures and resolves `'stopped-store'`), but `onDrained` is caller code
      // this hook doesn't control -- guard it too so a caller's own bug can't turn this
      // background sweep into an unhandled promise rejection.
      flushOutbox(store)
        .then((outcome) => onDrained?.(outcome))
        .catch((err: unknown) => {
          console.error('[offline outbox] background flush failed unexpectedly:', err)
        })
    }
    flush()
    window.addEventListener('online', flush)
    return () => window.removeEventListener('online', flush)
    // Intentionally mount-once: callers pass a stable setter (e.g. `setOffline`), so
    // capturing `onDrained` as it was at mount is fine, and re-running this effect on every
    // render's new inline-function identity would re-attach the `online` listener
    // needlessly (and double-flush on mount via StrictMode).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
