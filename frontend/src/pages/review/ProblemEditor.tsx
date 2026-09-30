import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useBlocker, useParams, useSearchParams } from 'react-router'
import {
  ApiError,
  approveProblem,
  deleteAllOverrides,
  deleteOverride,
  resolveReport,
  saveOverrides,
  setProblemHidden,
  type EditIn,
  type OverrideOut,
  type ProblemDetail,
  type ProblemDoc,
  type ProblemPart,
} from '../../api/client'
import { errorMessage } from '../../api/errors'
import { queryKeys, useReviewProblem } from '../../api/queries'
import { Badges } from './ProblemList'
import ReportProblem from './ReportProblem'

// Answers edited as one input per key.
const KEYED_TYPES = new Set([
  'number_input',
  'compare',
  'number_tree',
  'grid_fill',
  'count_image',
  'dot_draw',
])
// Answers edited as a list of keys: selected options/regions, or the order of items.
const LIST_TYPES: Record<string, 'selected' | 'order'> = {
  multiple_choice: 'selected',
  image_select: 'selected',
  order: 'order',
}

const FIELD_LABELS: Record<string, string> = {
  instruction: 'đề bài',
  display_label: 'nhãn bài',
  prompt: 'câu hỏi',
  answer: 'đáp án',
  hint: 'gợi ý',
  solution: 'lời giải',
  part: 'cả phần',
}

const MSG_SAVE_FIRST = 'Lưu trước khi duyệt.'
const MSG_LEAVE = 'Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?'

type KeyedEntry = { key: string; value: string }

type PartForm = {
  prompt: string
  hint: string
  steps: string
  final: string
  keyed: KeyedEntry[]
  list: string
  answerJson: string
  partJson: string
}

type FormState = { instruction: string; displayLabel: string; parts: Record<string, PartForm> }

type Message = { kind: 'status' | 'alert'; text: string; details?: string[] }

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function answerKind(part: ProblemPart): 'keyed' | 'list' | 'json' {
  if (KEYED_TYPES.has(part.type)) return 'keyed'
  if (part.type in LIST_TYPES) return 'list'
  return 'json'
}

function listOf(part: ProblemPart): string[] {
  const answer = part.answer as Record<string, string[]> | null
  return answer?.[LIST_TYPES[part.type]] ?? []
}

function initialPart(part: ProblemPart): PartForm {
  const kind = answerKind(part)
  return {
    prompt: part.prompt,
    hint: part.hint,
    steps: part.solution.steps.join('\n'),
    final: part.solution.final,
    keyed: kind === 'keyed' ? (part.answer as KeyedEntry[]).map((e) => ({ ...e })) : [],
    list: kind === 'list' ? listOf(part).join(', ') : '',
    answerJson: pretty(part.answer),
    partJson: pretty(part),
  }
}

function initialForm(doc: ProblemDoc): FormState {
  return {
    instruction: doc.instruction,
    displayLabel: doc.display_label,
    parts: Object.fromEntries(doc.parts.map((p) => [p.part_key, initialPart(p)])),
  }
}

class FormError extends Error {}

function parseJson(text: string, where: string): EditIn['value'] {
  try {
    return JSON.parse(text) as EditIn['value']
  } catch {
    throw new FormError(`${where}: JSON không hợp lệ.`)
  }
}

/**
 * The field-level edits: one per field whose editor value changed from its initial
 * string. A changed Part JSON replaces the whole Part and wins over its other inputs.
 */
