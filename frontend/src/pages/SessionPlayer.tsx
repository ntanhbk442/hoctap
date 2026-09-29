import type { UseQueryResult } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import type { SummaryOut } from '../api/client'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errors'
import {
  usePostEvent,
  useProfiles,
  useSessionBundle,
  useSessionSummary,
  useStartSession,
} from '../api/queries'
import { phrase } from '../audio/phrases'
import StarBurst from '../components/StarBurst/StarBurst'
import { newEventId } from '../ids'
import { getCurrentProfileId } from '../profile'
import ProblemPlayer from './ProblemPlayer'

/**
 * The real, one-Problem-at-a-time player (Story 2.6): fetches a Session's current chunk
 * ("Phần i/n"), owns which Problem of it is current, and delegates everything below that
 * (widget-per-type switcher, ✔ Kiểm tra, the Attempt submit/feedback sequence) to
 * `ProblemPlayer`. Story 2.4's read-only bundle listing is gone -- Bin now actually answers
 * each Problem instead of only seeing a list of them.
 *
 * Story 2.10: `chunkDone` alone (Story 2.6) only meant "this CHUNK is done" -- it fires
 * between every chunk, not just at the real end. `trueEnd` (`chunkDone && !hasNextChunk`)
 * is the actual end of the whole Session: only THEN is `session_completed` posted and the
 * real summary screen (first-try count, Streak, "Luyện lại bài sai") shown. A mid-Session
 * chunk boundary (`chunkDone && hasNextChunk`) keeps Story 2.6's unchanged behaviour --
 * advance to the next chunk, no summary, no `session_completed`.
 */
export default function SessionPlayer() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const [chunk, setChunk] = useState(1)
  const [problemIndex, setProblemIndex] = useState(0)
  const [stars, setStars] = useState(0)
  const [completedPosted, setCompletedPosted] = useState(false)
  // Guards the `session_completed` post against firing more than once per true end (the
  // effect below can re-run while the mutation is still in flight, e.g. a re-render from
  // an unrelated state change) -- a synchronous ref, not state, so it's checked-and-set
  // before any async work starts.
  const postingCompletedRef = useRef(false)
  const profileId = getCurrentProfileId() ?? ''
  const bundle = useSessionBundle(sessionId, profileId, chunk)
  // Story 2.9: the current Profile's `auto_play` setting gates auto-playing a Problem's
  // instruction on open. Defaults to true while Profiles are still loading/unknown, matching
  // `Profile.auto_play`'s own default-on -- never blocks the player on this fetch.
  const profiles = useProfiles()
  const autoPlay = profiles.data?.find((p) => p.id === profileId)?.auto_play ?? true
  const sessionGone =
    bundle.isError && bundle.error instanceof ApiError && bundle.error.code === 'SESSION_NOT_FOUND'

  const problems = bundle.data?.problems ?? []
  const chunkDone = bundle.data !== undefined && problemIndex >= problems.length
  const hasNextChunk = bundle.data !== undefined && bundle.data.chunk < bundle.data.chunk_count
  const trueEnd = chunkDone && !hasNextChunk

  const postEvent = usePostEvent(sessionId)
  const summary = useSessionSummary(sessionId, profileId, completedPosted)
  const startReplay = useStartSession()

  useEffect(() => {
    if (!trueEnd || completedPosted || postingCompletedRef.current) return
    postingCompletedRef.current = true
    postEvent
      .mutateAsync({
        profileId,
        events: [
          {
            id: newEventId(),
            kind: 'session_completed',
            problem_id: null,
            payload: {},
            occurred_at: new Date().toISOString(),
          },
        ],
      })
      .then(() => setCompletedPosted(true))
      .catch(() => {
        postingCompletedRef.current = false
      })
    // `postEvent` is a fresh `useMutation()` object identity on every render -- only
    // `trueEnd`/`completedPosted` should ever re-arm this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trueEnd, completedPosted])

  function goToNextChunk() {
    setChunk((c) => c + 1)
    setProblemIndex(0)
  }

  function handleReplay() {
    startReplay.mutate(
      { profileId, ref: { kind: 'replay', source_session_id: sessionId }, mode: 'replay' },
      { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
    )
  }

  return (
    <main className="home">
      <h1>Lượt học</h1>

      {bundle.isPending && <p>Đang tải…</p>}

      {sessionGone ? (
        <p role="alert" className="form-error">
          Lượt học này không còn tồn tại. Hãy quay lại Sách để bắt đầu lại.
        </p>
      ) : (
        bundle.isError && (
          <>
            <p role="alert" className="form-error">
              {errorMessage(bundle.error)}
            </p>
            <button type="button" onClick={() => void bundle.refetch()}>
              Thử lại
            </button>
          </>
        )
      )}

      {bundle.data && (
        <>
          <p className="session-chunk-label">{bundle.data.chunk_label}</p>

          {problems.length === 0 ? (
            <p className="home-empty">Phần này chưa có bài tập nào để hiển thị.</p>
          ) : trueEnd ? (
            <SessionSummaryScreen
              summary={summary}
              onReplay={handleReplay}
              replayPending={startReplay.isPending}
            />
          ) : chunkDone ? (
            <div className="session-done">
              {hasNextChunk && (
                <button type="button" onClick={goToNextChunk}>
                  Phần tiếp theo ➜
                </button>
              )}
            </div>
          ) : (
            <ProblemPlayer
              key={problems[problemIndex].problem.problem_id}
              sessionId={sessionId}
              profileId={profileId}
              bundleProblem={problems[problemIndex]}
              stars={stars}
              onStarEarned={() => setStars((s) => s + 1)}
              onDone={() => setProblemIndex((i) => i + 1)}
              autoPlay={autoPlay}
            />
          )}
        </>
      )}

      <p className="parent-link">
        <Link to="/library">Về Sách</Link>
      </p>
    </main>
  )
}

interface SessionSummaryScreenProps {
  summary: UseQueryResult<SummaryOut, unknown>
  onReplay: () => void
  replayPending: boolean
}

/** The real summary screen (Story 2.10): shown once at the true end of a Session, after
 * `session_completed` has been posted and `GET /sessions/{id}/summary` resolves. Shows the
 * fanfare/first-try count via `StarBurst` (reusing its "N ⭐" shape for the first-try-correct
 * count, not the in-Session Star tally `ProblemPlayer` already showed), the Streak, and
 * "Luyện lại bài sai" -- hidden entirely when there are zero wrong Problems (per this
 * story's frozen Boundaries: never shown for nothing to replay). */
function SessionSummaryScreen({ summary, onReplay, replayPending }: SessionSummaryScreenProps) {
  if (summary.isPending) {
    return (
      <div className="session-done">
        <p>Đang tải…</p>
      </div>
    )
  }
  if (summary.isError) {
    return (
      <div className="session-done">
        <p role="alert" className="form-error">
          {errorMessage(summary.error)}
        </p>
      </div>
    )
  }
  const data = summary.data
  const hasWrong = data.wrong_problem_ids.length > 0
  return (
    <div className="session-done">
      <StarBurst count={data.first_try_correct} justEarned />
      <p>{phrase('session_summary')}</p>
      <p>
        {data.first_try_correct}/{data.total}
      </p>
      {data.streak > 0 && (
        <p>
          {data.streak} {phrase('streak_days')}
        </p>
      )}
      {hasWrong && (
        <button type="button" onClick={onReplay} disabled={replayPending}>
          {phrase('practice_wrong_again')}
        </button>
      )}
    </div>
  )
}
