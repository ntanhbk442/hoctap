/// <reference types="node" />
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Positively encodes UX-DR5 ("no red on child screens") as a test: none of the ten
// child-facing components may reference an undefined danger/error/red token, and
// tokens.css itself must not define one.
const here = dirname(fileURLToPath(import.meta.url))
const componentsDir = resolve(here, '..', 'components')
const tokensCss = readFileSync(join(here, 'tokens.css'), 'utf-8')

const DANGER_PATTERN = /--color-[a-z-]*(danger|error|red)[a-z-]*/i

function componentSourceFiles(): string[] {
  const files: string[] = []
  for (const name of readdirSync(componentsDir)) {
    const dir = join(componentsDir, name)
    for (const file of readdirSync(dir)) {
      if (file.endsWith('.tsx') || file.endsWith('.css')) {
        if (file.endsWith('.test.tsx')) continue
        files.push(join(dir, file))
      }
    }
  }
  return files
}

describe('no red on child components (UX-DR5)', () => {
  it('tokens.css defines no danger/error/red colour token', () => {
    expect(tokensCss).not.toMatch(DANGER_PATTERN)
  })

  it('no child-facing component source references a danger/error/red token', () => {
    for (const file of componentSourceFiles()) {
      const source = readFileSync(file, 'utf-8')
      expect(source, `${file} references an undefined danger/red token`).not.toMatch(DANGER_PATTERN)
    }
  })
})
