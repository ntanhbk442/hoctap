import { Link, useNavigate, useParams } from 'react-router'
import { errorMessage } from '../api/errors'
import { useLibraryBooks, useLibraryLesson, useProfiles, useStartSession } from '../api/queries'
import { phrase } from '../audio/phrases'
import { getCurrentProfileId } from '../profile'

/**
 * One Lesson's visible Problems (Story 2.3): a read-only, numbered list. Reachable both
 * from the Library and from Home's "Học tiếp" card.
 *
 * Story 3.4: a quiz-sheet Lesson (`is_quiz_sheet`) shows a 📝 "Kiểm tra" indicator and a
 * start button. The Session's mode is decided by the server, so the button only sends the
 * plain Lesson ref.
 */
export default function LessonDetail() {
  const { bookId = '', unitKey = '', lessonKey = '' } = useParams()
  const navigate = useNavigate()
  const problems = useLibraryLesson(bookId, unitKey, lessonKey)
  const profiles = useProfiles()
  const profileId = getCurrentProfileId()
  const list = profiles.data ?? []
  const current = list.find((p) => p.id === profileId) ?? (list.length === 1 ? list[0] : undefined)
  const books = useLibraryBooks(current?.grade ?? 0, current?.id, {
    enabled: current !== undefined,
  })
  const startSession = useStartSession()

  const isQuiz = Boolean(
    books.data
      ?.find((b) => b.book_id === bookId)
      ?.units.find((u) => u.unit_key === unitKey)
      ?.lessons.find((l) => l.lesson_key === lessonKey)?.is_quiz_sheet,
  )

  function handleStartQuiz() {
    if (!current) return
    startSession.mutate(
      {
        profileId: current.id,
        ref: {
          kind: 'lesson',
          book_id: bookId,
          unit_key: unitKey,
          lesson_key: lessonKey,
        },
      },
      { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
    )
  }

  return (
    <main className="home">
      <h1>Bài học</h1>

      {isQuiz && (
        <p className="library-quiz-indicator" data-testid="quiz-indicator">
          📝 {phrase('quiz_indicator')}
        </p>
      )}

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

      {isQuiz && problems.data && problems.data.length > 0 && (
        <button type="button" onClick={handleStartQuiz} disabled={startSession.isPending}>
          {phrase('quiz_start')}
        </button>
      )}
      {startSession.isError && (
        <p role="alert" className="form-error">
          {errorMessage(startSession.error)}
        </p>
      )}

      <p className="parent-link">
        <Link to="/library">Về Sách</Link>
      </p>
    </main>
  )
}
