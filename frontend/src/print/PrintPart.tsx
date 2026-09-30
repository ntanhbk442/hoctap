import type { ReactNode } from 'react'
import type { ProblemPart } from '../api/client'
import { PRINT_RENDERERS, type PrintCtx } from './renderers'

export default function PrintPart({ part, ctx }: { part: ProblemPart; ctx: PrintCtx }) {
  const render = PRINT_RENDERERS[part.type] as (p: ProblemPart, c: PrintCtx) => ReactNode
  return (
    <section className="p-part" data-part-type={part.type}>
      <p className="p-part-head">
        <strong>{part.part_key})</strong> {part.prompt}
      </p>
      {part.image_keys.map((k) =>
        ctx.imageUrls[k] ? (
          <div key={k} className="p-picture">
            <img src={ctx.imageUrls[k]} alt="Hình minh họa" />
          </div>
        ) : null,
      )}
      {render(part, ctx)}
    </section>
  )
}
