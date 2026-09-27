// Generates src/api/schema.d.ts from the backend OpenAPI schema.
// Source: the running server (HOCTAP_OPENAPI_URL, default http://localhost:8000/openapi.json),
// falling back to ./openapi.json written by `uv run hoctap export-openapi` (offline).
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const url = process.env.HOCTAP_OPENAPI_URL ?? 'http://localhost:8000/openapi.json'
const file = join(root, 'openapi.json')
const out = join(root, 'src', 'api', 'schema.d.ts')

async function live() {
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(2000) })
    return resp.ok ? url : null
  } catch {
    return null
  }
}

const source = (await live()) ?? (existsSync(file) ? file : null)
if (!source) {
  console.error(
    `gen:api: no schema. Start the backend (uv run hoctap serve) or run ` +
      `\`uv run hoctap export-openapi\` in backend/ to write ${file}.`,
  )
  process.exit(1)
}
console.log(`gen:api: using ${source}`)

const require = createRequire(import.meta.url)
const cli = join(dirname(require.resolve('openapi-typescript/package.json')), 'bin', 'cli.js')
execFileSync(process.execPath, [cli, source, '-o', out], { stdio: 'inherit', cwd: root })
