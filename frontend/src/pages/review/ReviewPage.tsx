import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router'
import { errorMessage } from '../../api/errors'
import { useReviewBooks, useReviewProblems, useReviewQueue } from '../../api/queries'
import ConceptsTab from './ConceptsTab'
import ProblemList from './ProblemList'
import SpotCheckTab from './SpotCheckTab'

const TABS = [
  { id: 'queue', label: 'Cần duyệt' },
  { id: 'all', label: 'Tất cả' },
  { id: 'spot-check', label: 'Kiểm tra ngẫu nhiên' },
  { id: 'concepts', label: 'Khái niệm' },
] as const

type TabId = (typeof TABS)[number]['id']

function isTab(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value)
}

function QueueTab() {
  const queue = useReviewQueue()
  if (queue.isPending) return <p>Đang tải…</p>
  if (queue.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(queue.error)}
      </p>
    )
  }
  if (queue.data.length === 0) return <p>Không có bài cần duyệt.</p>
  return (
    <>
      <p>{queue.data.length} bài cần duyệt</p>
      <ProblemList items={queue.data} />
    </>
  )
}

function AllTab() {
  // Filters and page live in the URL, so a reload or "back" keeps them.
  const [params, setParams] = useSearchParams()
  const bookId = params.get('book') ?? ''
  const unitKey = params.get('unit') ?? ''
  const lessonKey = params.get('lesson') ?? ''
  const noConcepts = params.get('no_concepts') === '1'
  const page = Math.max(1, Number(params.get('page')) || 1)
  const books = useReviewBooks()
  const problems = useReviewProblems({
    bookId: bookId || undefined,
    unitKey: unitKey || undefined,
    lessonKey: lessonKey || undefined,
    noConcepts: noConcepts || undefined,
    page,
  })
  const total = problems.data?.total
  const pageSize = problems.data?.page_size ?? 50
  const pages = total === undefined ? 1 : Math.max(1, Math.ceil(total / pageSize))

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  // The list shrank (e.g. Problems retired): go to the last page that exists.
  const outOfRange = !problems.isPlaceholderData && total !== undefined && page > pages
  useEffect(() => {
    if (outOfRange) update({ page: pages > 1 ? String(pages) : '' })
  })

  const book = books.data?.find((b) => b.book_id === bookId)
  const unit = book?.units.find((u) => u.unit_key === unitKey)

  return (
    <>
      <div className="filters">
        <label className="inline-field">
          Sách{' '}
          <select
            value={bookId}
            onChange={(e) => update({ book: e.target.value, unit: '', lesson: '', page: '' })}
          >
            <option value="">Tất cả sách</option>
            {books.data?.map((b) => (
              <option key={b.book_id} value={b.book_id}>
                {b.title_vi} ({b.problem_count})
              </option>
            ))}
          </select>
        </label>
        {book && (
          <label className="inline-field">
            Tuần/Chương{' '}
            <select
              value={unitKey}
              onChange={(e) => update({ unit: e.target.value, lesson: '', page: '' })}
            >
              <option value="">Tất cả</option>
              {book.units.map((u) => (
                <option key={u.unit_key} value={u.unit_key}>
                  {u.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {unit && (
          <label className="inline-field">
            Bài học{' '}
            <select value={lessonKey} onChange={(e) => update({ lesson: e.target.value, page: '' })}>
              <option value="">Tất cả</option>
              {unit.lessons.map((l) => (
                <option key={l.lesson_key} value={l.lesson_key}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="inline-field">
          <input
            type="checkbox"
            checked={noConcepts}
            onChange={(e) => update({ no_concepts: e.target.checked ? '1' : '', page: '' })}
          />{' '}
          Chưa gắn khái niệm
        </label>
      </div>
      {books.isError && (
        <p role="alert" className="form-error">
          Không tải được danh sách sách: {errorMessage(books.error)}
        </p>
      )}
      {problems.isPending && <p>Đang tải…</p>}
      {problems.isError && (
        <p role="alert" className="form-error">
          {errorMessage(problems.error)}
        </p>
      )}
      {problems.isSuccess && (
        <>
          <p>{problems.data.total} bài</p>
          <ProblemList items={problems.data.items} />
          {pages > 1 && (
            <nav className="pager" aria-label="Trang">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => update({ page: page - 1 > 1 ? String(page - 1) : '' })}
              >
                Trang trước
              </button>
              <span>
                Trang {page}/{pages}
              </span>
              <button
                type="button"
                disabled={page >= pages || problems.isPlaceholderData}
                onClick={() => update({ page: String(page + 1) })}
              >
                Trang sau
              </button>
            </nav>
          )}
        </>
      )}
    </>
  )
}

export default function ReviewPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: TabId = isTab(raw) ? raw : 'queue'

  return (
    <main className="parent parent-wide">
      <p>
        <Link to="/parent">Khu vực phụ huynh</Link>
      </p>
      <h1>Duyệt nội dung</h1>
      <div role="tablist" className="tabs" aria-label="Duyệt nội dung">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              if (t.id !== tab) setParams(t.id === 'queue' ? {} : { tab: t.id }, { replace: true })
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <section role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label}>
        {tab === 'queue' && <QueueTab />}
        {tab === 'all' && <AllTab />}
        {tab === 'spot-check' && <SpotCheckTab />}
        {tab === 'concepts' && <ConceptsTab />}
      </section>
    </main>
  )
}
