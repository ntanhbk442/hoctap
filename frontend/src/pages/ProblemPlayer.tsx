import { useRef, useState } from 'react'
import type { BundleProblemOut, ChildProblemView, EventOut } from '../api/client'
import { errorMessage } from '../api/errors'
import { usePostEvent } from '../api/queries'
import { phrase } from '../audio/phrases'
import { playBoop, playChime } from '../audio/sfx'
import { speak } from '../audio/speech'
import type { AnswerSlotState } from '../components/AnswerSlot/AnswerSlot'
import FeedbackBanner from '../components/FeedbackBanner/FeedbackBanner'
import HintBubble from '../components/HintBubble/HintBubble'
import NumberPad from '../components/NumberPad/NumberPad'
import SolutionPanel from '../components/SolutionPanel/SolutionPanel'
import StarBurst from '../components/StarBurst/StarBurst'
import CompareWidget from '../components/widgets/CompareWidget'
import CountImageWidget from '../components/widgets/CountImageWidget'
import MultipleChoiceWidget from '../components/widgets/MultipleChoiceWidget'
import NumberInputWidget from '../components/widgets/NumberInputWidget'
import NumberTreeWidget from '../components/widgets/NumberTreeWidget'
import type { ChildPart } from '../components/widgets/types'
import UnsupportedWidget from '../components/widgets/UnsupportedWidget'
import { newEventId } from '../ids'
import './ProblemPlayer.css'

// UX-DR7's literal timing: the "boop" plays, then the Hint (or Solution) appears after this
// gap, never together.
const WRONG_FEEDBACK_DELAY_MS = 400
// How long the correct-feedback banner/StarBurst show before auto-advancing (implementer's
// call, Boundaries & Constraints -- no fixed spec value for this one).
const CORRECT_ADVANCE_DELAY_MS = 1200

const PRAISE_KEYS = ['praise_1', 'praise_2', 'praise_3', 'praise_4', 'praise_5', 'praise_6'] as const

type Phase = 'answering' | 'submitting' | 'correct' | 'wrong-shake' | 'wrong-hint' | 'wrong-solution'

const NUMERIC_TYPES = new Set(['number_input', 'number_tree', 'count_image'])
const SUPPORTED_TYPES = new Set([
  'number_input',
  'compare',
  'multiple_choice',
  'number_tree',
  'count_image',
])

export interface ProblemPlayerProps {
  sessionId: string
  profileId: string
  bundleProblem: BundleProblemOut
  stars: number
  onStarEarned: () => void
  /** Called once the last Part of this Problem is finished (correctly answered, or an
   * unsupported Part skipped) -- the caller advances to the next Problem/chunk. */
  onDone: () => void
}

/** One Problem's worth of the real player (Story 2.6): owns only which Part of the Problem
 * is current. Everything about answering that ONE Part -- the widget switcher, ✔ Kiểm tra
 * gating, the Attempt submit flow, the correct/wrong-first/wrong-second feedback sequence --
 * lives in `PartPlayer` below, which is remounted (via its `key`) on every Part change. That
 * remount is a deliberate choice over a reset-`useEffect`: React's own guidance is that
 * "resetting state when a prop changes" is exactly what a `key` change is for, and a
 * `set-state-in-effect` reset here (tried first) is flagged by this repo's lint rule
 * (`react-hooks/set-state-in-effect`) as unnecessary cascading renders.
 */
export default function ProblemPlayer({
  sessionId,
  profileId,
  bundleProblem,
  stars,
  onStarEarned,
  onDone,
}: ProblemPlayerProps) {
  const problem = bundleProblem.problem
  const [partIndex, setPartIndex] = useState(0)
  const part = problem.parts[partIndex] as ChildPart | undefined

  if (!part) return null

  function advance() {
    if (partIndex + 1 < problem.parts.length) {
      setPartIndex((i) => i + 1)
    } else {
      onDone()
    }
  }

  return (
    <PartPlayer
      key={part.part_key}
      sessionId={sessionId}
      profileId={profileId}
      problem={problem}
      bundleProblem={bundleProblem}
      part={part}
      stars={stars}
      onStarEarned={onStarEarned}
      onAdvance={advance}
    />
  )
}

interface PartPlayerProps {
  sessionId: string
  profileId: string
  problem: ChildProblemView
  bundleProblem: BundleProblemOut
  part: ChildPart
  stars: number
  onStarEarned: () => void
  onAdvance: () => void
}

