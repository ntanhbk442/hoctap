import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ProblemDoc } from '../api/client'
import PrintPart from './PrintPart'
import { PRINT_RENDERERS, type PrintCtx } from './renderers'

const DIR = join(process.cwd(), '..', 'backend', 'tests', 'fixtures', 'problemdocs')
const files = readdirSync(DIR).filter((f) => f.endsWith('.json'))
const docs = files.map((f) => JSON.parse(readFileSync(join(DIR, f), 'utf-8')) as ProblemDoc)

const TYPES = [
  'number_input',
  'expression_input',
  'compare',
  'multiple_choice',
  'image_select',
  'order',
  'number_tree',
  'grid_fill',
  'match',
  'count_image',
  'dot_draw',
  'connect_dots',
  'spot_difference',
  'fallback',
]

function ctxOf(doc: ProblemDoc, withImages = true): PrintCtx {
  return {
    imageUrls: withImages ? Object.fromEntries(doc.images.map((i) => [i.image_key, `/crop/${i.image_key}.jpg`])) : {},
    cropUrl: withImages ? '/crop/_problem.jpg' : null,
    instruction: doc.instruction,
  }
}

function docOf(type: string): ProblemDoc {
  const doc = docs.find((d) => d.parts[0].type === type)
  if (!doc) throw new Error(`no fixture for ${type}`)
  return doc
}

describe('print renderers', () => {
  it('has a renderer for every Problem Type and a fixture for each', () => {
    expect(Object.keys(PRINT_RENDERERS).sort()).toEqual([...TYPES].sort())
    for (const t of TYPES) expect(() => docOf(t)).not.toThrow()
  })

  it.each(TYPES)('%s prints without Hint, Solution or answer text', (type) => {
    const doc = docOf(type)
    const { container } = render(
      <>
        {doc.parts.map((part) => (
          <PrintPart key={part.part_key} part={part} ctx={ctxOf(doc)} />
        ))}
      </>,
    )
    expect(container.querySelector('.p-part')).not.toBeNull()
    const text = container.textContent ?? ''
    for (const part of doc.parts) {
      expect(text).not.toContain(part.hint)
      expect(text).not.toContain(part.solution.final)
    }
  })

  it('prints answer slots as empty boxes', () => {
    const doc = docOf('number_input')
    const part = doc.parts[0]
    if (part.type !== 'number_input') throw new Error('fixture')
    const { container } = render(<PrintPart part={part} ctx={ctxOf(doc)} />)
    expect(container.querySelectorAll('.p-box')).toHaveLength(part.slots.length)
    for (const e of part.answer) {
      expect(container.textContent).not.toContain(`= ${e.value}`)
    }
  })

  it('prints expression_input slots as wide empty boxes', () => {
    const doc = docOf('expression_input')
    const { container } = render(<PrintPart part={doc.parts[0]} ctx={ctxOf(doc)} />)
    expect(container.querySelectorAll('.p-box-wide').length).toBeGreaterThan(0)
  })

  it('prints match as dots to connect, with no pairs', () => {
    const doc = docOf('match')
    const part = doc.parts[0]
    if (part.type !== 'match') throw new Error('fixture')
    const { getAllByTestId, container } = render(<PrintPart part={part} ctx={ctxOf(doc)} />)
    expect(getAllByTestId('match-dot')).toHaveLength(part.left.length + part.right.length)
    expect(container.querySelector('svg, line')).toBeNull()
  })

  it('prints fallback as the crop image with a blank writing area', () => {
    const doc = docOf('fallback')
    const { container, getByTestId } = render(<PrintPart part={doc.parts[0]} ctx={ctxOf(doc)} />)
    expect(container.querySelector('img')).toHaveAttribute('src', '/crop/me-cung.jpg')
    expect(getByTestId('print-writing-area')).toBeInTheDocument()
  })

  it('falls back to the Problem text when the crop is missing, with no broken image', () => {
    const doc = docOf('fallback')
    const { container, getByTestId } = render(
      <PrintPart part={doc.parts[0]} ctx={ctxOf(doc, false)} />,
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain(doc.instruction)
    expect(getByTestId('print-writing-area')).toBeInTheDocument()
  })

  it('leaves out an image whose crop is missing', () => {
    const doc = docOf('count_image')
    const { container } = render(<PrintPart part={doc.parts[0]} ctx={ctxOf(doc, false)} />)
    expect(container.querySelector('img')).toBeNull()
  })

  it('numbers the dots of connect_dots over the picture', () => {
    const doc = docOf('connect_dots')
    const { container } = render(<PrintPart part={doc.parts[0]} ctx={ctxOf(doc)} />)
    expect(container.querySelectorAll('.p-numdot')).toHaveLength(6)
  })
})
