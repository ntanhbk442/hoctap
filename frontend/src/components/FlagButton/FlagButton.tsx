import { useState } from 'react'
import { flagProblem } from '../../api/client'
import { phrase } from '../../audio/phrases'

type State = 'idle' | 'confirm' | 'sending' | 'done' | 'failed'

/**
 * Story 4.4: the child's 🚩. A "Có / Không" confirm, then one call; the Problem stays
 * visible and Bin only sees a calm acknowledgement. Never queued offline: a failed call
 * shows a neutral retry message. No red, no ✗, no "Sai!".
 */
export default function FlagButton({
  problemId,
  profileId,
}: {
  problemId: string
  profileId: string
}) {
  const [state, setState] = useState<State>('idle')

  async function send() {
    setState('sending')
    try {
      await flagProblem(problemId, profileId)
      setState('done')
    } catch {
      setState('failed')
    }
  }

  if (state === 'done') {
    return (
      <p className="flag-bar" role="status">
        {phrase('flag_done')}
      </p>
    )
  }
  if (state === 'confirm' || state === 'sending') {
    return (
      <div className="flag-bar" role="group" aria-label={phrase('flag_confirm')}>
        <span>{phrase('flag_confirm')}</span>
        <button type="button" disabled={state === 'sending'} onClick={() => void send()}>
          {phrase('flag_yes')}
        </button>
        <button type="button" disabled={state === 'sending'} onClick={() => setState('idle')}>
          {phrase('flag_no')}
        </button>
      </div>
    )
  }
  return (
    <div className="flag-bar">
      <button
        type="button"
        aria-label={phrase('flag_button')}
        onClick={() => setState('confirm')}
      >
        🚩
      </button>
      {state === 'failed' && <span role="status">{phrase('flag_failed')}</span>}
    </div>
  )
}
