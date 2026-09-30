import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  acceptProposal,
  approveConceptGuide,
  mergeProposal,
  renameConcept,
  resetConceptGuide,
  saveConceptGuide,
  type ConceptOut,
  type ConceptsOut,
  type GuideDetail,
  type ProposalOut,
} from '../../api/client'
import { errorMessage } from '../../api/errors'
import { queryKeys, useConceptGuide, useConcepts } from '../../api/queries'

const STATUS_LABELS: Record<ProposalOut['status'], string> = {
  proposed: 'đề xuất',
  accepted: 'đã nhận',
  merged: 'đã gộp',
}

function useConceptAction<T>(fn: (body: T) => Promise<ConceptsOut>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.reviewConcepts, data)
      // Effective concept_ids changed: refetch the problem views.
      void queryClient.invalidateQueries({ queryKey: queryKeys.review, refetchType: 'none' })
    },
  })
}

function ProposalRow({ proposal, concepts }: { proposal: ProposalOut; concepts: ConceptOut[] }) {
  const accept = useConceptAction(acceptProposal)
  const merge = useConceptAction(mergeProposal)
  const [target, setTarget] = useState('')
  const [merging, setMerging] = useState(false)
  const error = accept.error ?? merge.error
  const busy = accept.isPending || merge.isPending
  const sameGrade = concepts.filter((c) => c.grade === proposal.grade)

  return (
    <li>
      <strong>{proposal.text}</strong> · {proposal.problem_count} bài ·{' '}
      {STATUS_LABELS[proposal.status]}
      {proposal.target_concept_id && <> → {proposal.target_concept_id}</>}
      {proposal.status === 'proposed' && (
        <span className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => accept.mutate({ grade: proposal.grade, proposal_key: proposal.proposal_key })}
          >
            Nhận
          </button>
          {!merging && (
            <button type="button" disabled={busy || sameGrade.length === 0} onClick={() => setMerging(true)}>
              Gộp vào…
            </button>
          )}
          {merging && (
            <>
              <select
                aria-label={`Gộp "${proposal.text}" vào khái niệm`}
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="">Chọn khái niệm</option>
                {sameGrade.map((c) => (
                  <option key={c.concept_id} value={c.concept_id}>
                    {c.name_vi}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={busy || !target}
                onClick={() =>
                  merge.mutate({
                    grade: proposal.grade,
                    proposal_key: proposal.proposal_key,
                    concept_id: target,
                  })
                }
              >
                Gộp
              </button>
              <button type="button" onClick={() => setMerging(false)}>
                Huỷ
              </button>
            </>
          )}
        </span>
      )}
      {error && (
        <p role="alert" className="form-error">
          {errorMessage(error)}
        </p>
      )}
    </li>
  )
}

function GuideEditor({ concept }: { concept: ConceptOut }) {
  const queryClient = useQueryClient()
  const guide = useConceptGuide(concept.concept_id, true)
  const done = (data: GuideDetail) => {
    queryClient.setQueryData(queryKeys.conceptGuide(concept.concept_id), data)
    void queryClient.invalidateQueries({ queryKey: queryKeys.reviewConcepts })
  }
  const save = useMutation({
    mutationFn: (edits: Parameters<typeof saveConceptGuide>[1]) =>
      saveConceptGuide(concept.concept_id, edits),
    onSuccess: done,
  })
  const reset = useMutation({ mutationFn: () => resetConceptGuide(concept.concept_id), onSuccess: done })
  const approve = useMutation({
    mutationFn: (hash: string) => approveConceptGuide(concept.concept_id, hash),
    onSuccess: done,
  })
  if (guide.isPending) return <p>Đang tải…</p>
  if (guide.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(guide.error)}
      </p>
    )
  }
  const error = save.error ?? reset.error ?? approve.error
  const busy = save.isPending || reset.isPending || approve.isPending
  // Re-mount the form whenever the stored Guide changes (save, reset, approve).
  return (
    <GuideForm
      key={guide.data.content_hash + guide.data.overrides.length}
      guide={guide.data}
      busy={busy}
      error={error}
      onSave={(edits) => save.mutate(edits)}
      onReset={() => reset.mutate()}
      onApprove={() => approve.mutate(guide.data.content_hash)}
    />
  )
}

