/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
// Reuses the generator's own frontmatter parsing and DESIGN.md path (single source of
// truth), rather than re-implementing the regex/path here. This test still independently
// checks the *committed* tokens.css against that parse, so a stale/hand-edited tokens.css
// (not regenerated after a DESIGN.md change) fails here rather than only in the generator.
// @ts-expect-error -- plain .mjs script, no type declarations; typed via the JSDoc cast below.
import { designPath, parseFrontmatter } from '../../scripts/gen-tokens.mjs'
import { KEY_SIZE, TOUCH_MIN } from './dimensions'

interface Design {
  colors: Record<string, string>
  typography: Record<
    string,
    { fontFamily: string; fontSize: string; fontWeight: number; lineHeight: number }
  >
  rounded: Record<string, string>
  spacing: Record<string, string>
}

const here = dirname(fileURLToPath(import.meta.url))
const tokensPath = resolve(here, 'tokens.css')

const design = parseFrontmatter(readFileSync(designPath as string, 'utf-8')) as Design
const css = readFileSync(tokensPath, 'utf-8')

describe('tokens.css', () => {
  it('has every DESIGN.md colors.* value verbatim, as --color-<key>', () => {
    for (const [key, value] of Object.entries(design.colors)) {
      expect(css).toContain(`--color-${key}: ${value};`)
    }
  })

  it('has every DESIGN.md typography.* role verbatim, as --font-<role>-*', () => {
    for (const [role, spec] of Object.entries(design.typography)) {
      expect(css).toContain(String(spec.fontFamily))
      expect(css).toContain(`--font-${role}-size: ${spec.fontSize};`)
      expect(css).toContain(`--font-${role}-weight: ${spec.fontWeight};`)
      expect(css).toContain(`--font-${role}-line-height: ${spec.lineHeight};`)
    }
  })

  it('has every DESIGN.md rounded.* value verbatim, as --radius-<key>', () => {
    for (const [key, value] of Object.entries(design.rounded)) {
      expect(css).toContain(`--radius-${key}: ${value};`)
    }
  })

  it('has every DESIGN.md spacing.* value verbatim, as --space-<key>, including touch-min and key', () => {
    for (const [key, value] of Object.entries(design.spacing)) {
      expect(css).toContain(`--space-${key}: ${value};`)
    }
    expect(design.spacing['touch-min']).toBe('64px')
    expect(design.spacing['key']).toBe('80px')
  })

  it('defines no danger/error/red token (UX-DR5: no red on child components)', () => {
    expect(css).not.toMatch(/--color-(danger|error|red)\b/i)
  })
})

describe('src/styles/dimensions.ts', () => {
  it('TOUCH_MIN/KEY_SIZE stay in sync with DESIGN.md spacing.touch-min / spacing.key', () => {
    expect(`${TOUCH_MIN}px`).toBe(design.spacing['touch-min'])
    expect(`${KEY_SIZE}px`).toBe(design.spacing['key'])
  })
})
