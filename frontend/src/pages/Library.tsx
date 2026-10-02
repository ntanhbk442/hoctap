import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import { errorMessage } from '../api/errors'
import { useLibraryBooks, useLibraryConcepts, useProfiles } from '../api/queries'
import { phrase } from '../audio/phrases'
import ConceptGuide from '../components/ConceptGuide/ConceptGuide'
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
  const [tab, setTab] = useState<'books' | 'concepts'>('books')
  const [openConcept, setOpenConcept] = useState<string | null>(null)
  const books = useLibraryBooks(current?.grade ?? 0, current?.id, {
    enabled: current !== undefined,
  })
  const concepts = useLibraryConcepts(current?.grade ?? 0, {
    enabled: current !== undefined && tab === 'concepts',
  })

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

      {/* Story 8.1: the on-demand exam entry point -- gated on `exams_enabled` (a parent
       * must turn it on per Child Profile; off by default), never shown at all otherwise. */}
      {current.exams_enabled && (
        <p>
          <Link to="/exam/new" className="library-exam-entry">
            📝 {phrase('exam_entry_point')}
          </Link>
        </p>
      )}

      <div className="library-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'books'}
          onClick={() => setTab('books')}
        >
          Sách
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'concepts'}
          onClick={() => setTab('concepts')}
        >
          Khái niệm
        </button>
      </div>

      {tab === 'concepts' && (
        <>
          {concepts.isPending && <p>Đang tải…</p>}
          {concepts.isError && (
            <>
              <p role="alert" className="form-error">
                {errorMessage(concepts.error)}
              </p>
              <button type="button" onClick={() => void concepts.refetch()}>
                Thử lại
              </button>
            </>
          )}
          {concepts.data?.length === 0 && (
            <p className="home-empty">Chưa có khái niệm nào cho lớp {current.grade}.</p>
          )}
          <ul className="library-lesson-list">
            {concepts.data?.map((c) => (
              <li key={c.concept_id}>
                <button
                  type="button"
                  className="library-lesson-row"
                  onClick={() => setOpenConcept(c.concept_id)}
                >
                  <span>📖 {c.name_vi}</span>
                  <span className="library-lesson-progress">{c.problem_count} bài</span>
                </button>
              </li>
            ))}
          </ul>
          {openConcept && (
            <ConceptGuide
              key={openConcept}
              conceptIds={[openConcept]}
              grade={current.grade}
              profileId={current.id}
              onClose={() => setOpenConcept(null)}
            />
          )}
        </>
      )}

      {tab === 'books' && books.isPending && <p>Đang tải…</p>}

      {tab === 'books' && books.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(books.error)}
          </p>
          <button type="button" onClick={() => void books.refetch()}>
            Thử lại
          </button>
        </>
      )}

      {tab === 'books' && books.data?.length === 0 && (
        <p className="home-empty">Chưa có sách nào cho lớp {current.grade}.</p>
      )}

      {tab === 'books' &&
        books.data?.map((book) => (
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
                      <span>
                        {lesson.label || lesson.title || lesson.lesson_key}
                        {lesson.is_quiz_sheet && (
                          <span className="library-quiz-indicator" data-testid="quiz-indicator">
                            {' '}
                            📝 {phrase('quiz_indicator')}
                          </span>
                        )}
                      </span>
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
