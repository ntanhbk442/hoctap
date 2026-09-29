import { useEffect, useRef, useState } from 'react'
import type { BundleProblemOut, ChildProblemView, EventOut } from '../api/client'
import { errorMessage } from '../api/errors'
import { usePostEvent } from '../api/queries'
import {
  getPlayerState,
  isAudioUnlocked,
  isMissing,
  stop as stopAudio,
  subscribe as subscribePlayer,
  type PlayerState,
} from '../audio/player'
import { phrase } from '../audio/phrases'
import { playBoop, playChime } from '../audio/sfx'
import { speak, speechKey } from '../audio/speech'
import type { AnswerSlotState } from '../components/AnswerSlot/AnswerSlot'
import FeedbackBanner from '../components/FeedbackBanner/FeedbackBanner'
import HintBubble from '../components/HintBubble/HintBubble'
import NumberPad from '../components/NumberPad/NumberPad'
import SolutionPanel from '../components/SolutionPanel/SolutionPanel'
import SpeakerButton from '../components/SpeakerButton/SpeakerButton'
import StarBurst from '../components/StarBurst/StarBurst'
import CompareWidget from '../components/widgets/CompareWidget'
import ConnectDotsWidget from '../components/widgets/ConnectDotsWidget'
import CountImageWidget from '../components/widgets/CountImageWidget'
import DotDrawWidget from '../components/widgets/DotDrawWidget'
import GridFillWidget from '../components/widgets/GridFillWidget'
import ImageSelectWidget from '../components/widgets/ImageSelectWidget'
import MatchWidget from '../components/widgets/MatchWidget'
import MultipleChoiceWidget from '../components/widgets/MultipleChoiceWidget'
import NumberInputWidget from '../components/widgets/NumberInputWidget'
import NumberTreeWidget from '../components/widgets/NumberTreeWidget'
import OrderWidget from '../components/widgets/OrderWidget'
import SpotDifferenceWidget from '../components/widgets/SpotDifferenceWidget'
import FallbackWidget from '../components/widgets/FallbackWidget'
import type { ChildPart } from '../components/widgets/types'
import UnsupportedWidget from '../components/widgets/UnsupportedWidget'
import { newEventId } from '../ids'
import { QueuedOfflineError } from '../offline/outbox'
import './ProblemPlayer.css'

// UX-DR7's literal timing: the "boop" plays, then the Hint (or Solution) appears after this
// gap, never together.
const WRONG_FEEDBACK_DELAY_MS = 400
// How long the correct-feedback banner/StarBurst show before auto-advancing (implementer's
// call, Boundaries & Constraints -- no fixed spec value for this one).
const CORRECT_ADVANCE_DELAY_MS = 1200

const PRAISE_KEYS = ['praise_1', 'praise_2', 'praise_3', 'praise_4', 'praise_5', 'praise_6'] as const

type Phase = 'answering' | 'submitting' | 'correct' | 'wrong-shake' | 'wrong-hint' | 'wrong-solution'

// `grid_fill` joins these three: it's the same tap-a-slot-then-`NumberPad` shape as
// `number_input`/`number_tree`, just laid out as a grid (Story 2.7).
const NUMERIC_TYPES = new Set(['number_input', 'number_tree', 'count_image', 'grid_fill'])
const SUPPORTED_TYPES = new Set([
  'number_input',
  'compare',
  'multiple_choice',
  'number_tree',
  'count_image',
  // Story 2.7's 7 additions.
  'order',
  'grid_fill',
  'match',
  'image_select',
  'dot_draw',
  'connect_dots',
  'spot_difference',
])
// All-or-nothing types (Story 2.7): `multiple_choice`/`image_select` share `selected`;
// `order`/`match`/`connect_dots`/`spot_difference` each get their own lifted state below.

