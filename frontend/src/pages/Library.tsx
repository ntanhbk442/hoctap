import { Link, Navigate, useNavigate } from 'react-router'
import { errorMessage } from '../api/errors'
import { useLibraryBooks, useProfiles } from '../api/queries'
import { getCurrentProfileId } from '../profile'

/**
 * The Library (Story 2.3): Grade -> Book -> Unit -> Lesson, for the child's own Grade only
 * (a Grade switcher is out of scope, see `deferred-work.md`). Both Editions of a Grade show
 * as separate Books. Each Lesson shows "0/n ✓" (n = the visible-Problem count) -- the "0" is
 * honest, not a placeholder; Story 2.4 makes it a real progress count.
 */
export default function Library() {
  const navigate = useNavigate()
  const profiles = useProfiles()
  const profileId = getCurrentProfileId()
  const list = profiles.data ?? []
  const current = list.find((p) => p.id === profileId) ?? (list.length === 1 ? list[0] : undefined)
  const books = useLibraryBooks(current?.grade ?? 0, current?.id, { enabled: current !== undefined })

  if (profiles.isPending) {
    return (
      <main className="home">
        <p>Đang tải…</p>
      </main>
    )
  }

  if (profiles.isError) {
    return (
      <main className="home">
        <h1>Sách</h1>
        <p role="alert" className="form-error">
          {errorMessage(profiles.error)}
        </p>
        <button type="button" onClick={() => void profiles.refetch()}>
          Thử lại
        </button>
      </main>
    )
  }

  // Zero Profiles at all (an inconsistent but reachable `setup_required: false` state,
  // e.g. the sole Profile deleted from the Parent Area post-setup) has no picker to send
  // them through -- go straight to Setup instead of bouncing through a dead-end Home.
  if (list.length === 0) return <Navigate to="/setup" replace />

  // No current Profile resolvable (e.g. direct navigation with 2+ Profiles and none
  // picked yet this session): send them through Home's picker first.
  if (!current) return <Navigate to="/" replace />

  return (
    <main className="home library">
      <h1>Sách</h1>

      {books.isPending && <p>Đang tải…</p>}

      {books.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(books.error)}
          </p>
          <button type="button" onClick={() => void books.refetch()}>
            Thử lại
          </button>
        </>
      )}

      {books.data?.length === 0 && (
        <p className="home-empty">Chưa có sách nào cho lớp {current.grade}.</p>
      )}

      {books.data?.map((book) => (
        <section key={book.book_id} className="library-book">
          <h2>{book.title_vi}</h2>
          {book.units.map((unit) => (
            <div key={unit.unit_key} className="library-unit">
              {(unit.label || unit.title) && <h3>{unit.label || unit.title}</h3>}
              <ul className="library-lesson-list">
                {unit.lessons.map((lesson) => (
                  <li key={lesson.lesson_key}>
                    <button
                      type="button"
                      className="library-lesson-row"
                      onClick={() =>
                        navigate(`/library/${book.book_id}/${unit.unit_key}/${lesson.lesson_key}`)
                      }
                    >
                      <span>{lesson.label || lesson.title || lesson.lesson_key}</span>
                      <span className="library-lesson-progress">
                        {lesson.attempted}/{lesson.problem_count} ✓
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}

      <p className="parent-link">
        <Link to="/">Về trang chủ</Link>
      </p>
    </main>
  )
}
