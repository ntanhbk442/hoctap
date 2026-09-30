import type { ProblemPart } from '../../api/client'

type Keyed = { key: string; value: string }
type Labeled = { key: string; text?: string | null; image_key?: string | null }

function keyedLines(answer: Keyed[], label: (key: string) => string = (k) => k): string[] {
  return answer.map((e) => `${label(e.key)} = ${e.value}`)
}

function textOf(items: Labeled[], key: string): string {
  const item = items.find((i) => i.key === key)
  return item?.text ?? item?.image_key ?? key
}

/**
 * The Answer Key of a Part as human-readable lines (read-only, per Problem Type), for the
 * spot-check: the filled template, the compared rows, the chosen options, the order…
 */
export function answerLines(part: ProblemPart): string[] {
  switch (part.type) {
    case 'number_input':
    case 'expression_input': {
      let text = part.template
      for (const e of part.answer) text = text.split(`[[${e.key}]]`).join(e.value)
      return [text]
    }
    case 'compare':
      return part.answer.map((e) => {
        const row = part.rows.find((r) => r.slot_key === e.key)
        return row ? `${row.left} ${e.value} ${row.right}` : `${e.key}: ${e.value}`
      })
    case 'multiple_choice': {
      const options = part.options.map((o) => ({ key: o.option_key, text: o.text, image_key: o.image_key }))
      return [`Chọn: ${part.answer.selected.map((k) => textOf(options, k)).join('; ')}`]
    }
    case 'image_select':
      return [`Chọn vùng: ${part.answer.selected.join(', ')}`]
    case 'order': {
      const items = part.items.map((i) => ({ key: i.item_key, text: i.text }))
      return [part.answer.order.map((k) => textOf(items, k)).join(' → ')]
    }
    case 'match': {
      const left = part.left.map((i) => ({ key: i.item_key, text: i.text, image_key: i.image_key }))
      const right = part.right.map((i) => ({ key: i.item_key, text: i.text, image_key: i.image_key }))
      return part.answer.pairs.map(([l, r]) => `${textOf(left, l)} — ${textOf(right, r)}`)
    }
    case 'count_image': {
      const labels = new Map(part.slots.map((s) => [s.slot_key, s.label || s.slot_key]))
      return keyedLines(part.answer, (k) => labels.get(k) ?? k)
    }
    case 'dot_draw': {
      const labels = new Map(part.boxes.map((b) => [b.slot_key, b.label]))
      return keyedLines(part.answer, (k) => `Ô ${labels.get(k) ?? k}`)
    }
    case 'number_tree':
      return keyedLines(part.answer, (k) => `Nút ${k}`)
    case 'grid_fill':
      return keyedLines(part.answer, (k) => {
        const m = /^r(\d+)c(\d+)$/.exec(k)
        return m ? `Hàng ${Number(m[1]) + 1}, cột ${Number(m[2]) + 1}` : k
      })
    case 'connect_dots':
      return [`Nối: ${part.answer.sequence.join(' → ')}`]
    case 'spot_difference':
      return [`${part.answer.regions.length} chỗ khác nhau`]
    case 'fallback':
      return ['Không có đáp án chấm tự động (chỉ có lời giải).']
    default:
      return [JSON.stringify((part as { answer?: unknown }).answer)]
  }
}
