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
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        // The API and data assets are served by FastAPI on the same origin; never
        // answer them with the cached app shell.
        navigateFallbackDenylist: [/^\/api(\/|$)/, /^\/assets-data\//, /^\/docs/, /^\/redoc/, /^\/openapi\.json$/],
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