function diff(doc: ProblemDoc, initial: FormState, form: FormState): EditIn[] {
  const edits: EditIn[] = []
  if (form.instruction !== initial.instruction) {
    edits.push({ field: 'instruction', value: form.instruction })
  }
  if (form.displayLabel !== initial.displayLabel) {
    edits.push({ field: 'display_label', value: form.displayLabel })
  }
  for (const part of doc.parts) {
    const key = part.part_key
    const f = form.parts[key]
    const i = initial.parts[key]
    const where = `Phần ${key}`
    if (f.partJson !== i.partJson) {
      edits.push({ part_key: key, field: 'part', value: parseJson(f.partJson, where) })
      continue
    }
    if (f.prompt !== i.prompt) edits.push({ part_key: key, field: 'prompt', value: f.prompt })
    if (f.hint !== i.hint) edits.push({ part_key: key, field: 'hint', value: f.hint })
    if (f.steps !== i.steps || f.final !== i.final) {
      const steps = f.steps
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
      edits.push({ part_key: key, field: 'solution', value: { steps, final: f.final } })
    }
    const kind = answerKind(part)
    if (kind === 'keyed' && !same(f.keyed, i.keyed)) {
      const value = f.keyed.map((e) => ({ key: e.key, value: e.value.trim() }))
      edits.push({ part_key: key, field: 'answer', value })
    } else if (kind === 'list' && f.list !== i.list) {
      const keys = f.list
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      edits.push({ part_key: key, field: 'answer', value: { [LIST_TYPES[part.type]]: keys } })
    } else if (kind === 'json' && f.answerJson !== i.answerJson) {
      edits.push({ part_key: key, field: 'answer', value: parseJson(f.answerJson, `${where} › đáp án`) })
    }
  }
  return edits
}

function overrideLabel(o: OverrideOut): string {
  const field = FIELD_LABELS[o.field] ?? o.field
  return o.part_key ? `Phần ${o.part_key} › ${field}` : field
}

function toMessage(error: unknown): Message {
  return {
    kind: 'alert',
    text: error instanceof FormError ? error.message : errorMessage(error),
    details: error instanceof ApiError ? error.details : [],
  }
}

function MessageView({ message }: { message: Message | null }) {
  if (!message) return null
  if (message.kind === 'status') return <p role="status">{message.text}</p>
  return (
    <div role="alert" className="form-error">
      <p className="form-error">{message.text}</p>
      {message.details && message.details.length > 0 && (
        <ul>
          {message.details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PartFields({
  part,
  value,
  onChange,
}: {
  part: ProblemPart
  value: PartForm
  onChange: (next: PartForm) => void
}) {
  const kind = answerKind(part)
  const set = (patch: Partial<PartForm>) => onChange({ ...value, ...patch })
  const name = `Phần ${part.part_key}`

  return (
    <fieldset>
      <legend>
        {name} · {part.type}
      </legend>
      <label>
        Câu hỏi
        <textarea
          aria-label={`${name} câu hỏi`}
          value={value.prompt}
          onChange={(e) => set({ prompt: e.target.value })}
          rows={2}
        />
      </label>
      {kind === 'keyed' && (
        <div className="answer-keyed">
          <span>Đáp án</span>
          {value.keyed.map((entry, i) => (
            <label key={entry.key} className="inline-field">
              {entry.key}
              <input
                type="text"
                aria-label={`${name} đáp án ${entry.key}`}
                value={entry.value}
                onChange={(e) =>
                  set({ keyed: value.keyed.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })
                }
              />
            </label>
          ))}
        </div>
      )}
      {kind === 'list' && (
        <label>
          Đáp án ({LIST_TYPES[part.type] === 'order' ? 'thứ tự các mục' : 'các lựa chọn đúng'}, cách nhau bởi dấu phẩy)
          <input
            type="text"
            aria-label={`${name} đáp án`}
            value={value.list}
            onChange={(e) => set({ list: e.target.value })}
          />
        </label>
      )}
      {kind === 'json' && (
        <label>
          Đáp án (JSON)
          <textarea
            className="mono"
            aria-label={`${name} đáp án JSON`}
            value={value.answerJson}
            onChange={(e) => set({ answerJson: e.target.value })}
            rows={4}
          />
        </label>
      )}
      <label>
        Gợi ý
        <textarea
          aria-label={`${name} gợi ý`}
          value={value.hint}
          onChange={(e) => set({ hint: e.target.value })}
          rows={2}
        />
      </label>
      <label>
        Lời giải (mỗi bước một dòng)
        <textarea
          aria-label={`${name} lời giải`}
          value={value.steps}
          onChange={(e) => set({ steps: e.target.value })}
          rows={3}
        />
      </label>
      <label>
        Kết quả
        <input
          type="text"
          aria-label={`${name} kết quả`}
          value={value.final}
          onChange={(e) => set({ final: e.target.value })}
        />
      </label>
      <details>
        <summary>Thay cả phần (JSON, dùng để đổi dạng bài)</summary>
        <textarea
          className="mono"
          aria-label={`${name} JSON`}
          value={value.partJson}
          onChange={(e) => set({ partJson: e.target.value })}
          rows={12}
        />
      </details>
    </fieldset>
  )
}

/** Warns before leaving the page (in-app navigation or closing the tab) while dirty. */
function useLeaveWarning(dirty: boolean) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  )
  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (window.confirm(MSG_LEAVE)) blocker.proceed()
    else blocker.reset()
  }, [blocker])
  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])
}

