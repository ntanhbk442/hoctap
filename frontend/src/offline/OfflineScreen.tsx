import { phrase } from '../audio/phrases'
import { speak } from '../audio/speech'
import SpeakerButton from '../components/SpeakerButton/SpeakerButton'

export interface OfflineScreenProps {
  /** Manual retry (I/O matrix "Offline screen, retry tapped"): attempts to flush the
   * outbox; if it's still offline, this screen just stays up -- no crash, no change. */
  onRetry: () => void
  retrying?: boolean
  /** Review Triage Log #9 (2026-10-01, medium): true once a flush attempt has confirmed the
   * queue is stuck on something OTHER than "still offline" (a genuine server-side rejection,
   * e.g. a `problem_id` invalidated by a content edit after it was queued, or a broken
   * store -- see `outbox.ts`'s `FlushOutcome`). Defaults `false` (the original "chưa kết nối
   * mạng" wording), which stays correct and honest for the overwhelmingly common real case
   * (a genuinely unreachable server) and for every existing caller/test that doesn't pass
   * this prop. */
  stuckNotNetwork?: boolean
}

/**
 * "Máy tính bảng chưa kết nối…" (Story 2.11): shown instead of the Problem/Session screen
 * once an event has been queued to the offline outbox. No local grading of any kind is
 * ever computed while this is up -- the child sees no correct/wrong verdict until the
 * server actually answers (post-flush).
 */
export default function OfflineScreen({ onRetry, retrying = false, stuckNotNetwork = false }: OfflineScreenProps) {
  const label = phrase(stuckNotNetwork ? 'offline_stuck_not_network' : 'offline_not_connected')
  return (
    <div className="session-done" data-testid="offline-screen">
      <p role="alert">{label}</p>
      <SpeakerButton label={`Nghe: ${label}`} onClick={() => void speak(label)} />
      <button type="button" onClick={onRetry} disabled={retrying}>
        Thử lại
      </button>
    </div>
  )
}