function GuideForm({
  guide,
  busy,
  error,
  onSave,
  onReset,
  onApprove,
}: {
  guide: GuideDetail
  busy: boolean
  error: unknown
  onSave: (edits: Array<{ field: 'explanation' | 'example'; value: unknown }>) => void
  onReset: () => void
  onApprove: () => void
}) {
  const current = guide.effective ?? guide.generated
  const [explanation, setExplanation] = useState(current.explanation)
  const [question, setQuestion] = useState(current.example.question)
  const [steps, setSteps] = useState(current.example.steps.join('\n'))
  const [answer, setAnswer] = useState(current.example.answer)
  const example = {
    question,
    steps: steps.split('\n').map((x) => x.trim()).filter(Boolean),
    answer,
  }
  const edits: Array<{ field: 'explanation' | 'example'; value: unknown }> = []
  if (explanation !== current.explanation) edits.push({ field: 'explanation', value: explanation })
  if (JSON.stringify(example) !== JSON.stringify(current.example)) {
    edits.push({ field: 'example', value: example })
  }
  return (
    <form
      className="guide-editor"
      onSubmit={(e) => {
        e.preventDefault()
        onSave(edits)
      }}
    >
      <p>
        {guide.approved ? (
          <span className="badge">đã duyệt</span>
        ) : (
          <span className="badge badge-review">chưa duyệt</span>
        )}
        {guide.conflict && (
          <span className="badge badge-review">
            xung đột: bản sinh lại đã đổi, bản sửa của bạn vẫn được dùng
          </span>
        )}
        <span className="badge">{guide.source === 'book' ? 'từ sách' : 'từ bài tập mẫu'}</span>
      </p>
      <label>
        Giải thích
        <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={3} />
      </label>
      <label>
        Ví dụ: đề bài
        <input type="text" value={question} onChange={(e) => setQuestion(e.target.value)} />
      </label>
      <label>
        Ví dụ: các bước (mỗi dòng một bước)
        <textarea value={steps} onChange={(e) => setSteps(e.target.value)} rows={4} />
      </label>
      <label>
        Ví dụ: kết quả
        <input type="text" value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </label>
      <span className="actions">
        <button type="submit" disabled={busy || edits.length === 0}>
          Lưu hướng dẫn
        </button>
        <button type="button" disabled={busy || guide.overrides.length === 0} onClick={onReset}>
          Bỏ sửa
        </button>
        <button
          type="button"
          disabled={busy || edits.length > 0 || guide.approved}
          onClick={onApprove}
        >
          Duyệt hướng dẫn
        </button>
      </span>
      {error != null && (
        <p role="alert" className="form-error">
          {errorMessage(error)}
        </p>
      )}
    </form>
  )
}

function ConceptRow({ concept }: { concept: ConceptOut }) {
  const [showGuide, setShowGuide] = useState(false)
  const rename = useConceptAction(renameConcept)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(concept.name_vi)

  return (
    <li>
      {!editing && (
        <>
          <strong>{concept.name_vi}</strong> <span className="problem-id">{concept.concept_id}</span> ·{' '}
          {concept.problem_count} bài
          <span className="actions">
            <button
              type="button"
              onClick={() => {
                setName(concept.name_vi)
                setEditing(true)
              }}
            >
              Đổi tên
            </button>
            {concept.has_guide && (
              <button
                type="button"
                aria-expanded={showGuide}
                onClick={() => setShowGuide((v) => !v)}
              >
                Hướng dẫn
              </button>
            )}
          </span>
          {concept.has_guide && (
            <span className="badges">
              {!concept.guide_approved && <span className="badge badge-review">hướng dẫn chưa duyệt</span>}
              {concept.guide_conflict && <span className="badge badge-review">xung đột</span>}
            </span>
          )}
        </>
      )}
      {editing && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            rename.mutate(
              { concept_id: concept.concept_id, name_vi: name },
              { onSuccess: () => setEditing(false) },
            )
          }}
        >
          <input
            type="text"
            aria-label={`Tên mới cho ${concept.concept_id}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="submit" disabled={rename.isPending || !name.trim()}>
            Lưu
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Huỷ
          </button>
        </form>
      )}
      {showGuide && concept.has_guide && <GuideEditor concept={concept} />}
      {rename.isError && (
        <p role="alert" className="form-error">
          {errorMessage(rename.error)}
        </p>
      )}
    </li>
  )
}

export default function ConceptsTab() {
  const concepts = useConcepts()
  if (concepts.isPending) return <p>Đang tải…</p>
  if (concepts.isError) {
    return (
      <p role="alert" className="form-error">
        {errorMessage(concepts.error)}
      </p>
    )
  }
  const { proposals, concepts: curated } = concepts.data
  const grades = [...new Set([...proposals.map((p) => p.grade), ...curated.map((c) => c.grade)])].sort()
  if (grades.length === 0) return <p>Chưa có đề xuất khái niệm.</p>

  return (
    <>
      {grades.map((grade) => {
        const gradeProposals = proposals.filter((p) => p.grade === grade)
        const gradeConcepts = curated.filter((c) => c.grade === grade)
        return (
          <section key={grade} className="concept-grade">
            <h2>Lớp {grade}</h2>
            <h3>Đề xuất ({gradeProposals.length})</h3>
            {gradeProposals.length === 0 ? (
              <p>Không có đề xuất.</p>
            ) : (
              <ul className="concept-list">
                {gradeProposals.map((p) => (
                  <ProposalRow key={p.proposal_key} proposal={p} concepts={curated} />
                ))}
              </ul>
            )}
            <h3>Khái niệm ({gradeConcepts.length})</h3>
            {gradeConcepts.length === 0 ? (
              <p>Chưa có khái niệm.</p>
            ) : (
              <ul className="concept-list">
                {gradeConcepts.map((c) => (
                  <ConceptRow key={c.concept_id} concept={c} />
                ))}
              </ul>
            )}
          </section>
        )
      })}
    </>
  )
}
