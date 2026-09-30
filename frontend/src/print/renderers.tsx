/* eslint-disable react-refresh/only-export-components -- a renderer table plus its private helper components; not a fast-refresh boundary. */
import type { ReactNode } from 'react'
import type { ProblemPart } from '../api/client'

/**
 * Story 7.1: paper renderers, one per Problem Type. They receive the full Part (the API
 * returns it with the Answer Key) but only ever read its child-visible fields: `answer`,
 * `hint` and `solution` are never touched here. Answer slots are empty boxes, `match` is
 * dots to connect, and nothing depends on colour.
 */

type PartOf<T extends ProblemPart['type']> = Extract<ProblemPart, { type: T }>

export interface PrintCtx {
  /** image_key -> served crop URL; only crops that exist. */
  imageUrls: Record<string, string>
  /** The whole-Problem crop, or null when the file is missing. */
  cropUrl: string | null
  /** The Problem's instruction, the text fallback when a crop is missing. */
  instruction: string
}

type Renderer<T extends ProblemPart['type']> = (part: PartOf<T>, ctx: PrintCtx) => ReactNode

const SLOT = /\[\[([^[\]]*)\]\]/g

function Box({ wide = false, label }: { wide?: boolean; label?: string }) {
  return <span className={wide ? 'p-box p-box-wide' : 'p-box'} role="presentation" aria-label={label} />
}

/** Text with every `[[slot]]` replaced by an empty box. */
function Template({ text, wide }: { text: string; wide?: boolean }) {
  const nodes: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(SLOT)) {
    nodes.push(text.slice(last, m.index))
    nodes.push(<Box key={m.index} wide={wide} />)
    last = m.index + m[0].length
  }
  nodes.push(text.slice(last))
  return <p className="p-line">{nodes}</p>
}

function Picture({ src, alt, children }: { src?: string; alt: string; children?: ReactNode }) {
  if (!src) return null
  return (
    <div className="p-picture">
      <img src={src} alt={alt} />
      {children}
    </div>
  )
}

function Item({ text, imageUrl }: { text?: string | null; imageUrl?: string }) {
  return (
    <>
      {imageUrl && <img className="p-item-img" src={imageUrl} alt="" />}
      {text}
    </>
  )
}

const numberInput: Renderer<'number_input'> = (part) => <Template text={part.template} />
const expressionInput: Renderer<'expression_input'> = (part) => (
  <Template text={part.template} wide />
)

const compare: Renderer<'compare'> = (part) => (
  <ul className="p-rows">
    {part.rows.map((r) => (
      <li key={r.slot_key} className="p-line">
        {r.left} <Box label="so sánh" /> {r.right}
      </li>
    ))}
  </ul>
)

const multipleChoice: Renderer<'multiple_choice'> = (part, ctx) => (
  <ul className="p-options">
    {part.options.map((o) => (
      <li key={o.option_key}>
        <span className={part.multi ? 'p-tick' : 'p-tick p-tick-round'} aria-hidden="true" />{' '}
        <Item text={o.text} imageUrl={o.image_key ? ctx.imageUrls[o.image_key] : undefined} />
      </li>
    ))}
  </ul>
)

const imageSelect: Renderer<'image_select'> = (part, ctx) => (
  <div>
    <Picture src={ctx.imageUrls[part.image_key]} alt="Hình để chọn">
      {part.regions.map((r, i) => (
        <span
          key={r.region_key}
          className="p-region"
          style={{
            left: `${r.bbox[0] * 100}%`,
            top: `${r.bbox[1] * 100}%`,
            width: `${(r.bbox[2] - r.bbox[0]) * 100}%`,
            height: `${(r.bbox[3] - r.bbox[1]) * 100}%`,
          }}
        >
          {i + 1}
        </span>
      ))}
    </Picture>
    <p className="p-line">
      {part.multi ? 'Chọn các hình:' : 'Chọn một hình:'}{' '}
      {part.regions.map((r, i) => (
        <span key={r.region_key} className="p-choice">
          {i + 1} <Box />
        </span>
      ))}
    </p>
  </div>
)

const order: Renderer<'order'> = (part) => (
  <div>
    <ul className="p-chips">
      {part.items.map((i) => (
        <li key={i.item_key}>{i.text}</li>
      ))}
    </ul>
    <p className="p-line">
      {part.items.map((i, n) => (
        <span key={i.item_key} className="p-choice">
          {n > 0 && '→ '}
          <Box />
        </span>
      ))}
    </p>
  </div>
)

