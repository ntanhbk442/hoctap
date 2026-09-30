import { useState } from 'react'
import { Link, Navigate } from 'react-router'
import { authRedirect, errorMessage } from '../api/errors'
import {
  useAssignments,
  useCreateAssignment,
  useDeleteAssignment,
  useLibraryBooks,
  useParentSession,
  useProfiles,
} from '../api/queries'
import { printLink } from '../print/printLink'
import { statusText, tomorrowLocal } from './assignmentUtils'

function Picker({ profileId, grade }: { profileId: string; grade: number }) {
  const books = useLibraryBooks(grade, profileId)
  const create = useCreateAssignment()
  const [bookId, setBookId] = useState('')
  const [unitKey, setUnitKey] = useState('')
  const [lessonKey, setLessonKey] = useState('')
  const [date, setDate] = useState(() => tomorrowLocal())

  const list = books.data ?? []
  const book = list.find((b) => b.book_id === bookId)
  const unit = book?.units.find((u) => u.unit_key === unitKey)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          {
            profile_id: profileId,
            book_id: bookId,
            unit_key: unitKey,
            lesson_key: lessonKey,
            assigned_date: date,
          },
          { onSuccess: () => setLessonKey('') },
        )
      }}
    >
      {books.isError && (
        <p role="alert" className="form-error">
          {errorMessage(books.error)}
        </p>
      )}
      <label>
        Sách
        <select
          value={bookId}
          onChange={(e) => {
            setBookId(e.target.value)
            setUnitKey('')
            setLessonKey('')
          }}
        >
          <option value="">Chọn sách</option>
          {list.map((b) => (
            <option key={b.book_id} value={b.book_id}>
              {b.title_vi}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tuần / bài
        <select
          value={unitKey}
          disabled={!book}
          onChange={(e) => {
            setUnitKey(e.target.value)
            setLessonKey('')
          }}
        >
          <option value="">Chọn tuần / bài</option>
          {book?.units.map((u) => (
            <option key={u.unit_key} value={u.unit_key}>
              {`${u.label} ${u.title}`.trim() || u.unit_key}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tiết
        <select value={lessonKey} disabled={!unit} onChange={(e) => setLessonKey(e.target.value)}>
          <option value="">Chọn tiết</option>
          {unit?.lessons
            .filter((l) => l.problem_count > 0)
            .map((l) => (
              <option key={l.lesson_key} value={l.lesson_key}>
                {`${l.label} ${l.title}`.trim() || l.lesson_key} ({l.problem_count} bài)
              </option>
            ))}
        </select>
      </label>
      <label>
        Ngày
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      </label>
      {create.isError && (
        <p role="alert" className="form-error">
          {errorMessage(create.error)}
        </p>
      )}
      <button type="submit" disabled={!lessonKey || !date || create.isPending}>
        Giao bài
      </button>
    </form>
  )
}

function AssignmentList({ profileId }: { profileId: string }) {
  const assignments = useAssignments(profileId)
  const remove = useDeleteAssignment()
  const list = assignments.data ?? []
  return (
    <section aria-labelledby="assign-list">
      <h2 id="assign-list">Bài đã giao</h2>
      {assignments.isPending && <p>Đang tải…</p>}
      {assignments.isError && (
        <p role="alert" className="form-error">
          {errorMessage(assignments.error)}
        </p>
      )}
      {assignments.isSuccess && list.length === 0 && <p>Chưa giao bài nào.</p>}
      {remove.isError && (
        <p role="alert" className="form-error">
          {errorMessage(remove.error)}
        </p>
      )}
      <ul>
        {list.map((a) => (
          <li key={a.id} data-testid={`assignment-${a.id}`}>
            {a.assigned_date} · {a.book_title_vi} · {a.unit_label} {a.lesson_label} —{' '}
            <strong>{statusText(a)}</strong>
            {a.carried_over && ' (Hôm qua)'}{' '}
            <Link
              to={printLink({ bookId: a.book_id, unitKey: a.unit_key, lessonKey: a.lesson_key })}
            >
              In phiếu
            </Link>{' '}
            {a.status !== 'done' && (
              <button type="button" onClick={() => remove.mutate(a.id)} disabled={remove.isPending}>
                Xóa
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Story 4.3: the Parent assigns a Lesson to a date and sees/deletes what was assigned. */
export default function Assignments() {
  const session = useParentSession()
  const profiles = useProfiles()
  const [chosen, setChosen] = useState('')
  const list = profiles.data ?? []
  const profile = list.find((p) => p.id === chosen) ?? list[0]

  if (session.isError) {
    const target = authRedirect(session.error)
    if (target) return <Navigate to={target} replace />
  }

  return (
    <main className="parent assignments">
      <h1>Giao bài</h1>
      <p>
        <Link to="/parent">Về khu vực phụ huynh</Link>
      </p>
      {profiles.isPending && <p>Đang tải…</p>}
      {profiles.isError && (
        <p role="alert" className="form-error">
          {errorMessage(profiles.error)}
        </p>
      )}
      {profile && (
        <>
          <label>
            Bé
            <select value={profile.id} onChange={(e) => setChosen(e.target.value)}>
              {list.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <Picker key={profile.id} profileId={profile.id} grade={profile.grade} />
          <AssignmentList profileId={profile.id} />
        </>
      )}
    </main>
  )
}