export interface ProblemPlayerProps {
  sessionId: string
  profileId: string
  bundleProblem: BundleProblemOut
  stars: number
  onStarEarned: () => void
  /** Called once the last Part of this Problem is finished (correctly answered, or an
   * unsupported Part skipped) -- the caller advances to the next Problem/chunk. */
  onDone: () => void
  /** The current Profile's `auto_play` setting (Story 2.9). Defaults `true` so existing
   * callers/tests that don't pass it keep the pre-Story-2.9 auto-play-on behaviour. */
  autoPlay?: boolean
  /** Story 2.11: called instead of showing a normal `submitError` when an event got
   * queued to the offline outbox (`QueuedOfflineError`) -- the caller (`SessionPlayer`)
   * shows the "Máy tính bảng chưa kết nối…" screen in place of this whole Problem. Optional
   * (defaults to a no-op) so existing tests that don't exercise the offline path are
   * unaffected. */
  onOffline?: () => void
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
  autoPlay = true,
  onOffline = () => {},
}: ProblemPlayerProps) {
  const problem = bundleProblem.problem
  const [partIndex, setPartIndex] = useState(0)
  const part = problem.parts[partIndex] as ChildPart | undefined

  // Story 2.9: auto-play the Problem's instruction once when it opens -- this component is
  // remounted per Problem (see `SessionPlayer`'s `key={problems[...].problem.problem_id}`),
  // never per Part, so an empty-deps effect here fires exactly once per Problem open, not on
  // every Part advance. Gated on both `autoPlay` (the Profile's setting) and the page having
  // been unlocked by a user gesture already (Boundaries & Constraints: never attempted, never
  // retried, before unlock). The cleanup stops the shared player on unmount -- covers both a
  // Part-to-Part remount lower in the tree and leaving the Session entirely.
  useEffect(() => {
    if (autoPlay && isAudioUnlocked()) {
      void speak(problem.instruction)
    }
    return () => stopAudio()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally once per Problem
  }, [])

  if (!part) return null

  function advance() {
    if (partIndex + 1 < problem.parts.length) {
      setPartIndex((i) => i + 1)
    } else {
      onDone()
    }
  }

  // `fallback` (Story 2.8, FR-11) has no machine-gradable answer at all -- its "Xem đáp
  // án" -> self-mark flow is fundamentally not the shared ✔ Kiểm tra/Attempt shape every
  // other Part type here uses, so it gets its own dedicated player rather than another
  // branch bolted onto `PartPlayer`'s already-large state machine.
  if (part.type === 'fallback') {
    return (
      <FallbackPartPlayer
        key={part.part_key}
        sessionId={sessionId}
        profileId={profileId}
        problem={problem}
        bundleProblem={bundleProblem}
        part={part}
        stars={stars}
        onStarEarned={onStarEarned}
        onAdvance={advance}
        onOffline={onOffline}
      />
    )
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
      onOffline={onOffline}
    />
  )
}

/** Story 2.9, finding #1: the Problem instruction's own 🔊, wired to `audio/player.ts`'s real
 * subscribable state -- not just built-and-unit-tested at the `SpeakerButton` level, but
 * actually reachable from the running Problem screen. `playing` is true while this exact
 * instruction's `speechKey()` is the one the shared player is currently playing (covers both
 * the auto-play-on-open effect above AND this button's own manual tap, since both ultimately
 * call `player.ts`'s `playKey()` -- the auto-play effect via `speak()`, and this tap via the
 * same `speak()` call). `missing` reflects `isMissing()` once the key is known. Shared by
 * `PartPlayer` and `FallbackPartPlayer` below, which both render the same instruction line. */
