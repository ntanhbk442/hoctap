import type { BundleOut } from '../api/client'

/**
 * Warms the Workbox `/assets-data/*` runtime cache (`vite.config.ts`'s `runtimeCaching`
 * route, CacheFirst) with a Session bundle's crop/page/audio URLs as soon as it's fetched
 * (Story 2.11, AD-10) -- so the REST of that chunk stays available if connectivity drops
 * mid-Session, not just whichever Problem/audio the child already happened to view. The
 * route itself does the actual caching; this only needs to trigger one `fetch()` per URL
 * (every fetch is intercepted by the Service Worker's route regardless of who issued it,
 * including this call) -- a plain `<img>`/`<audio>` tag rendering the current Problem
 * would eventually do the same for THAT Problem's assets alone, but not for the rest of
 * the chunk not yet on screen.
 *
 * A no-op outside a Service-Worker-capable browser, and every per-URL failure is swallowed
 * -- this is a best-effort warm, never something that should block or fail the Session
 * (e.g. genuinely offline: the fetches simply fail and nothing is warmed, which is exactly
 * the state the Session was already in).
 */
export function cacheBundleAssets(bundle: BundleOut): void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return
  const urls = new Set<string>()
  for (const p of bundle.problems) {
    for (const u of p.crop_urls) urls.add(u)
    for (const u of p.page_urls) urls.add(u)
    for (const u of Object.values(p.audio)) urls.add(u)
  }
  for (const url of urls) {
    void fetch(url).catch(() => {})
  }
}