function EditorForm({
  detail,
  message,
  setMessage,
}: {
  detail: ProblemDetail
  message: Message | null
  setMessage: (m: Message | null) => void
}) {
  const queryClient = useQueryClient()
  const problemId = detail.summary.problem_id
  const invalid = detail.effective === null
  const doc = (detail.effective ?? detail.extracted) as ProblemDoc
  const [initial] = useState<FormState>(() => initialForm(doc))
  const [form, setForm] = useState<FormState>(initial)
  const dirty = !invalid && !same(form, initial)
  useLeaveWarning(dirty)

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue })
    void queryClient.invalidateQueries({ queryKey: ['review', 'problems'] })
    // An edit changes the effective hash: spot-check verdicts may need re-checking.
    void queryClient.invalidateQueries({ queryKey: queryKeys.spotCheck })
    void queryClient.invalidateQueries({ queryKey: queryKeys.gate })
  }
  const onDetail = (text: string) => (data: ProblemDetail) => {
    queryClient.setQueryData(queryKeys.reviewProblem(problemId), data)
    refresh()
    setMessage({ kind: 'status', text })
  }
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.code === 'STALE') {
      // Someone (or a re-publish) changed it: show the current content.
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewProblem(problemId) })
    }
    setMessage(toMessage(error))
  }
  const common = { onMutate: () => setMessage(null), onError }

  const save = useMutation({
    mutationFn: async () => {
      const edits = diff(doc, initial, form)
      return edits.length === 0 ? null : saveOverrides(problemId, edits)
    },
    ...common,
    onSuccess: (data: ProblemDetail | null) => {
      if (data) onDetail('Đã lưu.')(data)
      else setMessage({ kind: 'status', text: 'Không có thay đổi.' })
    },
  })
  const approve = useMutation({
    mutationFn: () => approveProblem(problemId, detail.content_hash ?? ''),
    ...common,
    onSuccess: onDetail('Đã duyệt.'),
  })
  const hide = useMutation({
    mutationFn: (hidden: boolean) => setProblemHidden(problemId, hidden),
    ...common,
    onSuccess: (data: ProblemDetail, hidden: boolean) => onDetail(hidden ? 'Đã ẩn.' : 'Đã hiện.')(data),
  })
  const revert = useMutation({
    mutationFn: (overrideId: string | null) =>
      overrideId ? deleteOverride(problemId, overrideId) : deleteAllOverrides(problemId),
    ...common,
    onSuccess: onDetail('Đã bỏ sửa.'),
  })
  const resolve = useMutation({
    mutationFn: resolveReport,
    ...common,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewProblem(problemId) })
      refresh()
      setMessage({ kind: 'status', text: 'Đã đánh dấu báo lỗi là đã xử lý.' })
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }
  const busy = [save, approve, hide, revert, resolve].some((m) => m.isPending)

  return (
    <form className="review-form" onSubmit={onSubmit}>
      {invalid && (
        <div role="alert" className="form-error">
          <p className="form-error">
            Nội dung sau khi sửa không hợp lệ. Hãy bỏ các bản sửa gây lỗi; chưa sửa được các ô bên dưới.
          </p>
          <ul>
            {detail.effective_error.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      <fieldset className="plain" disabled={invalid}>
        <label>
          Nhãn bài
          <input
            type="text"
            value={form.displayLabel}
            onChange={(e) => setForm({ ...form, displayLabel: e.target.value })}
          />
        </label>
        <label>
          Đề bài
          <textarea
            value={form.instruction}
            onChange={(e) => setForm({ ...form, instruction: e.target.value })}
            rows={2}
          />
        </label>
        {doc.parts.map((part) => (
          <PartFields
            key={part.part_key}
            part={part}
            value={form.parts[part.part_key]}
            onChange={(next) => setForm({ ...form, parts: { ...form.parts, [part.part_key]: next } })}
          />
        ))}
      </fieldset>
      <MessageView message={message} />
      <div className="actions">
        <button type="submit" disabled={busy || invalid}>
          Lưu
        </button>
        <button type="button" disabled={busy || dirty || invalid} onClick={() => approve.mutate()}>
          Duyệt
        </button>
        {detail.status.hidden ? (
          <button type="button" disabled={busy || dirty} onClick={() => hide.mutate(false)}>
            Hiện
          </button>
        ) : (
          <button type="button" disabled={busy || dirty} onClick={() => hide.mutate(true)}>
            Ẩn
          </button>
        )}
        {dirty && <span className="hint">{MSG_SAVE_FIRST}</span>}
      </div>
      {detail.overrides.length > 0 && (
        <section>
          <h2>Bản sửa</h2>
          <ul className="override-list">
            {detail.overrides.map((o) => (
              <li key={o.id}>
                {overrideLabel(o)}
                {o.conflict && (
                  <span className="badge badge-conflict">
                    {o.conflict === 'part_missing' ? 'xung đột: phần không còn' : 'xung đột: bản gốc đã đổi'}
                  </span>
                )}
                <button
                  type="button"
                  aria-label={`Bỏ sửa ${overrideLabel(o)}`}
                  disabled={busy || dirty}
                  onClick={() => revert.mutate(o.id)}
                >
                  Bỏ sửa
                </button>
              </li>
            ))}
          </ul>
          {invalid && (
            <button type="button" disabled={busy} onClick={() => revert.mutate(null)}>
              Bỏ tất cả sửa đổi
            </button>
          )}
        </section>
      )}
      <section>
        <h2>Báo lỗi</h2>
        <ReportProblem
          problemId={detail.summary.problem_id}
          reported={detail.reports.some((r) => r.kind === 'parent' && r.status === 'open')}
        />
        {detail.reports.length > 0 && (
          <ul>
            {detail.reports.map((r) => (
              <li key={r.id}>
                {r.kind === 'parent' ? 'Phụ huynh' : 'Bé'}: {r.note || '(không ghi chú)'} ·{' '}
                {r.status === 'open' ? 'đang mở' : 'đã xử lý'}
                {r.status === 'open' && (
                  <button type="button" disabled={busy} onClick={() => resolve.mutate(r.id)}>
                    Đã xử lý
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </form>
  )
}

function statusLine(detail: ProblemDetail): string {
  const s = detail.status
  const parts = [s.visible ? 'Bé đang thấy bài này' : 'Bé chưa thấy bài này']
  if (s.approved) parts.push('đã duyệt')
  return parts.join(' · ')
}

export default function ProblemEditor() {
  const { problemId = '' } = useParams()
  const [params] = useSearchParams()
  const fromSpotCheck = params.get('from') === 'spot-check'
  const problem = useReviewProblem(problemId)
  // Kept here, not in the form: the form remounts whenever the content changes.
  const [message, setMessage] = useState<Message | null>(null)

  return (
    <main className="parent parent-wide">
      <p>
        {fromSpotCheck ? (
          <Link to="/parent/review?tab=spot-check">Kiểm tra ngẫu nhiên</Link>
        ) : (
          <Link to="/parent/review">Duyệt nội dung</Link>
        )}
      </p>
      {problem.isPending && <p>Đang tải…</p>}
      {problem.isError && (
        <p role="alert" className="form-error">
          {errorMessage(problem.error)}
        </p>
      )}
      {problem.isSuccess && (
        <>
          <h1>
            {problem.data.summary.display_label}{' '}
            <span className="problem-id">{problem.data.summary.problem_id}</span>
          </h1>
          <p>
            <Badges problem={problem.data.summary} /> {statusLine(problem.data)}
          </p>
          <div className="review-editor">
            <div className="review-source">
              {problem.data.crop_urls.slice(0, 1).map((url) => (
                <img key={url} src={url} alt="Ảnh cắt của bài" />
              ))}
              {problem.data.page_urls.map((url) => (
                <img key={url} src={url} alt="Trang sách gốc" />
              ))}
            </div>
            <EditorForm
              key={`${problem.data.content_hash}:${problem.data.overrides.map((o) => o.id + o.base_hash).join(',')}`}
              detail={problem.data}
              message={message}
              setMessage={setMessage}
            />
          </div>
        </>
      )}
    </main>
  )
}
