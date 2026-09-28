import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errors'
import { useSessionBundle } from '../api/queries'
import { getCurrentProfileId } from '../profile'

/**
 * The read-only bundle-rendering placeholder Story 2.4 needs (not a real Problem player --
 * that is a later Epic 2 widget story, see `deferred-work.md`): a Session's current chunk
 * ("Phần i/n"), each Problem numbered, with an "đã làm" mark for `attempted` Problems, and
 * simple Prev/Next chunk navigation when the Session has more than one chunk.
 */
export default function SessionPlayer() {
  const { sessionId = '' } = useParams()
  const [chunk, setChunk] = useState(1)
  const profileId = getCurrentProfileId() ?? ''
  const bundle = useSessionBundle(sessionId, profileId, chunk)
  const sessionGone =
    bundle.isError && bundle.error instanceof ApiError && bundle.error.code === 'SESSION_NOT_FOUND'

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
          {bundle.data.problems.length === 0 ? (
            <p className="home-empty">Phần này chưa có bài tập nào để hiển thị.</p>
          ) : (
            <ol className="lesson-problem-list">
              {bundle.data.problems.map((p, i) => (
                <li key={p.problem.problem_id} className="lesson-problem-row">
                  <span className="lesson-problem-label">
                    {p.problem.display_label || `Bài ${i + 1}`}
                  </span>
                  {p.problem.instruction && (
                    <span className="lesson-problem-instruction">{p.problem.instruction}</span>
                  )}
                  {p.attempted && <span data-testid="attempted-mark">Đã làm</span>}
                </li>
              ))}
            </ol>
          )}
          {bundle.data.chunk_count > 1 && (
            <div className="session-chunk-nav">
              <button type="button" disabled={chunk <= 1} onClick={() => setChunk((c) => c - 1)}>
                Phần trước
              </button>
              <button
                type="button"
                disabled={chunk >= bundle.data.chunk_count}
                onClick={() => setChunk((c) => c + 1)}
              >
                Phần sau
              </button>
            </div>
          )}
        </>
      )}

      <p className="parent-link">
        <Link to="/library">Về Sách</Link>
      </p>
    </main>
  )
}
