import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// jsdom's `HTMLMediaElement` has no real network/playback: `play()`/`pause()` are stubbed
// no-ops (Chromium's own `Not implemented` warnings from `play()` are expected/benign, seen
// throughout Stories 2.6-2.8's test runs) and a real `error` event never fires on its own --
// tests dispatch it manually on the shared element itself, per this story's design (no
// separate injectable/mock element needed; `getAudioElement()` exposes the real one).
import {
  __resetAudioUnlockForTests,
  getAudioElement,
  getPlayerState,
  isAudioUnlocked,
  isMissing,
  playKey,
  stop,
  subscribe,
} from './player'

beforeEach(() => {
  __resetAudioUnlockForTests()
})

describe('shared audio element', () => {
  it('is a singleton -- the same element across calls', () => {
    expect(getAudioElement()).toBe(getAudioElement())
  })
})

describe('playKey / stop', () => {
  afterEach(() => {
    stop()
  })

  it('sets the player state to playing for the given key', async () => {
    await playKey('key-a', '/assets-data/audio/key-a.mp3')
    expect(getPlayerState()).toEqual({ key: 'key-a', status: 'playing' })
  })

  it('stops whatever was previously playing when a new clip starts', async () => {
    const el = getAudioElement()
    const pauseSpy = vi.spyOn(el, 'pause')
    await playKey('key-a', '/assets-data/audio/key-a.mp3')
    pauseSpy.mockClear()
    await playKey('key-b', '/assets-data/audio/key-b.mp3')
    expect(pauseSpy).toHaveBeenCalled()
    expect(getPlayerState()).toEqual({ key: 'key-b', status: 'playing' })
  })

  it('stop() pauses and resets to idle', async () => {
    await playKey('key-a', '/assets-data/audio/key-a.mp3')
    stop()
    expect(getPlayerState()).toEqual({ key: null, status: 'idle' })
  })

  it('notifies subscribers of state changes', async () => {
    const listener = vi.fn()
    const unsubscribe = subscribe(listener)
    await playKey('key-a', '/assets-data/audio/key-a.mp3')
    expect(listener).toHaveBeenCalledWith({ key: 'key-a', status: 'playing' })
    unsubscribe()
    listener.mockClear()
    stop()
    expect(listener).not.toHaveBeenCalled()
  })
})

describe('missing-file detection', () => {
  afterEach(() => {
    stop()
  })

  it('marks the key missing when the shared element fires its own error event', async () => {
    await playKey('missing-key', '/assets-data/audio/missing-key.mp3')
    expect(isMissing('missing-key')).toBe(false)

    const el = getAudioElement()
    el.dispatchEvent(new Event('error'))

    expect(isMissing('missing-key')).toBe(true)
    expect(getPlayerState()).toEqual({ key: 'missing-key', status: 'missing' })
  })

  it('does not mark a different, still-idle key as missing', async () => {
    await playKey('key-a', '/assets-data/audio/key-a.mp3')
    const el = getAudioElement()
    el.dispatchEvent(new Event('error'))
    expect(isMissing('key-b')).toBe(false)
  })

  // Finding #2: `playKey()` itself triggers `MEDIA_ERR_ABORTED` (code 1) by swapping `src`
  // mid-load when a new clip interrupts an in-flight one -- that must never poison
  // `missingKeys` (which is remembered forever), or a perfectly playable clip would grey out
  // 🔊 for the rest of the page session.
  // jsdom's `HTMLMediaElement` doesn't implement `error` at all (it's `undefined`, not even
  // a defined accessor -- confirmed by inspection), so tests set it directly via a narrow
  // cast, the same "dispatch a synthetic event on the real element" approach this file
  // already uses for `error`/`ended`.
  function setMediaErrorCode(el: HTMLAudioElement, code: number): void {
    ;(el as unknown as { error: MediaError | null }).error = { code } as MediaError
  }

  it('does NOT mark a key missing when the error is MEDIA_ERR_ABORTED (an interrupted load)', async () => {
    await playKey('aborted-key', '/assets-data/audio/aborted-key.mp3')
    const el = getAudioElement()
    setMediaErrorCode(el, 1) // MEDIA_ERR_ABORTED
    el.dispatchEvent(new Event('error'))
    expect(isMissing('aborted-key')).toBe(false)
    expect(getPlayerState()).toEqual({ key: 'aborted-key', status: 'playing' })
  })

  it('DOES mark a key missing on a genuine decode/not-found failure (MEDIA_ERR_SRC_NOT_SUPPORTED)', async () => {
    await playKey('really-missing-key', '/assets-data/audio/really-missing-key.mp3')
    const el = getAudioElement()
    setMediaErrorCode(el, 4) // MEDIA_ERR_SRC_NOT_SUPPORTED
    el.dispatchEvent(new Event('error'))
    expect(isMissing('really-missing-key')).toBe(true)
    expect(getPlayerState()).toEqual({ key: 'really-missing-key', status: 'missing' })
  })

  it('going idle via ended does not report missing', async () => {
    await playKey('key-c', '/assets-data/audio/key-c.mp3')
    const el = getAudioElement()
    el.dispatchEvent(new Event('ended'))
    expect(getPlayerState()).toEqual({ key: 'key-c', status: 'idle' })
    expect(isMissing('key-c')).toBe(false)
  })
})

describe('audio unlock tracking', () => {
  it('starts locked', () => {
    expect(isAudioUnlocked()).toBe(false)
  })

  it('unlocks on the first pointerdown anywhere', () => {
    window.dispatchEvent(new Event('pointerdown'))
    expect(isAudioUnlocked()).toBe(true)
  })

  it('unlocks on the first click anywhere', () => {
    window.dispatchEvent(new Event('click'))
    expect(isAudioUnlocked()).toBe(true)
  })

  it('stays unlocked once set', () => {
    window.dispatchEvent(new Event('pointerdown'))
    window.dispatchEvent(new Event('pointerdown'))
    expect(isAudioUnlocked()).toBe(true)
  })
})
