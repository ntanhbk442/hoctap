// Generates src/styles/tokens.css from DESIGN.md's YAML frontmatter.
// Source: the UX spec's frontmatter is the literal source of truth for every token value
// (see spec-2-1-design-tokens-nunito-and-core-components.md). Run with `npm run gen:tokens`;
// the output is committed, like `gen:api`'s generated schema.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const designPath = resolve(
  root,
  '..',
  '_bmad-output/planning-artifacts/ux-designs/ux-hoctap-2026-09-26/DESIGN.md',
)
const outPath = join(root, 'src', 'styles', 'tokens.css')

/** Parses the `---`-delimited YAML frontmatter at the top of a markdown file. */
export function parseFrontmatter(markdown) {
  const match = /^---\n([\s\S]*?)\n---/.exec(markdown)
  if (!match) throw new Error('gen:tokens: no YAML frontmatter found in DESIGN.md')
  return yaml.load(match[1])
}

const REQUIRED_TYPOGRAPHY_FIELDS = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight']

/**
 * Fails loudly (rather than crashing with an unhelpful TypeError, or silently writing
 * `undefined` into tokens.css) when DESIGN.md's frontmatter doesn't parse to the shape
 * buildTokensCss() expects.
 */
export function validateDesign(design) {
  if (design === null || typeof design !== 'object' || Array.isArray(design)) {
    throw new Error(
      `gen:tokens: DESIGN.md frontmatter did not parse to an object (got ${JSON.stringify(design)})`,
    )
  }
  for (const [role, spec] of Object.entries(design.typography ?? {})) {
    const missing = REQUIRED_TYPOGRAPHY_FIELDS.filter(
      (field) => spec == null || spec[field] === undefined,
    )
    if (missing.length > 0) {
      throw new Error(`gen:tokens: DESIGN.md typography.${role} is missing: ${missing.join(', ')}`)
    }
  }
  return design
}

/**
 * Builds tokens.css from the parsed DESIGN.md frontmatter. Every value is emitted verbatim
 * (no rounding, no re-deriving) so a test can assert it appears in the output unchanged.
 */
export function buildTokensCss(design) {
  const lines = []
  lines.push('/* GENERATED FILE. Do not edit by hand — run `npm run gen:tokens`.')
  lines.push(
    ' * Source of truth: _bmad-output/planning-artifacts/ux-designs/ux-hoctap-2026-09-26/DESIGN.md (frontmatter). */',
  )
  lines.push(':root {')

  lines.push('  /* colors */')
  for (const [key, value] of Object.entries(design.colors ?? {})) {
    lines.push(`  --color-${key}: ${value};`)
  }

  lines.push('')
  lines.push('  /* typography */')
  for (const [role, spec] of Object.entries(design.typography ?? {})) {
    lines.push(`  --font-${role}-family: ${spec.fontFamily}, sans-serif;`)
    lines.push(`  --font-${role}-size: ${spec.fontSize};`)
    lines.push(`  --font-${role}-weight: ${spec.fontWeight};`)
    lines.push(`  --font-${role}-line-height: ${spec.lineHeight};`)
  }

  lines.push('')
  lines.push('  /* rounded corners */')
  for (const [key, value] of Object.entries(design.rounded ?? {})) {
    lines.push(`  --radius-${key}: ${value};`)
  }

  lines.push('')
  lines.push('  /* spacing */')
  for (const [key, value] of Object.entries(design.spacing ?? {})) {
    lines.push(`  --space-${key}: ${value};`)
  }

  lines.push('}')
  lines.push('')
  return lines.join('\n')
}

function main() {
  const markdown = readFileSync(designPath, 'utf-8')
  const design = validateDesign(parseFrontmatter(markdown))
  const css = buildTokensCss(design)
  writeFileSync(outPath, css)
  console.log(`gen:tokens: wrote ${outPath}`)
}

// Only run when invoked directly (`npm run gen:tokens`), not when imported by the test.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main()
}