function TreeNode({
  nodes,
  nodeKey,
}: {
  nodes: PartOf<'number_tree'>['nodes']
  nodeKey: string
}) {
  const node = nodes.find((n) => n.node_key === nodeKey)
  if (!node) return null
  const children = nodes.filter((n) => n.parent_key === nodeKey)
  return (
    <li>
      <span className="p-node">{node.given ?? <Box />}</span>
      {children.length > 0 && (
        <ul>
          {children.map((c) => (
            <TreeNode key={c.node_key} nodes={nodes} nodeKey={c.node_key} />
          ))}
        </ul>
      )}
    </li>
  )
}

const numberTree: Renderer<'number_tree'> = (part) => {
  const root = part.nodes.find((n) => !n.parent_key)
  return <ul className="p-tree">{root && <TreeNode nodes={part.nodes} nodeKey={root.node_key} />}</ul>
}

const gridFill: Renderer<'grid_fill'> = (part) => (
  <table className="p-grid">
    <tbody>
      {part.cells.map((row, i) => (
        <tr key={i}>
          {row.map((cell, j) => (
            <td key={j}>{cell.given ?? <Box />}</td>
          ))}
        </tr>
      ))}
    </tbody>
  </table>
)

const match: Renderer<'match'> = (part, ctx) => {
  const rows = Math.max(part.left.length, part.right.length)
  return (
    <div className="p-match" data-testid="print-match">
      {Array.from({ length: rows }, (_, i) => {
        const l = part.left[i]
        const r = part.right[i]
        return (
          <div key={i} className="p-match-row">
            <span className="p-match-item p-match-left">
              {l && <Item text={l.text} imageUrl={l.image_key ? ctx.imageUrls[l.image_key] : undefined} />}
            </span>
            <span className="p-dot" data-testid="match-dot" aria-hidden="true">
              {l ? '●' : ''}
            </span>
            <span className="p-match-gap" />
            <span className="p-dot" data-testid="match-dot" aria-hidden="true">
              {r ? '●' : ''}
            </span>
            <span className="p-match-item p-match-right">
              {r && <Item text={r.text} imageUrl={r.image_key ? ctx.imageUrls[r.image_key] : undefined} />}
            </span>
          </div>
        )
      })}
    </div>
  )
}

const countImage: Renderer<'count_image'> = (part, ctx) => (
  <div>
    <Picture src={ctx.imageUrls[part.image_key]} alt="Hình để đếm" />
    <ul className="p-rows">
      {part.slots.map((s) => (
        <li key={s.slot_key} className="p-line">
          {s.label} <Box />
        </li>
      ))}
    </ul>
  </div>
)

const dotDraw: Renderer<'dot_draw'> = (part) => (
  <ul className="p-dotboxes">
    {part.boxes.map((b) => (
      <li key={b.slot_key}>
        <span className="p-dotbox">{'●'.repeat(b.given)}</span>
        <span className="p-dotbox-label">{b.label}</span>
      </li>
    ))}
  </ul>
)

const connectDots: Renderer<'connect_dots'> = (part, ctx) => (
  <Picture src={ctx.imageUrls[part.image_key]} alt="Hình nối các chấm">
    {part.dots.map((d) => (
      <span key={d.n} className="p-numdot" style={{ left: `${d.x * 100}%`, top: `${d.y * 100}%` }}>
        {d.n}
      </span>
    ))}
  </Picture>
)

const spotDifference: Renderer<'spot_difference'> = (part, ctx) => (
  <div>
    <div className="p-pair">
      <Picture src={ctx.imageUrls[part.image_left]} alt="Tranh bên trái" />
      <Picture src={ctx.imageUrls[part.image_right]} alt="Tranh bên phải" />
    </div>
    <p className="p-line">
      Tìm {part.count} điểm khác nhau. Đã tìm thấy: <Box />
    </p>
  </div>
)

const fallback: Renderer<'fallback'> = (part, ctx) => {
  const src = ctx.imageUrls[part.image_key] ?? ctx.cropUrl ?? undefined
  return (
    <div>
      {src ? <Picture src={src} alt="Ảnh bài toán" /> : <p className="p-line">{ctx.instruction}</p>}
      <div className="p-writing" data-testid="print-writing-area" />
    </div>
  )
}

/** One renderer per Problem Type: the compiler rejects a type without an entry. */
export const PRINT_RENDERERS: { [T in ProblemPart['type']]: Renderer<T> } = {
  number_input: numberInput,
  expression_input: expressionInput,
  compare,
  multiple_choice: multipleChoice,
  image_select: imageSelect,
  order,
  number_tree: numberTree,
  grid_fill: gridFill,
  match,
  count_image: countImage,
  dot_draw: dotDraw,
  connect_dots: connectDots,
  spot_difference: spotDifference,
  fallback,
}
