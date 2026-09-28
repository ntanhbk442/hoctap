import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMotion } from './useMotion'

function stubMatchMedia(initialMatches: boolean) {
  const listeners = new Set<(e: { matches: boolean }) => void>()
  let matches = initialMatches
  const mql = {
    get matches() {
      return matches
    },
    media: '(prefers-reduced-motion: reduce)',
    addEventListener: (_: string, listener: (e: { matches: boolean }) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_: string, listener: (e: { matches: boolean }) => void) => {
      listeners.delete(listener)
    },
  }
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mql),
  )
  return {
    fire: (next: boolean) => {
      matches = next
      act(() => {
        for (const listener of listeners) listener({ matches: next })
      })
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useMotion', () => {
  it('reads the initial prefers-reduced-motion value', () => {
    stubMatchMedia(true)
    const { result } = renderHook(() => useMotion())
    expect(result.current.reduced).toBe(true)
  })

  it('is reactive to a change event', () => {
    const { fire } = stubMatchMedia(false)
    const { result } = renderHook(() => useMotion())
    expect(result.current.reduced).toBe(false)
    fire(true)
    expect(result.current.reduced).toBe(true)
  })

  it('falls back to false when matchMedia is unavailable (SSR/test safety)', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { result } = renderHook(() => useMotion())
    expect(result.current.reduced).toBe(false)
  })
})
