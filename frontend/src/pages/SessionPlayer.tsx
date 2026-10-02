import type { UseQueryResult } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import type { EventOut, ExamResultOut, QuizResultOut, SummaryOut } from '../api/client'
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
import { useOutboxAutoFlush } from '../offline/useOutboxAutoFlush'
import { getCurrentProfileId } from '../profile'
import ConceptGuide from '../components/ConceptGuide/ConceptGuide'
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
  // Keyed by Session so navigating straight to another Session (e.g. "Luyện tập" from a
  // Concept Guide) starts from clean state.
  return <SessionPlayerInner key={sessionId} />
}

function SessionPlayerInner() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const [chunk, setChunk] = useState(1)
  const [problemIndex, setProblemIndex] = useState(0)
  const [stars, setStars] = useState(0)
  const [completedPosted, setCompletedPosted] = useState(false)
  // Story 3.4: the server's `quiz_submitted` response (every Problem's ✔/↻ + Solutions).
  // The client never grades; this is the only source of a quiz's results.
  const [quizSubmitted, setQuizSubmitted] = useState<EventOut | null>(null)
  // Story 8.1: same shape, for `exam_submitted`.
  const [examSubmitted, setExamSubmitted] = useState<EventOut | null>(null)
  // Story 8.1: true once the backend-computed countdown (`started_at` + `time_limit_s`)
  // reaches zero -- the frontend never owns the clock, only reads it (see `ExamCountdown`).
  // Setting this re-arms the SAME `session_completed`/`exam_submitted` effect `trueEnd`
  // already drives, regardless of how many Problems are actually answered yet.
  const [examTimedOut, setExamTimedOut] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  // Home "Tiếp tục": any mode resumes at the first Problem not yet finished IN THIS Session
  // (the bundle's Session-scoped `done_in_session`), skipping whole finished chunks.
  const [resumed, setResumed] = useState(false)
  // Story 5.2: the Concept Guide overlay (📖), above the still-mounted ProblemPlayer.
  const [guideOpen, setGuideOpen] = useState(false)
  // Story 2.11: true once ANY event (an attempt/self_marked/fallback_revealed/
  // session_completed, from anywhere below) got queued to the offline outbox instead of
  // reaching the server -- replaces the whole Session view with `OfflineScreen` (no local
  // grading happens while this is up). `retryTick` re-arms the `session_completed` effect
  // below after a successful manual flush, since neither `trueEnd` nor `completedPosted`
  // themselves change just because the outbox drained in the background.
  const [offline, setOffline] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryTick, setRetryTick] = useState(0)
  // Review Triage Log #9: true once a flush has confirmed the queue is stuck on something
  // OTHER than "still offline" (a genuine server-side rejection, or a broken store) --
  // `OfflineScreen` shows a different, honest message instead of claiming "chưa kết nối
  // mạng" when the connection is actually fine.
  const [stuckNotNetwork, setStuckNotNetwork] = useState(false)
  // Kept in sync with `offline` so `useOutboxAutoFlush`'s `onDrained` callback below (whose
  // closure is captured once, at mount) can read the CURRENT value rather than the stale
  // one from whenever the effect first ran -- without this, every background flush (even a
  // routine, nothing-queued one on ordinary mount) would needlessly bump `retryTick`.
  const offlineRef = useRef(false)
  useEffect(() => {
    offlineRef.current = offline
  }, [offline])
  // Guards the `session_completed` post against firing more than once per true end (the
  // effect below can re-run while the mutation is still in flight, e.g. a re-render from
  // an unrelated state change) -- a synchronous ref, not state, so it's checked-and-set
  // before any async work starts.
  const postingCompletedRef = useRef(false)
  const profileId = getCurrentProfileId() ?? ''
  const bundle = useSessionBundle(sessionId, profileId, chunk)
  // Story 2.9: the current Profile's `auto_play` setting gates auto-playing a Problem's
  // instruction on open. Defaults to true when the Profile is unknown (fetch failed),
  // matching `Profile.auto_play`'s own default-on; the Problem itself waits for the fetch.
  const profiles = useProfiles()
  const autoPlay = profiles.data?.find((p) => p.id === profileId)?.auto_play ?? true
  const sessionGone =
    bundle.isError && bundle.error instanceof ApiError && bundle.error.code === 'SESSION_NOT_FOUND'

  const problems = bundle.data?.problems ?? []
  const isQuiz = bundle.data?.mode === 'quiz'
  const isExam = bundle.data?.mode === 'exam'
  if (bundle.data && !resumed) {
    const first = bundle.data.problems.findIndex((p) => !p.done_in_session)
    if (first === -1 && bundle.data.chunk < bundle.data.chunk_count) {
      // The whole chunk is finished: look at the next one (`resumed` stays false).
      setChunk(bundle.data.chunk + 1)
      setProblemIndex(0)
    } else {
      setResumed(true)
      setProblemIndex(first === -1 ? bundle.data.problems.length : first)
    }
  }
  const chunkDone = bundle.data !== undefined && problemIndex >= problems.length
  const hasNextChunk = bundle.data !== undefined && bundle.data.chunk < bundle.data.chunk_count
  const trueEnd = chunkDone && !hasNextChunk
  // Story 8.1: an exam's real end is either the ordinary `trueEnd` (every Problem of every
  // chunk done) OR the countdown reaching zero, whichever comes first -- "no further input
  // accepted" applies the instant the clock runs out, even mid-chunk.
  const examEnd = isExam && (trueEnd || examTimedOut)

  const postEvent = usePostEvent(sessionId)
  const summary = useSessionSummary(sessionId, profileId, completedPosted)
  const startReplay = useStartSession()

  // Story 2.11 (AD-10): warm the Workbox `/assets-data/*` runtime cache with this chunk's
  // crop/page/audio URLs as soon as the bundle is fetched, so the rest of the chunk stays
  // available if connectivity drops mid-Session.
  useEffect(() => {
    if (bundle.data) cacheBundleAssets(bundle.data)
  }, [bundle.data])

  // Review Triage Log #10 (2026-10-01, medium): previously only this screen's OWN manual
  // "Thử lại" (`handleRetryOnline` below) ever cleared `offline` -- the app-wide background
  // sweep (mount/`online`, `useOutboxAutoFlush` in `App.tsx`) could silently drain the exact
  // queue that caused this screen to show, leaving the child staring at "chưa kết nối mạng"
  // with nothing left to actually retry. Subscribing here too means EITHER path clears it.
  useOutboxAutoFlush((outcome) => {
    if (!offlineRef.current) return
    if (outcome === 'drained') {
      setOffline(false)
      setStuckNotNetwork(false)
      setRetryTick((t) => t + 1)
    } else if (outcome === 'stopped-rejected' || outcome === 'stopped-store') {
      setStuckNotNetwork(true)
    }
  })

  useEffect(() => {
    const shouldFinish = trueEnd || examEnd
    if (!shouldFinish || completedPosted || postingCompletedRef.current) return
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
      if (isExam) {
        // Story 8.1: `exam_submitted` grades the whole exam Session once, the same
        // "server grades, client never does" posture quiz's own submit has -- fired here
        // whether this is the ordinary true end OR the countdown ran out (`examEnd`),
        // with whatever is answered so far (unanswered Problems grade wrong server-side).
        const [submitted] = await postEvent.mutateAsync({
          profileId,
          events: [
            {
              id: newEventId(),
              kind: 'exam_submitted',
              problem_id: null,
              payload: {},
              occurred_at: new Date().toISOString(),
            },
          ],
        })
        setExamSubmitted(submitted)
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
      else setSubmitError(errorMessage(err))
    })
    // `postEvent` is a fresh `useMutation()` object identity on every render -- only
    // `trueEnd`/`examEnd`/`completedPosted`/`retryTick` should ever re-arm this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trueEnd, examEnd, completedPosted, retryTick])

  async function handleRetryOnline() {
    setRetrying(true)
    try {
      const outcome = await flushOutbox(defaultOutboxStore())
      if (outcome === 'drained') {
        setOffline(false)
        setStuckNotNetwork(false)
        setRetryTick((t) => t + 1)
      } else if (outcome === 'stopped-rejected' || outcome === 'stopped-store') {
        // Review Triage Log #9: the connection is fine -- something else (a server
        // rejection, or the outbox store itself) is jamming the queue. Stay on the offline
        // screen (there is still nothing to show for the un-gradeable Problem), but stop
        // lying about why.
        setStuckNotNetwork(true)
      } else {
        setStuckNotNetwork(false)
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

          {isExam && !examEnd && bundle.data.time_limit_s != null && (
            // Story 8.1: a REAL, visible countdown -- a deliberate departure from this
            // app's own "no timers on child screens" rule, gated to exam mode only. Ticks
            // through both ordinary play and the "Phần tiếp theo" interstitial between
            // chunks; stops once `examEnd` fires (either naturally or by timing out).
            <ExamCountdown
              startedAt={bundle.data.started_at}
              timeLimitS={bundle.data.time_limit_s}
              onExpire={() => setExamTimedOut(true)}
            />
          )}

          {offline ? (
            // Story 2.11: replaces the whole Session view -- no local grading happens
            // while an event is queued in the offline outbox.
            <OfflineScreen
              onRetry={() => void handleRetryOnline()}
              retrying={retrying}
              stuckNotNetwork={stuckNotNetwork}
            />
          ) : problems.length === 0 ? (
            <p className="home-empty">Phần này chưa có bài tập nào để hiển thị.</p>
          ) : examEnd && !examSubmitted ? (
            // Story 8.1: mirrors quiz's own "submitting, no feedback yet" screen below --
            // reached either from the ordinary true end OR the countdown running out.
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
                <p>{examTimedOut ? phrase('exam_time_up') : 'Đang tải…'}</p>
              )}
            </div>
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
          ) : trueEnd || examEnd ? (
            <>
              {submitError && !completedPosted && (
                // `session_completed` failed for a non-offline reason (any mode; for a quiz
                // `quiz_submitted` already went through): say so, and re-arm the post.
                <div className="session-done">
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
                </div>
              )}
              {isQuiz && quizSubmitted && <QuizResultsScreen submitted={quizSubmitted} />}
              {/* Story 8.1: exam shows ONLY its own results screen -- never the generic
               * `SessionSummaryScreen` (StarBurst/Streak/"Luyện lại bài sai" would all be
               * zero/misleading for a mode that awards none of those by design). */}
              {isExam && examSubmitted && <ExamResultsScreen submitted={examSubmitted} />}
              {!isExam && !(submitError && !completedPosted) && (
                <SessionSummaryScreen
                  autoPlay={autoPlay}
                  summary={summary}
                  onReplay={handleReplay}
                  replayPending={startReplay.isPending}
                  replayError={startReplay.isError ? errorMessage(startReplay.error) : null}
                />
              )}
            </>
          ) : chunkDone ? (
            <div className="session-done">
              {hasNextChunk && (
                <button type="button" onClick={goToNextChunk}>
                  Phần tiếp theo ➜
                </button>
              )}
            </div>
          ) : profiles.isPending ? (
            // The Problem's auto-play must know the Profile's `auto_play` before it opens
            // (usually already cached from Home), or it could speak against the setting.
            <p>Đang tải…</p>
          ) : (
            <>
              {(isQuiz || isExam) && (
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
              {!isQuiz && !isExam && problems[problemIndex].problem.concept_ids.length > 0 && (
                <button
                  type="button"
                  className="concept-guide-open"
                  aria-label="Xem hướng dẫn"
                  onClick={() => setGuideOpen(true)}
                >
                  📖
                </button>
              )}
              {guideOpen && !isQuiz && !isExam && (
                <ConceptGuide
                  key={`guide-${problems[problemIndex].problem.problem_id}`}
                  conceptIds={problems[problemIndex].problem.concept_ids}
                  grade={profiles.data?.find((p) => p.id === profileId)?.grade ?? 0}
                  profileId={profileId}
                  onClose={() => setGuideOpen(false)}
                />
              )}
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
                quiz={isQuiz || isExam}
                grade={profiles.data?.find((p) => p.id === profileId)?.grade ?? 0}
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
  autoPlay: boolean
  summary: UseQueryResult<SummaryOut, unknown>
  onReplay: () => void
  replayPending: boolean
  replayError: string | null
}

/** The real summary screen (Story 2.10): shown once at the true end of a Session, after
 * `session_completed` has been posted and `GET /sessions/{id}/summary` resolves. Shows the
 * fanfare/first-try count via `StarBurst` (reusing its "N ⭐" shape for the first-try-correct
 * count, not the in-Session Star tally `ProblemPlayer` already showed), the Streak, and
 * "Luyện lại bài sai" -- hidden entirely when there are zero wrong Problems (per this
 * story's frozen Boundaries: never shown for nothing to replay). */
function SessionSummaryScreen({
  autoPlay,
  summary,
  onReplay,
  replayPending,
  replayError,
}: SessionSummaryScreenProps) {
  const newBadges = summary.data?.new_badges ?? []
  // Story 3.2: fanfare + 🔊 the moment the summary resolves with 1+ newly earned badges
  // -- runs once per Session summary (keyed by the joined badge list, which only ever
  // changes when a genuinely different summary loads).
  const newBadgesKey = newBadges.join(',')
  useEffect(() => {
    if (newBadges.length === 0 || !autoPlay) return
    speak(phrase('new_badge_earned'))
      .then(() => {
        for (const key of newBadges) void speak(badgeName(key)).catch(() => {})
      })
      .catch(() => {})
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
      {replayError && (
        <p role="alert" className="form-error">
          {replayError}
        </p>
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

/** Story 8.1: a REAL, visible countdown -- the backend (`started_at` + `time_limit_s`,
 * both re-read from the bundle on every mount, never a client-side anchor) is the single
 * source of truth, so a closed-and-reopened tablet mid-exam shows the actual remaining
 * time, never a reset one. Fires `onExpire()` exactly once, the instant remaining time
 * reaches zero -- this is this codebase's first `setInterval`-driven live UI element (no
 * existing countdown precedent to follow; every other timer in this app is a one-shot
 * `setTimeout` delay), so it follows the same "ref'd handle, cleared on unmount/re-run"
 * convention `ProblemPlayer.tsx`'s own one-shot timers already use. */
function ExamCountdown({
  startedAt,
  timeLimitS,
  onExpire,
}: {
  startedAt: string
  timeLimitS: number
  onExpire: () => void
}) {
  const deadlineMs = new Date(startedAt).getTime() + timeLimitS * 1000
  const [remainingMs, setRemainingMs] = useState(() => deadlineMs - Date.now())
  const expiredRef = useRef(false)

  useEffect(() => {
    expiredRef.current = false
    const tick = () => {
      const left = deadlineMs - Date.now()
      setRemainingMs(left)
      if (left <= 0 && !expiredRef.current) {
        expiredRef.current = true
        onExpire()
      }
    }
    tick()
    const handle = window.setInterval(tick, 1000)
    return () => window.clearInterval(handle)
    // `onExpire` is a fresh closure every render (it captures `setExamTimedOut`, which is
    // itself stable) -- only `deadlineMs` should ever restart the interval.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadlineMs])

  const clamped = Math.max(0, remainingMs)
  const totalSeconds = Math.ceil(clamped / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return (
    <p className="exam-countdown" data-testid="exam-countdown" aria-live="polite">
      {phrase('exam_indicator')}: {minutes}:{String(seconds).padStart(2, '0')}
    </p>
  )
}

/** Story 8.1: the exam results, straight from the server's `exam_submitted` response --
 * every Problem marked ✔ (right) or ↻ (to practise again, with its Solution). Never red,
 * never ✗ or "Sai!" -- same warm wording rule as quiz's own results, even though exam mode
 * itself is the deliberate "real timer" exception. Deliberately has NO Stars line (exam
 * mode awards zero, always) and is shown INSTEAD OF `SessionSummaryScreen` (no Streak, no
 * "Luyện lại bài sai" -- none of those apply to a pure assessment). */
function ExamResultsScreen({ submitted }: { submitted: EventOut }) {
  const results: ExamResultOut[] = submitted.exam_results ?? []
  return (
    <div className="session-done" data-testid="exam-results">
      <h2>{phrase('exam_results_title')}</h2>
      <ol className="quiz-results">
        {results.map((r) => (
          <li
            key={r.problem_id}
            className={r.correct ? 'quiz-result-right' : 'quiz-result-retry'}
            data-testid={`exam-result-${r.correct ? 'right' : 'retry'}`}
          >
            <span
              className="quiz-result-mark"
              role="img"
              aria-label={r.correct ? phrase('exam_result_right') : phrase('exam_result_retry')}
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
    </div>
  )
}
