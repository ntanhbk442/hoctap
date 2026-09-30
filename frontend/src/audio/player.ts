// Story 2.9's shared audio player: exactly ONE `<audio>` element, reused across every
// `speak()`/`SpeakerButton` call in the app (UX-DR7's "stop the previous clip when a new
// one starts or the screen changes"), instead of `speech.ts`'s old one-`Audio`-per-call
// behaviour. `speech.ts`'s `speak()` is the only intended entry point for existing callers
// (HintBubble/SolutionPanel/long-press-to-speak/etc.) -- this module is the shared internals
// it (and `SpeakerButton`/`ProblemPlayer`, which need to react to real player state) sit on.

export type PlayerStatus = 'idle' | 'playing' | 'missing'

export interface PlayerState {
  /** The `speechKey()` of the clip currently playing/last attempted, or `null` when idle. */
  key: string | null
  status: PlayerStatus
}

type Listener = (state: PlayerState) => void

let audioEl: HTMLAudioElement | null = null
let state: PlayerState = { key: null, status: 'idle' }
const listeners = new Set<Listener>()
// A pending `speak()` (still hashing its key) must not start a clip after `stop()` -- e.g.
// the Problem it belonged to unmounted -- or after a newer `speak()` superseded it.
let speakEpoch = 0
// Keys the shared element's own `error` event has confirmed missing (404/decode failure) --
// distinct from "not playing yet", per the Boundaries & Constraints' grey-out rule. Never
// cleared: a key is content-addressed (AD-8), so a confirmed-missing clip stays missing for
// the lifetime of the page.
const missingKeys = new Set<string>()

function setState(next: PlayerState): void {
  state = next
  for (const listener of listeners) listener(state)
}

/** The shared `<audio>` element, created lazily on first use. Exported so tests can dispatch
 * synthetic `error`/`ended` events on the real element (jsdom's `HTMLMediaElement` has no
 * real network/playback, so an actual 404 never fires -- see this story's Implementation
 * Notes) without needing a separate injectable/mock element. */
export function getAudioElement(): HTMLAudioElement {
  if (!audioEl) {
    audioEl = new Audio()
    audioEl.addEventListener('ended', () => {
      if (state.status === 'playing') setState({ key: state.key, status: 'idle' })
    })
    audioEl.addEventListener('error', () => {
      // A `src=''`/initial-state error (no clip ever asked for) is not a "missing file" --
      // only mark the key we were actually trying to play.
      if (state.key === null) return
      // Only a genuine "cannot load/decode this clip" failure marks it missing:
      // `MEDIA_ERR_SRC_NOT_SUPPORTED` (code 4, what a 404 or an undecodable file reports).
      // `MEDIA_ERR_ABORTED` (code 1, `playKey()` swapping `src` mid-load) and
      // `MEDIA_ERR_NETWORK` (code 2, a dropped connection -- the clip may well exist) must
      // never poison `missingKeys`, which is remembered for the page's lifetime. `MediaError`
      // isn't a global in every test environment, so the spec's numeric constant is used.
      const MEDIA_ERR_SRC_NOT_SUPPORTED = 4
      if (audioEl?.error?.code !== MEDIA_ERR_SRC_NOT_SUPPORTED) return
      missingKeys.add(state.key)
      setState({ key: state.key, status: 'missing' })
    })
  }
  return audioEl
}

export function getPlayerState(): PlayerState {
  return state
}

/** True once the element's `error` event has confirmed `key`'s clip is missing. */
export function isMissing(key: string): boolean {
  return missingKeys.has(key)
}

/** Subscribes to player state changes (key/status). Returns an unsubscribe function --
 * `SpeakerButton`/`ProblemPlayer` call this in a `useEffect` and clean up on unmount. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Stops whatever is currently playing on the shared element (a new clip starting, or the
 * caller leaving the screen it was playing on) -- `pause()` + reset, never a new element. */
export function stop(): void {
  speakEpoch += 1
  const el = getAudioElement()
  el.pause()
  el.currentTime = 0
  setState({ key: null, status: 'idle' })
}

/** Plays `url` (keyed by `key`, e.g. a `speechKey()` result) on the shared element, stopping
 * whatever was previously playing first. Resolves once `play()` itself resolves (playback
 * has started) -- a later `error` event (missing file) or `ended` is reported asynchronously
 * via `subscribe`, never by rejecting this promise; `speak()` in `speech.ts` is the
 * silent-no-op wrapper existing callers use directly. */
export async function playKey(key: string, url: string): Promise<void> {
  speakEpoch += 1
  const el = getAudioElement()
  el.pause()
  el.currentTime = 0
  el.src = url
  setState({ key, status: 'playing' })
  try {
    await el.play()
  } catch (err) {
    // Playback never started (blocked, aborted by a newer clip, ...): don't stay "playing".
    if (state.key === key && state.status === 'playing') setState({ key, status: 'idle' })
    throw err
  }
}

/** Starts a `speak()` request; pass the result to `isSpeakCurrent()` before playing. */
export function beginSpeak(): number {
  speakEpoch += 1
  return speakEpoch
}

/** False once `stop()`, `playKey()` or another `beginSpeak()` ran after `ticket` was issued. */
export function isSpeakCurrent(ticket: number): boolean {
  return ticket === speakEpoch
}

// --- Audio unlock tracking ---
//
// Browsers block audio playback until the page has received at least one user gesture.
// `frontend/src/App.tsx` has no existing app-wide gesture listener (checked before adding
// this), so this module owns a single first-`pointerdown`-or-`click`-anywhere flag, set once
// for the lifetime of the page (matching the module-level singleton pattern already used for
// the shared `<audio>` element above).
let unlocked = false

function handleFirstGesture(): void {
  unlocked = true
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointerdown', handleFirstGesture)
    window.removeEventListener('click', handleFirstGesture)
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('pointerdown', handleFirstGesture, { once: true })
  window.addEventListener('click', handleFirstGesture, { once: true })
}

/** True once the page has received at least one user gesture anywhere. Auto-play must never
 * be attempted before this (Boundaries & Constraints). */
export function isAudioUnlocked(): boolean {
  return unlocked
}

/** Test-only: resets the unlock flag and re-arms the listeners, so a "not yet unlocked" case
 * can be exercised even though `unlocked` is otherwise a page-lifetime-once flag. Not used by
 * app code. */
export function __resetAudioUnlockForTests(): void {
  unlocked = false
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointerdown', handleFirstGesture)
    window.removeEventListener('click', handleFirstGesture)
    window.addEventListener('pointerdown', handleFirstGesture, { once: true })
    window.addEventListener('click', handleFirstGesture, { once: true })
  }
}
