import { Link, Navigate, useSearchParams } from 'react-router'
import type { WorksheetRef } from '../api/client'
import { authRedirect, errorMessage } from '../api/errors'
import { useWorksheet } from '../api/queries'
import { answerLines } from '../pages/review/answerText'
import PrintPart from './PrintPart'
import type { PrintCtx } from './renderers'
import './print.css'

function refFromParams(params: URLSearchParams): WorksheetRef | null {
  const conceptId = params.get('concept_id')
  const profileId = params.get('profile_id')
  if (conceptId && profileId) return { conceptId, profileId }
  const bookId = params.get('book_id')
  const unitKey = params.get('unit_key')
  const lessonKey = params.get('lesson_key')
  if (bookId && unitKey && lessonKey) return { bookId, unitKey, lessonKey }
  return null
}

/**
 * Story 7.1 (FR-22): A4 print preview. The problem pages carry no Answer Key, Hint or
 * Solution; the answers come after a page break. The browser does the printing ("In" or
 * "Lưu thành PDF").
 */
export default function WorksheetPage() {
  const [params] = useSearchParams()
  const ref = refFromParams(params)
  const sheet = useWorksheet(ref)

  if (sheet.isError) {
    const target = authRedirect(sheet.error)
    if (target) return <Navigate to={target} replace />
  }
  const data = sheet.data
  const problems = data?.problems ?? []
  const empty = sheet.isSuccess && problems.length === 0

  return (
    <main className="ws">
      <div className="ws-chrome">
        <Link to="/parent">Về khu vực phụ huynh</Link>
        <button type="button" disabled={!data || empty} onClick={() => window.print()}>
          In phiếu
        </button>
        <span>Chọn “Lưu thành PDF” trong hộp thoại in để lưu file.</span>
      </div>
      {ref === null && (
        <p role="alert" className="form-error">
          Chưa chọn tiết học hoặc khái niệm để in phiếu.
        </p>
      )}
      {sheet.isPending && ref !== null && <p>Đang tải…</p>}
      {sheet.isError && (
        <p role="alert" className="form-error">
          {errorMessage(sheet.error)}
        </p>
      )}
      {data && (
        <>
          <header className="ws-head">
            <h1>{data.title}</h1>
            <p>{data.subtitle}</p>
            <p>Họ và tên: ……………………………………… Ngày: ………………………</p>
          </header>
          {empty && <p>Phiếu này chưa có bài nào để in.</p>}
          {problems.map((p, i) => {
            const ctx: PrintCtx = {
              imageUrls: p.image_urls,
              cropUrl: p.crop_url,
              instruction: p.doc.instruction,
            }
            return (
              <article key={p.problem_id} className="ws-problem" data-testid="ws-problem">
                <h2>
                  Câu {i + 1}. {p.doc.display_label}
                </h2>
                {p.doc.instruction && <p className="ws-instruction">{p.doc.instruction}</p>}
                {p.doc.parts.map((part) => (
                  <PrintPart key={part.part_key} part={part} ctx={ctx} />
                ))}
              </article>
            )
          })}
          {!empty && (
            <section className="ws-answers" data-testid="ws-answers" aria-label="Đáp án">
              <h2>Đáp án — {data.title}</h2>
              <ol>
                {problems.map((p) => (
                  <li key={p.problem_id}>
                    <strong>{p.doc.display_label}</strong>
                    {p.doc.parts.map((part) => (
                      <div key={part.part_key}>
                        {part.part_key}){' '}
                        {answerLines(part).map((line) => (
                          <span key={line} className="p-choice">
                            {line}
                          </span>
                        ))}
                      </div>
                    ))}
                  </li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}
    </main>
  )
}
