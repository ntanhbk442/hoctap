import { useState } from 'react'
import { Link } from 'react-router'
import { useConcepts, useLibraryBooks, useProfiles } from '../api/queries'
import { printLink } from '../print/printLink'

/**
 * Story 7.1: "In phiếu" entry points of the Parent Area. A Lesson sheet needs a Lesson; a
 * Concept sheet also needs the child (the set is unsolved-first for that profile). Errors
 * here stay quiet: the picker is a convenience, the print page reports real failures.
 */
export default function PrintPicker() {
  const profiles = useProfiles()
  const concepts = useConcepts()
  const [chosen, setChosen] = useState('')
  const [bookId, setBookId] = useState('')
  const [unitKey, setUnitKey] = useState('')
  const [lessonKey, setLessonKey] = useState('')
  const [conceptId, setConceptId] = useState('')

  const list = profiles.data ?? []
  const profile = list.find((p) => p.id === chosen) ?? list[0]
  const books = useLibraryBooks(profile?.grade ?? 1, profile?.id, { enabled: !!profile })
  const book = books.data?.find((b) => b.book_id === bookId)
  const unit = book?.units.find((u) => u.unit_key === unitKey)
  const conceptList = (concepts.data?.concepts ?? []).filter((c) => c.problem_count > 0)

  if (!profile) return <p>Cần có hồ sơ của bé để in phiếu.</p>
  return (
    <div className="print-picker">
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
      <fieldset>
        <legend>Theo tiết học</legend>
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
            {(books.data ?? []).map((b) => (
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
                  {`${l.label} ${l.title}`.trim() || l.lesson_key}
                </option>
              ))}
          </select>
        </label>
        {lessonKey ? (
          <Link to={printLink({ bookId, unitKey, lessonKey })}>In phiếu tiết học</Link>
        ) : (
          <span aria-disabled="true">In phiếu tiết học</span>
        )}
      </fieldset>
      <fieldset>
        <legend>Theo khái niệm</legend>
        <label>
          Khái niệm
          <select value={conceptId} onChange={(e) => setConceptId(e.target.value)}>
            <option value="">Chọn khái niệm</option>
            {conceptList.map((c) => (
              <option key={c.concept_id} value={c.concept_id}>
                {c.name_vi}
              </option>
            ))}
          </select>
        </label>
        {conceptId ? (
          <Link to={printLink({ conceptId, profileId: profile.id })}>In phiếu khái niệm</Link>
        ) : (
          <span aria-disabled="true">In phiếu khái niệm</span>
        )}
      </fieldset>
    </div>
  )
}
