import type { UseQueryResult } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import type { EventOut, QuizResultOut, SummaryOut } from '../api/client'
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
import { speak } from '../audio/speech'
import Badge from '../components/Badge/Badge'
import { badgeName } from '../components/Badge/badgeCopy'
import ProgressDots, { type DotState } from '../components/ProgressDots/ProgressDots'
import SolutionPanel from '../components/SolutionPanel/SolutionPanel'
import StarBurst from '../components/StarBurst/StarBurst'
import { newEventId } from '../ids'
import { cacheBundleAssets } from '../offline/assetCache'
import OfflineScreen from '../offline/OfflineScreen'
import { defaultOutboxStore, flushOutbox, QueuedOfflineError } from '../offline/outbox'
import { getCurrentProfileId } from '../profile'
import FlagButton from '../components/FlagButton/FlagButton'
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
  // Story 3.4: the server's `quiz_submitted` response (every Problem's ✔/↻ + Solutions).
  // The client never grades; this is the only source of a quiz's results.
  const [quizSubmitted, setQuizSubmitted] = useState<EventOut | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  // Story 3.4: a resumed quiz (Home "Tiếp tục") starts at its first unanswered Problem.
  const [resumed, setResumed] = useState(false)
  // Story 2.11: true once ANY event (an attempt/self_marked/fallback_revealed/
  // session_completed, from anywhere below) got queued to the offline outbox instead of
  // reaching the server -- replaces the whole Session view with `OfflineScreen` (no local
  // grading happens while this is up). `retryTick` re-arms the `session_completed` effect
  // below after a successful manual flush, since neither `trueEnd` nor `completedPosted`
  // themselves change just because the outbox drained in the background.
  const [offline, setOffline] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryTick, setRetryTick] = useState(0)
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
  const isQuiz = bundle.data?.mode === 'quiz'
  if (bundle.data && !resumed) {
    setResumed(true)
    if (bundle.data.mode === 'quiz') {
      const first = bundle.data.problems.findIndex((p) => !p.attempted)
      setProblemIndex(first === -1 ? bundle.data.problems.length : first)
    }
  }
  const chunkDone = bundle.data !== undefined && problemIndex >= problems.length
  const hasNextChunk = bundle.data !== undefined && bundle.data.chunk < bundle.data.chunk_count
  const trueEnd = chunkDone && !hasNextChunk

  const postEvent = usePostEvent(sessionId)
  const summary = useSessionSummary(sessionId, profileId, completedPosted)
  const startReplay = useStartSession()

  // Story 2.11 (AD-10): warm the Workbox `/assets-data/*` runtime cache with this chunk's
  // crop/page/audio URLs as soon as the bundle is fetched, so the rest of the chunk stays
  // available if connectivity drops mid-Session.
  useEffect(() => {
    if (bundle.data) cacheBundleAssets(bundle.data)
  }, [bundle.data])

  useEffect(() => {
    if (!trueEnd || completedPosted || postingCompletedRef.current) return
    postingCompletedRef.current = true
    const post = async () => {
      if (isQuiz) {
        // Story 3.4: `quiz_submitted` (server grading) comes right before
        // `session_completed`. A resend after an offline retry just returns the stored
        // result, so re-running this from the top is safe.
        const [submitted] = await postEvent.mutateAsync({
          profileId,
          events: [
            {
              id: newEventId(),
              kind: 'quiz_submitted',
              problem_id: null,
              payload: {},
              occurred_at: new Date().toISOString(),
            },
          ],
        })
        setQuizSubmitted(submitted)
      }
      await postEvent.mutateAsync({
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
      setCompletedPosted(true)
    }
    post().catch((err: unknown) => {
      postingCompletedRef.current = false
      // Story 2.11: queued to the offline outbox rather than a real error -- show the
      // offline screen; the retry below (or the app-wide `online` auto-flush) re-arms
      // this same effect via `retryTick` once the queue has actually drained.
      if (err instanceof QueuedOfflineError) setOffline(true)
      else if (isQuiz) setSubmitError(errorMessage(err))
    })
    // `postEvent` is a fresh `useMutation()` object identity on every render -- only
    // `trueEnd`/`completedPosted`/`retryTick` should ever re-arm this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trueEnd, completedPosted, retryTick])

  async function handleRetryOnline() {
    setRetrying(true)
    try {
      const outcome = await flushOutbox(defaultOutboxStore())
      if (outcome === 'drained') {
        setOffline(false)
        setRetryTick((t) => t + 1)
      }
    } finally {
      setRetrying(false)
    }
  }

  function goToNextChunk() {
    setChunk((c) => c + 1)
    setProblemIndex(0)
  }

  function handleReplay() {
    startReplay.mutate(
      {
        profileId,
        ref: { kind: 'replay', source_session_id: sessionId },
        mode: 'replay',
      },
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

          {offline ? (
            // Story 2.11: replaces the whole Session view -- no local grading happens
            // while an event is queued in the offline outbox.
            <OfflineScreen onRetry={() => void handleRetryOnline()} retrying={retrying} />
          ) : problems.length === 0 ? (
            <p className="home-empty">Phần này chưa có bài tập nào để hiển thị.</p>
          ) : trueEnd && isQuiz && !quizSubmitted ? (
            <div className="session-done">
              {submitError ? (
                <>
                  <p role="alert" className="form-error">
                    {submitError}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setSubmitError(null)
                      setRetryTick((t) => t + 1)
                    }}
                  >
                    Thử lại
                  </button>
                </>
              ) : (
                <p>Đang tải…</p>
              )}
            </div>
          ) : trueEnd ? (
            <>
              {isQuiz && quizSubmitted && <QuizResultsScreen submitted={quizSubmitted} />}
              <SessionSummaryScreen
                summary={summary}
                onReplay={handleReplay}
                replayPending={startReplay.isPending}
              />
            </>
          ) : chunkDone ? (
            <div className="session-done">
              {hasNextChunk && (
                <button type="button" onClick={goToNextChunk}>
                  Phần tiếp theo ➜
                </button>
              )}
            </div>
          ) : (
            <>
              {isQuiz && (
                <ProgressDots
                  dots={problems.map((_, i): DotState =>
                    i < problemIndex ? 'done' : i === problemIndex ? 'current' : 'todo',
                  )}
                />
              )}
              <FlagButton
                key={`flag-${problems[problemIndex].problem.problem_id}`}
                problemId={problems[problemIndex].problem.problem_id}
                profileId={profileId}
              />
              <ProblemPlayer
                key={problems[problemIndex].problem.problem_id}
                sessionId={sessionId}
                profileId={profileId}
                bundleProblem={problems[problemIndex]}
                stars={stars}
                onStarEarned={() => setStars((s) => s + 1)}
                onDone={() => setProblemIndex((i) => i + 1)}
                autoPlay={autoPlay}
                onOffline={() => setOffline(true)}
                quiz={isQuiz}
              />
            </>
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
  const newBadges = summary.data?.new_badges ?? []
  // Story 3.2: fanfare + 🔊 the moment the summary resolves with 1+ newly earned badges
  // -- runs once per Session summary (keyed by the joined badge list, which only ever
  // changes when a genuinely different summary loads).
  const newBadgesKey = newBadges.join(',')
  useEffect(() => {
    if (newBadges.length === 0) return
    void speak(phrase('new_badge_earned')).then(() => {
      for (const key of newBadges) void speak(badgeName(key))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newBadgesKey])

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
      {/* Story 3.1: `stars_earned` (this Session's own `progress_stars` SUM) is a
       * DIFFERENT, wider metric than the `StarBurst` above (first-try-correct count) --
       * see `learning.summary.SessionSummary`'s own docstring. A plain "n" satisfies the
       * AC's literal wording without a second burst animation. */}
      <p data-testid="stars-earned">
        {phrase('stars_earned')}: {data.stars_earned} ⭐
      </p>
      {data.streak > 0 && (
        <p>
          {data.streak} {phrase('streak_days')}
        </p>
      )}
      {newBadges.length > 0 && (
        <div className="session-new-badges" data-testid="session-new-badges">
          <p>{phrase('new_badge_earned')}</p>
          {newBadges.map((badgeKey) => (
            <Badge key={badgeKey} badgeKey={badgeKey} earned pop />
          ))}
        </div>
      )}
      {hasWrong && (
        <button type="button" onClick={onReplay} disabled={replayPending}>
          {phrase('practice_wrong_again')}
        </button>
      )}
    </div>
  )
}

/** Story 3.4: the quiz results, straight from the server's `quiz_submitted` response --
 * every Problem marked ✔ (right) or ↻ (to practise again, with its Solution). Never red, never
 * ✗ or "Sai!". The Stars line comes from the Session summary below. */
function QuizResultsScreen({ submitted }: { submitted: EventOut }) {
  const results: QuizResultOut[] = submitted.quiz_results ?? []
  return (
    <div className="session-done" data-testid="quiz-results">
      <h2>{phrase('quiz_results_title')}</h2>
      <ol className="quiz-results">
        {results.map((r) => (
          <li
            key={r.problem_id}
            className={r.correct ? 'quiz-result-right' : 'quiz-result-retry'}
            data-testid={`quiz-result-${r.correct ? 'right' : 'retry'}`}
          >
            <span
              className="quiz-result-mark"
              role="img"
              aria-label={r.correct ? phrase('quiz_result_right') : phrase('quiz_result_retry')}
            >
              {r.correct ? '✔' : '↻'}
            </span>
            <span>{r.display_label}</span>
            {!r.correct &&
              r.solutions.map((s) => (
                <SolutionPanel
                  key={s.part_key}
                  steps={s.solution.steps}
                  revealedCount={s.solution.steps.length}
                />
              ))}
          </li>
        ))}
      </ol>
      {submitted.quiz_stars_awarded === false && <p>{phrase('quiz_retake_no_stars')}</p>}
    </div>
  )
}