function InstructionLine({ instruction }: { instruction: string }) {
  const [instructionKey, setInstructionKey] = useState<string | null>(null)
  const [playerState, setPlayerState] = useState<PlayerState>(() => getPlayerState())

  useEffect(() => {
    let cancelled = false
    void speechKey(instruction).then((key) => {
      if (!cancelled) setInstructionKey(key)
    })
    return () => {
      cancelled = true
    }
  }, [instruction])

  useEffect(() => subscribePlayer(setPlayerState), [])

  const playing =
    instructionKey !== null && playerState.key === instructionKey && playerState.status === 'playing'
  const missing = instructionKey !== null && isMissing(instructionKey)

  return (
    <div className="problem-player-instruction-row">
      <p className="problem-player-prompt">{instruction}</p>
      <SpeakerButton
        label={instruction}
        playing={playing}
        missing={missing}
        onClick={() => void speak(instruction)}
      />
    </div>
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
  onOffline: () => void
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
  onOffline,
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
  // Story 2.7's per-type lifted state (these ARE the graded answer for their type, unlike
  // `count_image`'s dots above, so they persist across a retry exactly like `values`/
  // `selected` do -- no `attemptSeq` remount for any of these).
  const [pairs, setPairs] = useState<Record<string, string>>({})
  const [pickedItem, setPickedItem] = useState<string | null>(null)
  const [sequence, setSequence] = useState<number[]>([])
  const [foundRegions, setFoundRegions] = useState<string[]>([])
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
    if (disabled || (part.type !== 'multiple_choice' && part.type !== 'image_select')) return
    retryIfSettled()
    // `'multi' in part` (not a `part.type` narrowing) since this now covers two Part
    // types that both happen to carry the same `multi: boolean` field.
    const multi = 'multi' in part && part.multi
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

  // `order`/`match`: pick up (or put back down) an item/tile -- the tap-alternative's
  // first step, shared by both types (Boundaries & Constraints: never drag-only).
  function handlePickItem(itemKey: string) {
    if (disabled) return
    retryIfSettled()
    setPickedItem((prev) => (prev === itemKey ? null : itemKey))
  }

  // `order`: place the picked item (or an explicit drag-and-drop `itemKey`) into a position
  // slot, first clearing it from wherever it was (a permutation, never in two slots at
  // once). Tapping a FILLED slot with nothing picked instead picks that slot's item back up.
  function handlePlaceItem(slotKey: string, itemKey?: string) {
    if (disabled) return
    retryIfSettled()
    const item = itemKey ?? pickedItem
    if (!item) {
      const current = values[slotKey]
      if (current) {
        setValues((prev) => {
          const next = { ...prev }
          delete next[slotKey]
          return next
        })
        setPickedItem(current)
      }
      return
    }
    setValues((prev) => {
      const next = { ...prev }
      for (const k of Object.keys(next)) {
        if (next[k] === item) delete next[k]
      }
      next[slotKey] = item
      return next
    })
    setPickedItem(null)
  }

  // `match`: pair the currently picked left item with this right item. No-op if nothing
  // is picked (tapping a right item first, before any left item, per the I/O matrix).
  function handlePairRight(rightKey: string) {
    if (disabled || !pickedItem) return
    retryIfSettled()
    setPairs((prev) => ({ ...prev, [pickedItem]: rightKey }))
    setPickedItem(null)
  }

  function handleRemovePair(leftKey: string) {
    if (disabled) return
    retryIfSettled()
    setPairs((prev) => {
      const next = { ...prev }
      delete next[leftKey]
      return next
    })
  }

  // `dot_draw`: the box's resulting dot count is set directly (not via `NumberPad` digits).
  function handleSetValue(key: string, value: string) {
    if (disabled) return
    retryIfSettled()
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  // `connect_dots`: only the correct next dot is ever appended to `sequence` -- a tap out
  // of order is rejected here, BEFORE any state change, so it can never itself become an
  // Attempt (Boundaries & Constraints' explicit acceptance criterion for this type).
  function handleTapDot(n: number): boolean {
    if (disabled || n !== sequence.length + 1) return false
    retryIfSettled()
    setSequence((prev) => [...prev, n])
    return true
  }

  // `spot_difference`: only a genuinely NEW found region is appended -- a duplicate tap
  // (already found) is rejected here, before any state change, same "never itself an
  // Attempt" rule as `connect_dots` above.
  function handleFoundRegion(key: string): boolean {
    if (disabled || foundRegions.includes(key)) return false
    retryIfSettled()
    setFoundRegions((prev) => [...prev, key])
    return true
  }

  function slotKeysFor(): string[] {
    if (part.type === 'number_input') return part.slots.map((s) => s.slot_key)
    if (part.type === 'number_tree') {
      return part.nodes.filter((n) => n.given == null).map((n) => n.node_key)
    }
    if (part.type === 'compare') return part.rows.map((r) => r.slot_key)
    if (part.type === 'count_image') return part.slots.map((s) => s.slot_key)
    if (part.type === 'order') return part.items.map((_, i) => `pos${i}`)
    if (part.type === 'grid_fill') {
      const keys: string[] = []
      part.cells.forEach((row, i) => {
        row.forEach((cell, j) => {
          if (cell.given == null) keys.push(`r${i}c${j}`)
        })
      })
      return keys
    }
    if (part.type === 'dot_draw') return part.boxes.map((b) => b.slot_key)
    return []
  }

  function isComplete(): boolean {
    if (!supported) return false
    if (part.type === 'multiple_choice' || part.type === 'image_select') return selected.length > 0
    if (part.type === 'match') return Object.keys(pairs).length === part.left.length
    if (part.type === 'connect_dots') return sequence.length === part.dots.length
    if (part.type === 'spot_difference') return foundRegions.length === part.count
    return slotKeysFor().every((key) => (values[key] ?? '').trim() !== '')
  }

  function buildValue(): unknown {
    if (part.type === 'multiple_choice' || part.type === 'image_select') return { selected }
    if (part.type === 'order') return { order: part.items.map((_, i) => values[`pos${i}`] ?? '') }
    if (part.type === 'match') return { pairs: Object.entries(pairs) }
    if (part.type === 'connect_dots') return { sequence }
    if (part.type === 'spot_difference') return { region_keys: foundRegions }
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
      submittingRef.current = false
      if (err instanceof QueuedOfflineError) {
        // No local grading, ever (Boundaries & Constraints): the attempt was queued, not
        // graded, so this Part is left exactly as it was for the child to answer -- the
        // parent replaces the whole screen with the offline screen instead.
        setPhase('answering')
        onOffline()
        return
      }
      setPhase('answering')
      setSubmitError(errorMessage(err))
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
      pairs,
      pickedItem,
      onPickItem: handlePickItem,
      onPlaceItem: handlePlaceItem,
      onPairRight: handlePairRight,
      onRemovePair: handleRemovePair,
      onSetValue: handleSetValue,
      sequence,
      onTapDot: handleTapDot,
      foundRegions,
      onFoundRegion: handleFoundRegion,
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
      case 'order':
        return <OrderWidget {...shared} part={part} />
      case 'grid_fill':
        return <GridFillWidget {...shared} part={part} />
      case 'match':
        return <MatchWidget {...shared} part={part} />
      case 'image_select':
        return <ImageSelectWidget {...shared} part={part} />
      case 'dot_draw':
        return <DotDrawWidget {...shared} part={part} />
      case 'connect_dots':
        return <ConnectDotsWidget {...shared} part={part} />
      case 'spot_difference':
        return <SpotDifferenceWidget {...shared} part={part} />
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
        <InstructionLine instruction={problem.instruction} />
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

type FallbackChildPart = Extract<ChildPart, { type: 'fallback' }>

type FallbackPhase = 'crop' | 'revealing' | 'self-marking' | 'correct' | 'neutral'

interface FallbackPartPlayerProps {
  sessionId: string
  profileId: string
  problem: ChildProblemView
  bundleProblem: BundleProblemOut
  part: FallbackChildPart
  stars: number
  onStarEarned: () => void
  onAdvance: () => void
  onOffline: () => void
}

/** Story 2.8's fallback self-check: "Xem đáp án" reveals the Solution (posting
 * `fallback_revealed`, whose response carries the Part's own `solution` -- see
 * `learning/sessions.py`'s `_fallback_solution()` -- since the child_view bundle never
 * does), then "Em làm đúng"/"Em chưa đúng" self-reports (posting `self_marked`) before
 * advancing. Never calls `grade_part()`/an `attempt` event at all -- a fallback Problem's
 * `answer` is always `None` (Boundaries & Constraints). */
function FallbackPartPlayer({
  sessionId,
  profileId,
  problem,
  bundleProblem,
  part,
  stars,
  onStarEarned,
  onAdvance,
  onOffline,
}: FallbackPartPlayerProps) {
  const [phase, setPhase] = useState<FallbackPhase>('crop')
  const [solutionSteps, setSolutionSteps] = useState<string[]>([])
  const [solutionRevealed, setSolutionRevealed] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [justEarned, setJustEarned] = useState(false)
  const [praiseKey, setPraiseKey] = useState<(typeof PRAISE_KEYS)[number]>(PRAISE_KEYS[0])
  const submittingRef = useRef(false)
  const postEvent = usePostEvent(sessionId)

  function imageUrl(imageKey: string): string | undefined {
    const pages = new Set(problem.source_pages.map((p) => p.page))
    const prefixCount = pages.size > 1 ? 1 + pages.size : 1
    const tail = bundleProblem.crop_urls.slice(prefixCount)
    const index = problem.images.findIndex((i) => i.image_key === imageKey)
    return index === -1 ? undefined : tail[index]
  }

  async function handleShowAnswer() {
    if (submittingRef.current) return
    submittingRef.current = true
    setSubmitError(null)
    try {
      const [result] = await postEvent.mutateAsync({
        profileId,
        events: [
          {
            id: newEventId(),
            kind: 'fallback_revealed',
            problem_id: problem.problem_id,
            payload: { part_key: part.part_key },
            occurred_at: new Date().toISOString(),
          },
        ],
      })
      const steps = result.solution?.steps ?? []
      setSolutionSteps(steps)
      setPhase('revealing')
      if (steps.length > 0) {
        setSolutionRevealed(1)
        void speak(steps[0])
      } else {
        setSolutionRevealed(0)
      }
    } catch (err) {
      if (err instanceof QueuedOfflineError) {
        onOffline()
      } else {
        setSubmitError(errorMessage(err))
      }
    } finally {
      submittingRef.current = false
    }
  }

  function handleSolutionAdvance() {
    if (solutionRevealed < solutionSteps.length) {
      const next = solutionRevealed + 1
      setSolutionRevealed(next)
      void speak(solutionSteps[next - 1])
    } else {
      setPhase('self-marking')
    }
  }

  async function handleSelfMark(correct: boolean) {
    if (submittingRef.current) return
    submittingRef.current = true
    setSubmitError(null)
    try {
      await postEvent.mutateAsync({
        profileId,
        events: [
          {
            id: newEventId(),
            kind: 'self_marked',
            problem_id: problem.problem_id,
            payload: { correct },
            occurred_at: new Date().toISOString(),
          },
        ],
      })
      if (correct) {
        setPhase('correct')
        onStarEarned()
        setJustEarned(true)
        void playChime()
        const chosen = PRAISE_KEYS[Math.floor(Math.random() * PRAISE_KEYS.length)]
        setPraiseKey(chosen)
        void speak(phrase(chosen))
      } else {
        setPhase('neutral')
        void speak(phrase('self_mark_neutral_ack'))
      }
      window.setTimeout(onAdvance, CORRECT_ADVANCE_DELAY_MS)
    } catch (err) {
      submittingRef.current = false
      if (err instanceof QueuedOfflineError) {
        onOffline()
        return
      }
      setSubmitError(errorMessage(err))
    }
  }

  const showingSolution = phase === 'revealing' || phase === 'self-marking'

  return (
    <section className="problem-player" aria-label={problem.display_label || undefined}>
      <div className="problem-player-header">
        <StarBurst count={stars} justEarned={justEarned} />
      </div>
      <div className="problem-player-work">
        {problem.display_label && <h2 className="problem-player-label">{problem.display_label}</h2>}
        <InstructionLine instruction={problem.instruction} />
        {part.prompt && <p className="problem-player-part-prompt">{part.prompt}</p>}
        <FallbackWidget part={part} imageUrl={imageUrl} />
        {submitError && (
          <p role="alert" className="form-error">
            {submitError}
          </p>
        )}
        {showingSolution && (
          <>
            <SolutionPanel steps={solutionSteps} revealedCount={solutionRevealed} />
            {phase === 'revealing' && (
              <button type="button" className="problem-player-solution-next" onClick={handleSolutionAdvance}>
                {solutionRevealed < solutionSteps.length ? 'Xem tiếp ➜' : `${phrase('next')} ➜`}
              </button>
            )}
          </>
        )}
      </div>
      <FeedbackBanner
        variant={phase === 'correct' ? 'correct' : 'neutral'}
        visible={phase === 'correct' || phase === 'neutral'}
      >
        {phase === 'correct' ? phrase(praiseKey) : phase === 'neutral' ? phrase('self_mark_neutral_ack') : ''}
      </FeedbackBanner>
      <div className="problem-player-actions">
        {phase === 'crop' && (
          <button type="button" onClick={() => void handleShowAnswer()}>
            {phrase('show_answer')}
          </button>
        )}
        {phase === 'self-marking' && (
          <>
            <button type="button" onClick={() => void handleSelfMark(false)}>
              {phrase('self_mark_incorrect')}
            </button>
            <button type="button" onClick={() => void handleSelfMark(true)}>
              {phrase('self_mark_correct')}
            </button>
          </>
        )}
      </div>
    </section>
  )
}
