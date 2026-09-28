import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import {
  ApiError,
  drawSpotCheck,
  setSpotCheckVerdict,
  type ProblemDetail,
  type SpotCheckItem,
  type SpotCheckOut,
} from '../../api/client'
import { errorMessage } from '../../api/errors'
import { queryKeys, useReviewProblem, useSpotCheck } from '../../api/queries'
import { AnswerOverlay } from './answerOverlay'
import { answerLines } from './answerText'
import { cropUrlByImageKey, needsOverlay } from './overlayGeometry'

const MSG_REDRAW =
  'Rút mẫu mới? Mẫu hiện tại vẫn được lưu nhưng không còn được tính vào báo cáo.'

function verdictLabel(item: SpotCheckItem): string {
  if (item.stale) return 'cần kiểm tra lại'
  if (item.verdict === 'correct') return 'Đúng'
  if (item.verdict === 'wrong') return 'Sai'
  return 'chưa kiểm tra'
}

function needsWork(item: SpotCheckItem): boolean {
  return item.verdict === null || item.stale
}

/** The first item from `start` (wrapping) that still needs a verdict, else `start`. */
function nextToCheck(items: SpotCheckItem[], start: number): number {
  for (let k = 0; k < items.length; k++) {
    const i = (start + k) % items.length
    if (needsWork(items[i])) return i
  }
  return Math.min(start, items.length - 1)
}

function Answer({ detail }: { detail: ProblemDetail }) {
  const doc = detail.effective
  if (!doc) {
    return (
      <p role="alert" className="form-error">
        Nội dung sau khi sửa không hợp lệ; hãy bấm Sửa để sửa trước.
      </p>
    )
  }
  const cropByImageKey = cropUrlByImageKey(doc, detail.crop_urls)
  return (
    <div className="spot-answer">
      <p className="problem-instruction">{doc.instruction}</p>
      {doc.parts.map((part) => (
        <section key={part.part_key} aria-label={`Phần ${part.part_key}`}>
          <h3>
            Phần {part.part_key} · {part.type}
          </h3>
          {part.prompt && <p>{part.prompt}</p>}
          <p>
            <strong>Đáp án:</strong>
          </p>
          <ul className="spot-answer-lines">
            {answerLines(part).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
          {needsOverlay(part.type) && <AnswerOverlay part={part} cropByImageKey={cropByImageKey} />}
          <p>
            <strong>Gợi ý:</strong> {part.hint}
          </p>
          <p>
            <strong>Lời giải:</strong>
          </p>
          <ol>
            {part.solution.steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
          <p>
            <strong>Kết quả:</strong> {part.solution.final}
          </p>
        </section>
      ))}
    </div>
  )
}

function ItemView({
  sample,
  item,
  onJudged,
}: {
  sample: SpotCheckOut
  item: SpotCheckItem
  onJudged: (data: SpotCheckOut) => void
}) {
  const queryClient = useQueryClient()
  const problem = useReviewProblem(item.problem_id)
  const [note, setNote] = useState(item.note)
  const verdict = useMutation({
    mutationFn: ({ value, hash }: { value: 'correct' | 'wrong'; hash: string }) =>
      setSpotCheckVerdict(sample.sample_id ?? '', item.problem_id, {
        verdict: value,
        note: value === 'wrong' ? note : '',
        content_hash: hash,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.spotCheck, data)
      // A Sai verdict puts the Problem in Cần duyệt; the gate report changes too.
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue })
      void queryClient.invalidateQueries({ queryKey: queryKeys.gate })
      onJudged(data)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'STALE') {
        void queryClient.invalidateQueries({ queryKey: queryKeys.reviewProblem(item.problem_id) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.spotCheck })
      }
    },
  })

  const hash = problem.data?.content_hash ?? null
  const busy = verdict.isPending || problem.isFetching

  return (
    <article className="spot-item" aria-label={`Bài ${item.position} trong mẫu`}>
      <h2>
        {item.display_label} <span className="problem-id">{item.problem_id}</span>
      </h2>
      <p>
        Kết quả:{' '}
        <span className={item.stale ? 'badge badge-conflict' : 'badge'}>{verdictLabel(item)}</span>
        {item.note && <> · Ghi chú: {item.note}</>}
      </p>
      {problem.isPending && <p>Đang tải…</p>}
      {problem.isError && (
        <p role="alert" className="form-error">
          {errorMessage(problem.error)}
        </p>
      )}
      {problem.isSuccess && (
        <div className="review-editor">
          <div className="review-source">
            {problem.data.crop_urls.map((url) => (
              <img key={url} src={url} alt="Ảnh cắt của bài" />
            ))}
          </div>
          <Answer detail={problem.data} />
        </div>
      )}
      <label className="spot-note">
        Ghi chú (khi Sai, không bắt buộc)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} />
      </label>
      {verdict.isError && (
        <p role="alert" className="form-error">
          {errorMessage(verdict.error)}
        </p>
      )}
      <div className="actions">
        <button
          type="button"
          disabled={busy || !hash}
          onClick={() => hash && verdict.mutate({ value: 'correct', hash })}
        >
          Đúng
        </button>
        <button
          type="button"
          disabled={busy || !hash}
          onClick={() => hash && verdict.mutate({ value: 'wrong', hash })}
        >
          Sai
        </button>
        <Link to={`/parent/review/problems/${encodeURIComponent(item.problem_id)}?from=spot-check`}>Sửa</Link>
      </div>
    </article>
  )
}

