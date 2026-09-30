import { Link, Navigate, useParams } from 'react-router'
import { authRedirect, errorMessage } from '../api/errors'
import { useReviewProblem } from '../api/queries'
import { answerLines } from './review/answerText'
import ReportProblem from './review/ReportProblem'

/**
 * Story 4.4: read-only view of one Problem as the parent sees it (label, crop, Answer
 * Key, Concepts, existing reports) with the "Báo lỗi" action. Reuses the Review data.
 */
export default function ProblemPreview() {
  const { problemId = '' } = useParams()
  const problem = useReviewProblem(problemId)

  if (problem.isError) {
    const target = authRedirect(problem.error)
    if (target) return <Navigate to={target} replace />
  }
  const data = problem.data
  const doc = data?.effective ?? null
  return (
    <main className="parent problem-preview">
      <p>
        <Link to="/parent/dashboard">Về tiến độ của bé</Link>
      </p>
      {problem.isPending && <p>Đang tải…</p>}
      {problem.isError && (
        <p role="alert" className="form-error">
          {errorMessage(problem.error)}
        </p>
      )}
      {data && (
        <>
          <h1>{data.summary.display_label}</h1>
          {data.crop_urls.slice(0, 1).map((url) => (
            <img key={url} src={url} alt="Ảnh cắt của bài" />
          ))}
          {doc && (
            <>
              <p>{doc.instruction}</p>
              {doc.parts.map((part) => (
                <section key={part.part_key}>
                  <h2>Phần {part.part_key}</h2>
                  <p>{part.prompt}</p>
                  <p>
                    Đáp án:{' '}
                    {answerLines(part).map((line) => (
                      <span key={line} className="answer-line">
                        {line}{' '}
                      </span>
                    ))}
                  </p>
                </section>
              ))}
              <section>
                <h2>Kiến thức</h2>
                {doc.concept_ids.length + doc.concept_proposals.length === 0 && <p>Chưa gắn.</p>}
                <ul>
                  {doc.concept_ids.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                  {doc.concept_proposals.map((c) => (
                    <li key={c}>{c} (đề xuất)</li>
                  ))}
                </ul>
              </section>
            </>
          )}
          {data.reports.length > 0 && (
            <section>
              <h2>Báo lỗi</h2>
              <ul>
                {data.reports.map((r) => (
                  <li key={r.id}>
                    {r.kind === 'parent' ? 'Phụ huynh' : 'Bé'}: {r.note || '(không ghi chú)'} ·{' '}
                    {r.status === 'open' ? 'đang mở' : 'đã xử lý'}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <ReportProblem
            problemId={problemId}
            reported={data.reports.some((r) => r.kind === 'parent' && r.status === 'open')}
          />
          <p>
            <Link to={`/parent/review/problems/${problemId}`}>Mở trong Duyệt nội dung</Link>
          </p>
        </>
      )}
    </main>
  )
}
