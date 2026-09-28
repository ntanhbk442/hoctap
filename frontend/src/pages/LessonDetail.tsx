import { Link, useParams } from 'react-router'
import { errorMessage } from '../api/errors'
import { useLibraryLesson } from '../api/queries'

/**
 * One Lesson's visible Problems (Story 2.3): a read-only, numbered list -- no Problem
 * player yet (that is a later Epic 2 widget story, see `deferred-work.md`). Reachable both
 * from the Library and from Home's "Học tiếp" card.
 */
export default function LessonDetail() {
  const { bookId = '', unitKey = '', lessonKey = '' } = useParams()
  const problems = useLibraryLesson(bookId, unitKey, lessonKey)

  return (
    <main className="home">
      <h1>Bài học</h1>

      {problems.isPending && <p>Đang tải…</p>}

      {problems.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(problems.error)}
          </p>
          <button type="button" onClick={() => void problems.refetch()}>
            Thử lại
          </button>
        </>
      )}

      {problems.data?.length === 0 && <p className="home-empty">Chưa có bài tập nào ở đây.</p>}

      {problems.data && problems.data.length > 0 && (
        <ol className="lesson-problem-list">
          {problems.data.map((p, i) => (
            <li key={p.problem_id} className="lesson-problem-row">
              <span className="lesson-problem-label">{p.display_label || `Bài ${i + 1}`}</span>
              {p.instruction && <span className="lesson-problem-instruction">{p.instruction}</span>}
            </li>
          ))}
        </ol>
      )}

      <p className="parent-link">
        <Link to="/library">Về Sách</Link>
      </p>
    </main>
  )
}
