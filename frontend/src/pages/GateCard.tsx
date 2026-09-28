import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ApiError, approveGate, revokeGate, type GateReport } from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useGate } from '../api/queries'

// The same texts as `builder.gate.MSG_SAMPLE_OUTDATED` / `MSG_NOT_ENOUGH_PROBLEMS`.
const MSG_SAMPLE_OUTDATED =
  'Mẫu kiểm tra được rút trước khi có trang chạy thử mới — cần rút mẫu mới.'
const MSG_NOT_ENOUGH_PROBLEMS = 'Chưa đủ bài để đánh giá — hãy chạy thử thêm trang.'

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

function usd(value: number): string {
  return `$${value.toFixed(2)}`
}

function Check({ passed, children }: { passed: boolean; children: ReactNode }) {
  return (
    <li className={passed ? 'check-pass' : 'check-fail'}>
      <span className="check-mark">{passed ? '✓ Đạt' : '✗ Chưa đạt'}</span> · {children}
    </li>
  )
}

function Report({ report }: { report: GateReport }) {
  const { fallback: fb, accuracy: acc, cost } = report
  const counted = acc.correct + acc.wrong
  return (
    <>
      <p>
        {report.pilot_pages} trang chạy thử (
        {report.books.map((b) => `${b.book_id}: ${b.pilot_pages}`).join(', ')}) ·{' '}
        {report.pilot_problems} bài
      </p>
      <ul className="gate-checks" aria-label="Tiêu chí">
        <Check passed={fb.passed}>
          Bài dạng dự phòng (fallback): {pct(fb.value)} ({fb.with_fallback}/{fb.problems}), tối đa{' '}
          {pct(fb.threshold)}
        </Check>
        <Check passed={acc.passed}>
          Đáp án đúng: {pct(acc.value)} ({acc.correct}/{counted}), tối thiểu {pct(acc.threshold)}
          {!acc.enough_sample && (
            <>
              {' '}
              · chưa đủ mẫu ({counted}/{acc.min_sample})
            </>
          )}
          {acc.stale > 0 && <> · {acc.stale} bài cần kiểm tra lại</>}{' '}
          · <Link to="/parent/review?tab=spot-check">Kiểm tra ngẫu nhiên</Link>
        </Check>
      </ul>
      {acc.sample_outdated && <p role="note">{MSG_SAMPLE_OUTDATED}</p>}
      {!acc.enough_problems && (
        <p role="note">
          {MSG_NOT_ENOUGH_PROBLEMS} ({acc.eligible_problems}/{acc.min_sample} bài kiểm tra được)
        </p>
      )}
      <p>
        Chi phí chạy thử: {usd(cost.pilot_cost)} cho {cost.pilot_pages} trang
        {cost.est_cost !== null && (
          <>
            {' '}
            · Ước tính phần còn lại: <strong>{usd(cost.est_cost)}</strong> cho {cost.remaining_pages}/
            {cost.total_pages} trang
          </>
        )}
      </p>
      {cost.unknown_cost_calls > 0 && (
        <p>
          {cost.unknown_cost_calls} lượt gọi chưa rõ chi phí, đã tính ở mức tối đa{' '}
          {usd(cost.unknown_cost_cap_usd)}/lượt.
        </p>
      )}
    </>
  )
}

/** The go/no-go report card on ParentHome ("Chạy thử & đánh giá"). */
export default function GateCard() {
  const queryClient = useQueryClient()
  const gate = useGate()
  // The estimate the checkbox was ticked for: a different estimate (after any refetch)
  // unticks it, so a changed cost must be accepted again.
  const [acceptedFor, setAcceptedFor] = useState<number | null>(null)
  const onReport = (data: GateReport) => {
    queryClient.setQueryData(queryKeys.gate, data)
    setAcceptedFor(null)
  }
  const approve = useMutation({
    mutationFn: approveGate,
    onSuccess: onReport,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        // The estimate or the checks changed: show the current report again.
        setAcceptedFor(null)
        void queryClient.invalidateQueries({ queryKey: queryKeys.gate })
      }
    },
  })
  const revoke = useMutation({ mutationFn: revokeGate, onSuccess: onReport })

  if (gate.isPending) return <p>Đang tải…</p>
  if (gate.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(gate.error)}
      </p>
    )
  }
  const report = gate.data
  if (!report.has_pilot) {
    return (
      <div className="gate-card">
        <p>Chưa chạy thử.</p>
      </div>
    )
  }
  const est = report.cost.est_cost
  const accepted = est !== null && acceptedFor === est
  const busy = approve.isPending || revoke.isPending
  const error = approve.error ?? revoke.error

  return (
    <div className="gate-card">
      <Report report={report} />
      {report.approved && report.approval ? (
        <p role="status">
          <strong>Đã duyệt</strong> chạy toàn bộ lúc{' '}
          {new Date(report.approval.approved_at).toLocaleString('vi-VN')} (ước tính{' '}
          {usd(report.approval.est_cost)}).{' '}
          <button type="button" className="link-button" disabled={busy} onClick={() => revoke.mutate()}>
            Thu hồi
          </button>
        </p>
      ) : (
        <>
          {report.approval && !report.approval.valid && (
            <p>
              Lần duyệt trước không còn hiệu lực: {report.approval.invalid_reasons.join(' ')}{' '}
              <button type="button" className="link-button" disabled={busy} onClick={() => revoke.mutate()}>
                Thu hồi
              </button>
            </p>
          )}
          {est !== null && (
            <label className="inline-field">
              <input
                type="checkbox"
                checked={accepted}
                disabled={!report.checks_passed}
                onChange={(e) => setAcceptedFor(e.target.checked ? est : null)}
              />
              Tôi chấp nhận chi phí ước tính {usd(est)}
            </label>
          )}
          <p>
            <button
              type="button"
              disabled={busy || !report.checks_passed || !accepted || est === null}
              onClick={() => est !== null && approve.mutate(est)}
            >
              Duyệt chạy toàn bộ
            </button>
          </p>
        </>
      )}
      {error && (
        <p role="alert" className="form-error">
          {errorMessage(error)}
        </p>
      )}
    </div>
  )
}
