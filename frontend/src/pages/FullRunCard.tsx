import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import {
  cancelRun,
  pauseRun,
  planFullRun,
  resumeRun,
  startFullRun,
  type FullPlan,
  type FullRun,
} from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useCurrentFullRun } from '../api/queries'

function usd(value: number): string {
  return `$${value.toFixed(2)}`
}

const ACTIVE = new Set(['running', 'pausing', 'paused'])

const STOP_TEXT: Record<string, string> = {
  budget:
    'Đã dừng vì hết mức chi tối đa. Các trang đang chạy đã xong. Đặt mức cao hơn rồi chạy lại để tiếp tục từ chỗ dừng.',
  checkpoint:
    'Đã dừng ở điểm kiểm tra. Xem lại kết quả (Kiểm tra ngẫu nhiên, duyệt lại chạy toàn bộ nếu cần) rồi bấm Tiếp tục.',
  gate: 'Đã dừng vì chưa còn được duyệt chạy toàn bộ. Duyệt lại ở thẻ “Duyệt chạy toàn bộ”, rồi chạy lại.',
}

/** The live view of a full-corpus run: one row per Book, cost against the cap, failures. */
function FullProgress({ run }: { run: FullRun }) {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.currentFullRun })
    void queryClient.invalidateQueries({ queryKey: queryKeys.currentRun })
  }
  const pause = useMutation({ mutationFn: pauseRun, onSuccess: refresh })
  const resume = useMutation({ mutationFn: resumeRun, onSuccess: refresh })
  const cancel = useMutation({ mutationFn: cancelRun, onSuccess: refresh })
  const busy = pause.isPending || resume.isPending || cancel.isPending
  const error = pause.error ?? resume.error ?? cancel.error
  const last = run.books[run.books.length - 1]

  return (
    <div className="run-card" aria-live="polite">
      <p>
        Chi phí: {usd(run.spent_usd)} / mức tối đa {usd(run.max_total_usd)}
        {last ? ` · ${last.activity}` : ''}
      </p>
      <table>
        <thead>
          <tr>
            <th>Sách</th>
            <th>Trang</th>
            <th>Chi phí</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {run.books.map((b) => (
            <tr key={b.id}>
              <td>{b.book_id}</td>
              <td>
                {b.pages_done}/{b.pages_total}
                {b.failed_pages.length > 0 ? ` (${b.failed_pages.length} lỗi)` : ''}
              </td>
              <td>{usd(b.cost_usd)}</td>
              <td>{b.activity || b.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {run.stop_reason && <p role="note">{STOP_TEXT[run.stop_reason]}</p>}
      {run.unstarted.length > 0 && (
        <div>
          <p>Chưa chạy:</p>
          <ul>
            {run.unstarted.map((u) => (
              <li key={u.book_id}>
                {u.book_id}: {u.pages} trang
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.failed_pages.length > 0 && (
        <div>
          <p>{run.failed_pages.length} trang lỗi (chạy lại để thử lại):</p>
          <ul>
            {run.failed_pages.map((f, i) => (
              <li key={i}>
                {f.book_id} trang {f.page} ({f.stage}): {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.status === 'done' && (
        <p>
          Xong. Hãy kiểm tra 100 bài ngẫu nhiên (mục tiêu ≥ 98% đáp án đúng):{' '}
          <Link to="/parent/review?tab=spot-check">Kiểm tra ngẫu nhiên</Link>
        </p>
      )}
      <p className="run-actions">
        {run.status === 'running' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => pause.mutate(run.current_run_id)}
          >
            Tạm dừng
          </button>
        )}
        {run.status === 'pausing' && (
          <button type="button" disabled>
            Đang dừng…
          </button>
        )}
        {run.status === 'paused' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => resume.mutate(run.current_run_id)}
          >
            Tiếp tục
          </button>
        )}
        {ACTIVE.has(run.status) && (
          <button
            type="button"
            disabled={busy}
            onClick={() => cancel.mutate(run.current_run_id)}
          >
            Hủy
          </button>
        )}
      </p>
      {error && (
        <p role="alert" className="form-error">
          {errorMessage(error)}
        </p>
      )}
    </div>
  )
}

/** Plan table, estimate against the cap, and the confirm step. */
function StartForm({ latest }: { latest: FullRun | null | undefined }) {
  const queryClient = useQueryClient()
  const [plan, setPlan] = useState<FullPlan | null>(null)
  const [cap, setCap] = useState('')
  const [confirming, setConfirming] = useState(false)
  const capValue = Number(cap)
  const capValid = cap !== '' && Number.isFinite(capValue) && capValue > 0

  const load = useMutation({ mutationFn: () => planFullRun(), onSuccess: setPlan })
  const start = useMutation({
    mutationFn: () => startFullRun(capValue, true),
    onSuccess: (run) => {
      setConfirming(false)
      queryClient.setQueryData(queryKeys.currentFullRun, run)
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentRun })
    },
  })
  const resumable =
    latest && (latest.status === 'stopped_checkpoint' || latest.status === 'stopped_budget')

  return (
    <div>
      <button type="button" onClick={() => load.mutate()} disabled={load.isPending}>
        {resumable ? 'Xem kế hoạch để tiếp tục' : 'Xem kế hoạch chạy toàn bộ'}
      </button>
      {load.isError && (
        <p role="note" className="form-error">
          {errorMessage(load.error)}
        </p>
      )}
      {plan && (
        <div>
          {!plan.approved && (
            <p role="note" className="form-error">
              Chưa được duyệt chạy toàn bộ. Hãy xem báo cáo chạy thử và duyệt trước.
            </p>
          )}
          <table>
            <thead>
              <tr>
                <th>Sách</th>
                <th>Trang gọi Claude</th>
                <th>Ghi chú</th>
              </tr>
            </thead>
            <tbody>
              {plan.books.map((b) => (
                <tr key={b.book_id}>
                  <td>{b.title_vi}</td>
                  <td>
                    {b.pages_to_call}/{b.pages_in_scope}
                  </td>
                  <td>
                    {b.skipped ??
                      (b.probe ? 'Chạy thử đầu lớp, rồi dừng để duyệt lại' : '')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Ước tính: {usd(plan.estimate_usd)} (tối đa {usd(plan.worst_case_usd)}) cho{' '}
            {plan.pages_to_call} trang.
          </p>
          <form
            className="parent-form"
            onSubmit={(e) => {
              e.preventDefault()
              setConfirming(true)
            }}
          >
            <label>
              Mức chi tối đa (USD)
              <input
                type="number"
                min={0}
                step="any"
                value={cap}
                onChange={(e) => {
                  setCap(e.target.value)
                  setConfirming(false)
                }}
              />
            </label>
            {!confirming && (
              <button type="submit" disabled={!plan.approved || !capValid}>
                Chạy toàn bộ
              </button>
            )}
          </form>
          {confirming && (
            <div role="alert" className="run-confirm">
              <p>
                Lệnh này sẽ gọi Claude và tốn tiền: ước tính {usd(plan.estimate_usd)}, dừng khi đã
                chi {usd(capValue)}. Đồng ý?
              </p>
              <button type="button" onClick={() => start.mutate()} disabled={start.isPending}>
                Xác nhận &amp; chạy toàn bộ
              </button>
            </div>
          )}
          {start.isError && (
            <p role="alert" className="form-error">
              {errorMessage(start.error)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/** "Chạy toàn bộ": the whole corpus, Book by Book (Story 6.2). Only after the go/no-go
 * approval; the spend cap is always chosen by the parent. */
export default function FullRunCard() {
  const current = useCurrentFullRun()
  const run = current.data
  const active = run != null && ACTIVE.has(run.status)

  return (
    <section aria-labelledby="full-run-title">
      <h2 id="full-run-title">Chạy toàn bộ</h2>
      <p>
        Chạy tất cả các sách theo thứ tự lớp 1 đến 5. Cần duyệt chạy toàn bộ trước; luôn phải đặt
        mức chi tối đa. Dừng ở các điểm kiểm tra để xem lại.
      </p>
      {run && <FullProgress run={run} />}
      {!current.isPending && !active && <StartForm latest={run} />}
    </section>
  )
}
