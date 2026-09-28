import type { ProblemDoc } from '../../api/client'

/**
 * Maps each image_key of a ProblemDoc to its crop URL, mirroring the backend's
 * `problem_crop_urls` ordering: the whole-Problem crop(s) first, then one per image.
 */
export function cropUrlByImageKey(doc: ProblemDoc, cropUrls: string[]): Map<string, string> {
  const pages = Array.from(new Set(doc.source_pages.map((p) => p.page))).sort((a, b) => a - b)
  const names = [
    '_problem',
    ...(pages.length > 1 ? pages.map((n) => `_problem_p${n}`) : []),
    ...doc.images.map((i) => i.image_key),
  ]
  const map = new Map<string, string>()
  names.forEach((name, i) => {
    const url = cropUrls[i]
    if (url) map.set(name, url)
  })
  return map
}

/** Whether this Part's Answer Key is a set of image regions or points, unreadable as text alone. */
export function needsOverlay(type: string): boolean {
  return type === 'image_select' || type === 'connect_dots' || type === 'spot_difference'
}
