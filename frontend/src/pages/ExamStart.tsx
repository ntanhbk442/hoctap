import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import type { ExamScopeIn } from '../api/client'
import { errorMessage } from '../api/errors'
import { useLibraryBooks, useLibraryConcepts, useProfiles, useStartSession } from '../api/queries'
import { phrase } from '../audio/phrases'
import { getCurrentProfileId } from '../profile'

type ExamScopeKind = ExamScopeIn['kind']

/**
 * Story 8.1: the child's on-demand exam picker from the Library -- the SAME scope/count/
 * time_limit_s shape a parent's Assignment picker uses (`Assignments.tsx`'s `ExamPicker`),
 * per Anh's explicit call (spec-8-1's Design Notes): one picker, not a simplified child
 * version and a full parent one. Only reachable when the Profile's `exams_enabled` is on
 * (Library's own entry point is itself gated on it, and this route re-checks it too, so a
 * direct URL visit can't bypass the gate client-side -- the server enforces it either way).
 */
export default function ExamStart() {
  const navigate = useNavigate()
  const profiles = useProfiles()
  const list = profiles.data ?? []
  const wantedId = getCurrentProfileId()
  const current = list.find((p) => p.id === wantedId) ?? (list.length === 1 ? list[0] : undefined)
  const profileId = current?.id ?? ''
  const start = useStartSession()

  const [scopeKind, setScopeKind] = useState<ExamScopeKind>('grade')
  const [bookId, setBookId] = useState('')
  const [unitKey, setUnitKey] = useState('')
  const [conceptIds, setConceptIds] = useState<string[]>([])
  const [count, setCount] = useState(10)
  const [minutes, setMinutes] = useState(15)

  const books = useLibraryBooks(current?.grade ?? 0, current?.id, { enabled: !!current })
  const concepts = useLibraryConcepts(current?.grade ?? 0, { enabled: !!current })
  const bookList = books.data ?? []
  const book = bookList.find((b) => b.book_id === bookId)

  if (profiles.isPending) {
    return (
      <main className="home">
        <p>Đang tải…</p>
      </main>
    )
  }
  if (!current) return <Navigate to="/" replace />
  // Story 8.1: `exams_enabled` gates both entry points -- re-checked here so a direct URL
  // visit (not just Library's hidden link) can't reach the picker client-side either; the
  // server refuses the actual start (`EXAMS_DISABLED`) regardless.
  if (!current.exams_enabled) return <Navigate to="/library" replace />

  function scope(): ExamScopeIn | null {
    if (scopeKind === 'grade') return { kind: 'grade' }
    if (scopeKind === 'book_unit') {
      return bookId ? { kind: 'book_unit', book_id: bookId, unit_keys: unitKey ? [unitKey] : null } : null
    }
    return conceptIds.length > 0 ? { kind: 'concept', concept_ids: conceptIds } : null
  }

  const resolvedScope = scope()
  const canSubmit = resolvedScope !== null && count > 0 && minutes > 0

  return (
    <main className="home">
      <h1>{phrase('exam_picker_title')}</h1>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!resolvedScope) return
          start.mutate(
            {
              profileId,
              ref: { kind: 'exam', scope: resolvedScope, count, time_limit_s: minutes * 60 },
              mode: 'exam',
            },
            { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
          )
        }}
      >
        <fieldset>
          <legend>Phạm vi đề</legend>
          <label>
            <input
              type="radio"
              name="exam-scope-kind"
              checked={scopeKind === 'grade'}
              onChange={() => setScopeKind('grade')}
            />
            {phrase('exam_picker_scope_grade')}
          </label>
          <label>
            <input
              type="radio"
              name="exam-scope-kind"
              checked={scopeKind === 'book_unit'}
              onChange={() => setScopeKind('book_unit')}
            />
            {phrase('exam_picker_scope_book_unit')}
          </label>
          <label>
            <input
              type="radio"
              name="exam-scope-kind"
              checked={scopeKind === 'concept'}
              onChange={() => setScopeKind('concept')}
            />
            {phrase('exam_picker_scope_concept')}
          </label>
        </fieldset>

        {scopeKind === 'book_unit' && (
          <>
            <label>
              Sách
              <select
                value={bookId}
                onChange={(e) => {
                  setBookId(e.target.value)
                  setUnitKey('')
                }}
              >
                <option value="">Chọn sách</option>
                {bookList.map((b) => (
                  <option key={b.book_id} value={b.book_id}>
                    {b.title_vi}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Tuần / bài
              <select value={unitKey} disabled={!book} onChange={(e) => setUnitKey(e.target.value)}>
                <option value="">Cả sách</option>
                {book?.units.map((u) => (
                  <option key={u.unit_key} value={u.unit_key}>
                    {`${u.label} ${u.title}`.trim() || u.unit_key}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {scopeKind === 'concept' && (
          <label>
            Khái niệm (chọn một hoặc nhiều)
            <select
              multiple
              value={conceptIds}
              onChange={(e) =>
                setConceptIds(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {(concepts.data ?? []).map((c) => (
                <option key={c.concept_id} value={c.concept_id}>
                  {c.name_vi}
                </option>
              ))}
            </select>
          </label>
        )}

        <label>
          {phrase('exam_picker_count')}
          <input
            type="number"
            min={1}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </label>
        <label>
          {phrase('exam_picker_time_limit')}
          <input
            type="number"
            min={1}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </label>

        {start.isError && (
          <p role="alert" className="form-error">
            {errorMessage(start.error)}
          </p>
        )}

        <button type="submit" disabled={!canSubmit || start.isPending}>
          {phrase('exam_start')}
        </button>
      </form>

      <p className="parent-link">
        <Link to="/library">Về Sách</Link>
      </p>
    </main>
  )
}
