import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import {
  ApiError,
  cancelRun,
  pauseRun,
  resumeRun,
  startRun,
  type BuildRun,
} from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useCatalogueBooks, useCurrentRun } from '../api/queries'

function usd(value: number): string {
  return `$${value.toFixed(4)}`
}

function pct(done: number, total: number): number {
  return total <= 0 ? 0 : Math.round((done / total) * 100)
}

/** The book/page-range picker shown when no run is active. */
function Picker({ onStarted }: { onStarted: (run: BuildRun) => void }) {
  const books = useCatalogueBooks()
  const [bookId, setBookId] = useState('')
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  // Set once a start attempt comes back 422 SPEND_NOT_CONFIRMED, with the estimate text
  // to show; confirming re-submits the same request with yes_spend true.
  const [confirming, setConfirming] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: (yesSpend: boolean) => startRun(bookId, `${first}-${last || first}`, yesSpend),
    onSuccess: (run) => {
      setConfirming(null)
      onStarted(run)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'SPEND_NOT_CONFIRMED') {
        setConfirming(error.message)
      } else {
        setConfirming(null)
      }
    },
  })

  const canStart = bookId !== '' && first !== ''
  const book = books.data?.find((b) => b.book_id === bookId)

  return (
    <form
      className="parent-form"
      onSubmit={(e) => {
        e.preventDefault()
        start.mutate(false)
      }}
    >
      <label>
        Sách
        <select
          value={bookId}
          onChange={(e) => {
            setBookId(e.target.value)
            setConfirming(null)
          }}
        >
          <option value="">— Chọn sách —</option>
          {books.data?.map((b) => (
            <option key={b.book_id} value={b.book_id}>
              {b.title_vi} ({b.page_count} trang)
            </option>
          ))}
        </select>
      </label>
      <div className="filters">
        <label>
          Từ trang
          <input
            type="number"
            min={1}
            max={book?.page_count}
            value={first}
            onChange={(e) => {
              setFirst(e.target.value)
              setConfirming(null)
            }}
          />
        </label>
        <label>
          Đến trang
          <input
            type="number"
            min={first || 1}
            max={book?.page_count}
            value={last}
            onChange={(e) => {
              setLast(e.target.value)
              setConfirming(null)
            }}
          />
        </label>
      </div>
      {confirming && (
        <div role="alert" className="run-confirm">
          <p>{confirming}</p>
          <button type="button" onClick={() => start.mutate(true)} disabled={start.isPending}>
            Xác nhận &amp; chạy
          </button>
        </div>
      )}
      {!confirming && (
        <button type="submit" disabled={!canStart || start.isPending}>
          Chạy thử
        </button>
      )}
      {start.isError && !confirming && (
        <p role="alert" className="form-error">
          {errorMessage(start.error)}
        </p>
      )}
    </form>
  )
}

const STOPPABLE = new Set(['running', 'pausing'])

/** The live progress view of an active (or just-finished) run. */
function Progress({ run, onDismiss }: { run: BuildRun; onDismiss: () => void }) {
  const queryClient = useQueryClient()
  const onUpdate = (data: BuildRun) => queryClient.setQueryData(queryKeys.currentRun, data)
  const pause = useMutation({ mutationFn: pauseRun, onSuccess: onUpdate })
  const resume = useMutation({ mutationFn: resumeRun, onSuccess: onUpdate })
  const cancel = useMutation({ mutationFn: cancelRun, onSuccess: onUpdate })
  const busy = pause.isPending || resume.isPending || cancel.isPending
  const error = pause.error ?? resume.error ?? cancel.error

  return (
    <div className="run-card" aria-live="polite">
      <p>
        {run.book_id}: trang {run.first_page}-{run.last_page}
      </p>
      <div
        className="run-progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct(run.pages_done, run.pages_total)}
      >
        <div className="run-progress-bar" style={{ width: `${pct(run.pages_done, run.pages_total)}%` }} />
      </div>
      <p>
        {run.activity} ({run.pages_done}/{run.pages_total} trang) · Chi phí: {usd(run.cost_usd)}
      </p>
      {run.status === 'pausing' && (
        <p className="hint">Có thể mất một chút thời gian: trang đang chạy sẽ được xong trước.</p>
      )}
      {run.stale && run.status === 'running' && (
        <p role="note">
          Không thấy tiến triển trong vài phút qua; máy chủ có thể đã khởi động lại. Có thể bấm
          Tiếp tục để chạy tiếp.
        </p>
      )}
      {run.failed_pages.length > 0 && (
        <div>
          <p>{run.failed_pages.length} trang lỗi:</p>
          <ul>
            {run.failed_pages.map((f, i) => (
              <li key={i}>
                Trang {f.page} ({f.stage}): {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.error && (
        <p role="alert" className="form-error">
          {run.error}
        </p>
      )}
      <p className="run-actions">
        {run.status === 'running' && (
          <button type="button" disabled={busy} onClick={() => pause.mutate(run.id)}>
            Tạm dừng
          </button>
        )}
        {run.status === 'pausing' && (
          <button
            type="button"
            disabled
            title="Đang chờ trang hiện tại chạy xong trước khi dừng."
          >
            Đang dừng…
          </button>
        )}
        {(run.status === 'paused' || (run.status === 'running' && run.stale)) && (
          <button type="button" disabled={busy} onClick={() => resume.mutate(run.id)}>
            Tiếp tục
          </button>
        )}
        {STOPPABLE.has(run.status) && (
          <button type="button" disabled={busy} onClick={() => cancel.mutate(run.id)}>
            Hủy
          </button>
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {errorMessage(error)}
        </p>
      )}
      {!STOPPABLE.has(run.status) && (
        <p>
          <button type="button" className="link-button" onClick={onDismiss}>
            Chọn sách và trang khác
          </button>
        </p>
      )}
    </div>
  )
}

/** "Chạy thử" (trial run) screen: pick a book and page range, watch it run, pause/resume.
 * On mount, an already-active (or just-finished) run is shown instead of the picker. */
export default function ExtractionPage() {
  const queryClient = useQueryClient()
  const current = useCurrentRun()
  const [dismissed, setDismissed] = useState(false)

  if (current.isPending) return <p>Đang tải…</p>
  if (current.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(current.error)}
      </p>
    )
  }

  const run = current.data
  const showPicker = dismissed || run === null

  return (
    <main className="parent">
      <h1>Chạy thử (pilot)</h1>
      <p>
        <Link to="/parent">← Khu vực phụ huynh</Link>
      </p>
      {showPicker ? (
        <Picker
          onStarted={(started) => {
            queryClient.setQueryData(queryKeys.currentRun, started)
            setDismissed(false)
          }}
        />
      ) : (
        run && <Progress run={run} onDismiss={() => setDismissed(true)} />
      )}
    </main>
  )
}
