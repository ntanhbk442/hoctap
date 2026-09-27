import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  acceptProposal,
  mergeProposal,
  renameConcept,
  type ConceptOut,
  type ConceptsOut,
  type ProposalOut,
} from '../../api/client'
import { errorMessage } from '../../api/errors'
import { queryKeys, useConcepts } from '../../api/queries'

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

function ConceptRow({ concept }: { concept: ConceptOut }) {
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
          </span>
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