export default function SpotCheckTab() {
  const queryClient = useQueryClient()
  const spot = useSpotCheck()
  const [chosen, setChosen] = useState<{ sampleId: string; index: number } | null>(null)
  const draw = useMutation({
    mutationFn: drawSpotCheck,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.spotCheck, data)
      void queryClient.invalidateQueries({ queryKey: queryKeys.gate })
      setChosen(null)
    },
  })

  if (spot.isPending) return <p>Đang tải…</p>
  if (spot.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(spot.error)}
      </p>
    )
  }
  const sample = spot.data
  const items = sample.items
  const onDraw = () => {
    if (items.length === 0 || window.confirm(MSG_REDRAW)) draw.mutate()
  }
  const drawButton = (
    <button type="button" onClick={onDraw} disabled={draw.isPending}>
      Rút mẫu mới
    </button>
  )
  const drawError = draw.isError && (
    <p role="alert" className="form-error">
      {errorMessage(draw.error)}
    </p>
  )

  if (!sample.sample_id || items.length === 0) {
    return (
      <>
        <p>Chưa có mẫu kiểm tra. Rút một mẫu ngẫu nhiên từ các bài chạy thử để kiểm tra đáp án.</p>
        {drawButton}
        {drawError}
      </>
    )
  }

  const index =
    chosen && chosen.sampleId === sample.sample_id
      ? Math.min(chosen.index, items.length - 1)
      : nextToCheck(items, 0)
  const item = items[index]
  const go = (i: number) => setChosen({ sampleId: sample.sample_id ?? '', index: i })

  return (
    <>
      <p className="spot-progress">
        <strong aria-label="Tiến độ">
          {sample.checked}/{sample.size}
        </strong>{' '}
        đã kiểm tra · {sample.correct} Đúng · {sample.wrong} Sai
        {sample.stale > 0 && <> · {sample.stale} cần kiểm tra lại</>}
      </p>
      <nav className="pager" aria-label="Bài trong mẫu">
        <button type="button" disabled={index <= 0} onClick={() => go(index - 1)}>
          Bài trước
        </button>
        <span>
          Bài {index + 1}/{items.length}
        </span>
        <button type="button" disabled={index >= items.length - 1} onClick={() => go(index + 1)}>
          Bài sau
        </button>
        {drawButton}
      </nav>
      {drawError}
      <ItemView
        key={`${item.problem_id}:${item.verdict}:${item.verdict_hash}`}
        sample={sample}
        item={item}
        onJudged={(data) => go(nextToCheck(data.items, index + 1))}
      />
    </>
  )
}
