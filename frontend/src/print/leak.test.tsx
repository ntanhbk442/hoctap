import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ProblemDoc } from '../api/client'
import PrintPart from './PrintPart'
import type { PrintCtx } from './renderers'

// Answer-key leak guard for the question pages: every answer, hint and solution value of every
// fixture Problem is replaced by a unique sentinel, the question section is rendered, and no
// sentinel may appear anywhere in it (text or attributes). Keys that only identify a slot,
// item or option are structural and are left alone.

const DIR = join(process.cwd(), '..', 'backend', 'tests', 'fixtures', 'problemdocs')
const files = readdirSync(DIR).filter((f) => f.endsWith('.json'))
const docs = files.map((f) => [f, JSON.parse(readFileSync(join(DIR, f), 'utf-8')) as ProblemDoc] as const)

const STRING_MARK = 'ZZLEAK'
const NUMBER_BASE = 71828100

function sentinelize(value: unknown, counter: { n: number }, key = ''): unknown {
  if (typeof value === 'string') {
    return /(^|_)key$/.test(key) ? value : `${STRING_MARK}${counter.n++}ZZ`
  }
  if (typeof value === 'number') return NUMBER_BASE + counter.n++
  if (Array.isArray(value)) return value.map((v) => sentinelize(v, counter, key))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, sentinelize(v, counter, k)]),
    )
  }
  return value
}

function ctxOf(doc: ProblemDoc): PrintCtx {
  return {
    imageUrls: Object.fromEntries(doc.images.map((i) => [i.image_key, `/crop/${i.image_key}.jpg`])),
    cropUrl: '/crop/_problem.jpg',
    instruction: doc.instruction,
  }
}

describe('question pages never print an answer, hint or solution value', () => {
  it.each(docs)('%s', (_file, doc) => {
    const counter = { n: 0 }
    const parts = doc.parts.map((part) => {
      const record = part as unknown as Record<string, unknown>
      return {
        ...record,
        answer: sentinelize(record.answer, counter),
        hint: sentinelize(record.hint, counter),
        solution: sentinelize(record.solution, counter),
      }
    }) as unknown as ProblemDoc['parts']
    const { container } = render(
      <>
        {parts.map((part) => (
          <PrintPart key={part.part_key} part={part} ctx={ctxOf(doc)} />
        ))}
      </>,
    )
    const html = container.innerHTML
    expect(html).not.toContain(STRING_MARK)
    expect(html).not.toMatch(/7182\d{4}/)
  })
})