function PartPlayer({
  sessionId,
  profileId,
  problem,
  bundleProblem,
  part,
  stars,
  onStarEarned,
  onAdvance,
}: PartPlayerProps) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<string[]>([])
  const [activeSlot, setActiveSlot] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('answering')
  const [attemptResult, setAttemptResult] = useState<EventOut | null>(null)
  const [solutionRevealed, setSolutionRevealed] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [justEarned, setJustEarned] = useState(false)
  const [praiseKey, setPraiseKey] = useState<(typeof PRAISE_KEYS)[number]>(PRAISE_KEYS[0])
  // `count_image`'s tap-to-dot aid must reset per attempt (Boundaries & Constraints), not
  // only on a Part change -- bumped whenever a retry begins after a wrong attempt, and used
  // as `CountImageWidget`'s `key` below so a retry remounts it with empty dots.
  const [attemptSeq, setAttemptSeq] = useState(0)
  // Synchronous double-tap guard: `disabled` (derived from `phase` state) can lag a render
  // behind two back-to-back taps on ✔, and `newEventId()` mints a fresh id every call so the
  // backend's same-id dedup can't catch a resulting double-post. This ref is checked-and-set
  // before any state update, so a second tap within the same event-loop tick is a no-op.
  const submittingRef = useRef(false)

  const postEvent = usePostEvent(sessionId)
  const supported = SUPPORTED_TYPES.has(part.type)
  const disabled =
    phase === 'submitting' || phase === 'wrong-shake' || phase === 'wrong-solution' || phase === 'correct'

  function imageUrl(imageKey: string): string | undefined {
    const pages = new Set(problem.source_pages.map((p) => p.page))
    const prefixCount = pages.size > 1 ? 1 + pages.size : 1
    const tail = bundleProblem.crop_urls.slice(prefixCount)
    const index = problem.images.findIndex((i) => i.image_key === imageKey)
    return index === -1 ? undefined : tail[index]
  }

  function slotState(key: string): AnswerSlotState {
    if (phase === 'correct') return 'correct'
    if (phase === 'wrong-shake' || phase === 'wrong-hint' || phase === 'wrong-solution') {
      const wrongKeys = attemptResult?.wrong_keys ?? []
      return wrongKeys.length > 0 ? (wrongKeys.includes(key) ? 'wrong' : 'default') : 'wrong'
    }
    return key === activeSlot ? 'active' : 'default'
  }

  function retryIfSettled() {
    if (phase === 'wrong-hint') {
      setPhase('answering')
      setAttemptSeq((s) => s + 1)
      submittingRef.current = false
    }
  }

  function handleSlotTap(key: string) {
    if (disabled) return
    retryIfSettled()
    setActiveSlot(key)
  }

  function handleDigit(digit: string) {
    if (disabled || activeSlot == null) return
    retryIfSettled()
    setValues((prev) => ({ ...prev, [activeSlot]: (prev[activeSlot] ?? '') + digit }))
  }

  function handleBackspace() {
    if (disabled || activeSlot == null) return
    retryIfSettled()
    setValues((prev) => ({ ...prev, [activeSlot]: (prev[activeSlot] ?? '').slice(0, -1) }))
  }

  function handleToggleOption(key: string) {
    if (disabled || part.type !== 'multiple_choice') return
    retryIfSettled()
    const multi = part.multi
    setSelected((prev) => {
      if (prev.includes(key)) return prev.filter((k) => k !== key)
      return multi ? [...prev, key] : [key]
    })
  }

  function handleSetCompare(key: string, value: '<' | '=' | '>') {
    if (disabled) return
    retryIfSettled()
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  function slotKeysFor(): string[] {
    if (part.type === 'number_input') return part.slots.map((s) => s.slot_key)
    if (part.type === 'number_tree') {
      return part.nodes.filter((n) => n.given == null).map((n) => n.node_key)
    }
    if (part.type === 'compare') return part.rows.map((r) => r.slot_key)
    if (part.type === 'count_image') return part.slots.map((s) => s.slot_key)
    return []
  }

  function isComplete(): boolean {
    if (!supported) return false
    if (part.type === 'multiple_choice') return selected.length > 0
    return slotKeysFor().every((key) => (values[key] ?? '').trim() !== '')
  }

  function buildValue(): unknown {
    if (part.type === 'multiple_choice') return { selected }
    return slotKeysFor().map((key) => ({ key, value: values[key] ?? '' }))
  }

  async function handleCheck() {
    if (disabled || !isComplete()) return
    if (submittingRef.current) return
    submittingRef.current = true
    setPhase('submitting')
    setSubmitError(null)
    setJustEarned(false)
    try {
      const [result] = await postEvent.mutateAsync({
        profileId,
        events: [
          {
            id: newEventId(),
            kind: 'attempt',
            problem_id: problem.problem_id,
            payload: { part_key: part.part_key, value: buildValue() },
            occurred_at: new Date().toISOString(),
          },
        ],
      })
      setAttemptResult(result)
      if (result.correct) {
        setPhase('correct')
        onStarEarned()
        setJustEarned(true)
        void playChime()
        const chosen = PRAISE_KEYS[Math.floor(Math.random() * PRAISE_KEYS.length)]
        setPraiseKey(chosen)
        void speak(phrase(chosen))
        window.setTimeout(onAdvance, CORRECT_ADVANCE_DELAY_MS)
      } else {
        setPhase('wrong-shake')
        void playBoop()
        window.setTimeout(() => {
          if (result.solution) {
            setPhase('wrong-solution')
            setSolutionRevealed(1)
            void speak(result.solution.steps[0])
          } else {
            setPhase('wrong-hint')
            void speak(result.hint ?? '')
          }
        }, WRONG_FEEDBACK_DELAY_MS)
      }
    } catch (err) {
      setPhase('answering')
      setSubmitError(errorMessage(err))
      submittingRef.current = false
    }
  }

  function handleSolutionAdvance() {
    const steps = attemptResult?.solution?.steps ?? []
    if (solutionRevealed < steps.length) {
      const next = solutionRevealed + 1
      setSolutionRevealed(next)
      void speak(steps[next - 1])
    } else {
      onAdvance()
    }
  }

  function widget() {
    if (!supported) return <UnsupportedWidget type={part.type} />
    const shared = {
      values,
      selected,
      activeSlot,
      onSlotTap: handleSlotTap,
      onToggleOption: handleToggleOption,
      onSetCompare: handleSetCompare,
      slotState,
      disabled,
      imageUrl,
    }
    switch (part.type) {
      case 'number_input':
        return <NumberInputWidget {...shared} part={part} />
      case 'compare':
        return <CompareWidget {...shared} part={part} />
      case 'multiple_choice':
        return <MultipleChoiceWidget {...shared} part={part} />
      case 'number_tree':
        return <NumberTreeWidget {...shared} part={part} />
      case 'count_image':
        // `key={attemptSeq}` remounts the widget (clearing its local dots) on every retry
        // after a wrong attempt, not only on a Part change (finding #2).
        return <CountImageWidget key={attemptSeq} {...shared} part={part} />
      default:
        return <UnsupportedWidget type={part.type} />
    }
  }

  const showNumberPad = supported && NUMERIC_TYPES.has(part.type) && phase !== 'wrong-solution'
  const showCheck = supported && phase !== 'wrong-solution'

  return (
    <section className="problem-player" aria-label={problem.display_label || undefined}>
      <div className="problem-player-header">
        <StarBurst count={stars} justEarned={justEarned} />
      </div>
      <div className="problem-player-work">
        {problem.display_label && <h2 className="problem-player-label">{problem.display_label}</h2>}
        <p className="problem-player-prompt">{problem.instruction}</p>
        {part.prompt && <p className="problem-player-part-prompt">{part.prompt}</p>}
        {widget()}
        {submitError && (
          <p role="alert" className="form-error">
            {submitError}
          </p>
        )}
        {phase === 'wrong-hint' && attemptResult?.hint && <HintBubble text={attemptResult.hint} />}
        {phase === 'wrong-solution' && attemptResult?.solution && (
          <>
            <SolutionPanel steps={attemptResult.solution.steps} revealedCount={solutionRevealed} />
            <button type="button" className="problem-player-solution-next" onClick={handleSolutionAdvance}>
              {solutionRevealed < attemptResult.solution.steps.length ? 'Xem tiếp ➜' : `${phrase('next')} ➜`}
            </button>
          </>
        )}
      </div>
      <FeedbackBanner
        variant={phase === 'correct' ? 'correct' : 'retry'}
        visible={phase === 'correct' || phase === 'wrong-shake' || phase === 'wrong-hint'}
      >
        {phase === 'correct' ? phrase(praiseKey) : phase === 'wrong-hint' ? phrase('retry_first') : ''}
      </FeedbackBanner>
      {!supported ? (
        // An unsupported Part type has no widget to grade -- the only way forward is to
        // skip it (Boundaries & Constraints: reachable, never stranded).
        <div className="problem-player-actions">
          <button type="button" onClick={onAdvance}>
            Tiếp ➜
          </button>
        </div>
      ) : (
        phase !== 'wrong-solution' && (
          <div className="problem-player-actions">
            {showNumberPad && (
              <NumberPad
                onDigit={handleDigit}
                onBackspace={handleBackspace}
                showComma={false}
                disabled={disabled}
              />
            )}
            {showCheck && (
              <button type="button" disabled={disabled || !isComplete()} onClick={() => void handleCheck()}>
                {phrase('check_answer')}
              </button>
            )}
          </div>
        )
      )}
    </section>
  )
}
