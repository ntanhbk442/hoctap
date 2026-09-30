import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '../../api/errors'
import { useLibraryConcept, useLibraryConcepts, useStartSession } from '../../api/queries'
import {
  getPlayerState,
  isMissing,
  stop as stopAudio,
  subscribe as subscribePlayer,
  type PlayerState,
} from '../../audio/player'
import { speak, speechKey } from '../../audio/speech'
import SpeakerButton from '../SpeakerButton/SpeakerButton'
import './ConceptGuide.css'

/** One Guide text with its own 🔊 (client-side `speechKey`, same normaliser as the
 * backend's `guide_speech_refs()`); a missing clip greys the button and keeps the text. */
function GuideText({ text, as: Tag = 'p' }: { text: string; as?: 'p' | 'span' }) {
  const [key, setKey] = useState<string | null>(null)
  const [player, setPlayer] = useState<PlayerState>(() => getPlayerState())
  useEffect(() => {
    let cancelled = false
    void speechKey(text).then((k) => {
      if (!cancelled) setKey(k)
    })
    return () => {
      cancelled = true
    }
  }, [text])
  useEffect(() => subscribePlayer(setPlayer), [])
  const playing = key !== null && player.key === key && player.status === 'playing'
  const missing = key !== null && isMissing(key)
  return (
    <div className="concept-guide-row">
      <Tag className="concept-guide-text">{text}</Tag>
      <SpeakerButton
        label={text}
        playing={playing}
        missing={missing}
        onClick={() => void speak(text)}
      />
    </div>
  )
}

export interface ConceptGuideProps {
  /** The Concepts to offer (chips when 2-3; the first is selected). */
  conceptIds: string[]
  grade: number
  profileId: string
  onClose: () => void
}

/**
 * Story 5.2: the Concept Guide overlay. Rendered above whatever screen opened it (the
 * mounted `ProblemPlayer` keeps its typed answer). Only an approved Guide is ever shown;
 * with none the overlay says so and "Luyện tập" stays available. Child copy stays
 * positive: no red, no ✗.
 */
export default function ConceptGuide({ conceptIds, grade, profileId, onClose }: ConceptGuideProps) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState(conceptIds[0] ?? '')
  const names = useLibraryConcepts(grade, { enabled: conceptIds.length > 1 })
  const concept = useLibraryConcept(selected)
  const start = useStartSession()

  // Closing (or leaving) the overlay stops any Guide audio.
  useEffect(() => () => stopAudio(), [])

  function nameOf(id: string): string {
    return names.data?.find((c) => c.concept_id === id)?.name_vi ?? id
  }

  const data = concept.data
  const guide = data?.guide ?? null

  return (
    <div className="concept-guide-backdrop">
      <div className="concept-guide" role="dialog" aria-modal="true" aria-label="Hướng dẫn">
        <div className="concept-guide-head">
          <h2>{data?.name_vi ?? '📖'}</h2>
          <button type="button" className="concept-guide-close" onClick={onClose}>
            Đóng
          </button>
        </div>

        {conceptIds.length > 1 && (
          <div className="concept-guide-chips" role="tablist">
            {conceptIds.map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={id === selected}
                className={`concept-guide-chip${id === selected ? ' concept-guide-chip-on' : ''}`}
                onClick={() => setSelected(id)}
              >
                {nameOf(id)}
              </button>
            ))}
          </div>
        )}

        {concept.isPending && <p>Đang tải…</p>}
        {concept.isError && (
          <>
            <p role="alert">Chưa tải được hướng dẫn. Em thử lại nhé!</p>
            <button type="button" onClick={() => void concept.refetch()}>
              Thử lại
            </button>
          </>
        )}

        {data && !guide && <p>Chưa có hướng dẫn cho khái niệm này</p>}
        {guide && (
          <div className="concept-guide-body">
            <GuideText text={guide.explanation} />
            <h3>Ví dụ</h3>
            <GuideText text={guide.example.question} />
            <ol className="concept-guide-steps">
              {guide.example.steps.map((step, i) => (
                <li key={i}>
                  <GuideText text={step} as="span" />
                </li>
              ))}
            </ol>
            <GuideText text={guide.example.answer} />
          </div>
        )}

        {data && data.problem_count > 0 && (
          <button
            type="button"
            className="concept-guide-practice"
            disabled={start.isPending}
            onClick={() =>
              start.mutate(
                {
                  profileId,
                  ref: { kind: 'concept', concept_id: data.concept_id },
                  mode: 'concept',
                },
                { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
              )
            }
          >
            Luyện tập
          </button>
        )}
        {start.isError && <p role="alert">{errorMessage(start.error)}</p>}
      </div>
    </div>
  )
}
