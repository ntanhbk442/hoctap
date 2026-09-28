import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(QUERY).matches
}

/**
 * Reads `prefers-reduced-motion`, reactively. Every animated component (Star burst, feedback
 * banners, AnswerSlot's shake, ...) reads this hook rather than querying the media feature
 * itself, so tests mock one hook and every component's reduced-motion behaviour follows.
 *
 * Returns `false` (motion allowed) as a safe SSR/test fallback when `matchMedia` isn't
 * available, rather than throwing.
 */
export function useMotion(): { reduced: boolean } {
  const [reduced, setReduced] = useState(prefersReducedMotion)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(QUERY)
    const onChange = () => setReduced(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return { reduced }
}
