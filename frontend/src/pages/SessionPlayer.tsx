import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errors'
import { useProfiles, useSessionBundle } from '../api/queries'
import { phrase } from '../audio/phrases'
import { getCurrentProfileId } from '../profile'
import ProblemPlayer from './ProblemPlayer'

/**
 * The real, one-Problem-at-a-time player (Story 2.6): fetches a Session's current chunk
 * ("Phần i/n"), owns which Problem of it is current, and delegates everything below that
 * (widget-per-type switcher, ✔ Kiểm tra, the Attempt submit/feedback sequence) to
 * `ProblemPlayer`. Story 2.4's read-only bundle listing is gone -- Bin now actually answers
 * each Problem instead of only seeing a list of them.
 */
export default function SessionPlayer() {
  const { sessionId = '' } = useParams()
  const [chunk, setChunk] = useState(1)
  const [problemIndex, setProblemIndex] = useState(0)
  const [stars, setStars] = useState(0)
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

  function goToNextChunk() {
    setChunk((c) => c + 1)
    setProblemIndex(0)
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
          ) : chunkDone ? (
            <div className="session-done">
              <p>{phrase('session_summary')}</p>
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
