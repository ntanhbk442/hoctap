/// <reference types="vitest/config" />
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,

      pwaAssets: {
        disabled: false,
        config: true,
      },

      manifest: {
        name: 'Học Tập',
        short_name: 'Học Tập',
        description: 'Luyện Toán tiểu học',
        lang: 'vi',
        theme_color: '#ffffff',
      },

      workbox: {
        // `.woff2` already precaches the self-hosted Nunito fonts (Story 2.1); nothing to
        // add there. KaTeX is NOT precached here -- confirmed (Story 2.11) not actually a
        // dependency/integration anywhere in this codebase yet despite being named in the
        // architecture's stack table; see deferred-work.md rather than inventing one.
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        // The API and data assets are served by FastAPI on the same origin; never
        // answer them with the cached app shell.
        navigateFallbackDenylist: [/^\/api(\/|$)/, /^\/assets-data\//, /^\/docs/, /^\/redoc/, /^\/openapi\.json$/],
        // Story 2.11 (AD-10): a Session's Problem crop/page images and phrase/Problem audio
        // clips (`content.assets`/`content.speech`, all served under `/assets-data/*`) are
        // NOT part of this build's own output, so they can't be `globPatterns`-precached --
        // they're runtime-cached the first time each URL is fetched (either by
        // `offline/assetCache.ts`'s explicit warm on Session start, or an ordinary
        // `<img>`/`<audio>` tag), then served from cache thereafter.
        //
        // Split into two routes (2026-09-29 review fix, finding #3 -- the single combined
        // 30-day route previously here incorrectly claimed crops/pages were
        // content-addressed like audio): `content.speech`'s `/assets-data/audio/*` URLs
        // genuinely ARE content-addressed (`speech_key` hashes the spoken text + voice id --
        // see `content/speech.py`), so a stale cache entry there is provably impossible; a
        // long CacheFirst expiry is safe. `content.assets`' `/assets-data/crops/*` and
        // `/assets-data/pages/*` URLs (`content/assets.py`'s `crop_url()`/`page_url()`) are
        // keyed only by book/problem/page IDENTITY, not content -- a Problem re-extracted or
        // re-cropped after a device already cached its old image would serve the STALE image
        // for as long as this cache entry lives. Accepted as a known, low-frequency
        // limitation (re-extraction of already-published content is rare) rather than left
        // unaddressed: this route's `maxAgeSeconds` is kept much shorter (3 days) than
        // audio's, so a stale crop/page self-heals quickly rather than persisting for a
        // month.
        runtimeCaching: [
          {
            urlPattern: /^\/assets-data\/audio\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'assets-data-audio',
              expiration: {
                maxEntries: 1000,
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days -- safe: content-addressed by speech_key.
              },
            },
          },
          {
            urlPattern: /^\/assets-data\/(crops|pages)\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'assets-data-images',
              expiration: {
                maxEntries: 1000,
                // NOT content-addressed (identity-keyed) -- kept short so a re-extracted
                // Problem's stale cached image self-heals quickly. See comment above.
                maxAgeSeconds: 60 * 60 * 24 * 3, // 3 days
              },
            },
          },
        ],
      },

      devOptions: {
        enabled: false,
        navigateFallback: 'index.html',
        suppressWarnings: true,
        type: 'module',
      },
    }),
  ],
  server: {
    // `npm run dev` talks to `uv run hoctap serve` on port 8000.
    proxy: {
      '/api': 'http://localhost:8000',
      '/assets-data': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Unset by default. On a WSL /mnt/c checkout, one jsdom worker per core can time out
    // while starting; set e.g. VITEST_MAX_WORKERS=4 there.
    maxWorkers: process.env.VITEST_MAX_WORKERS ? Number(process.env.VITEST_MAX_WORKERS) : undefined,
  },
})
