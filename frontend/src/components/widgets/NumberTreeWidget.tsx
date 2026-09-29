import type { ReactNode } from 'react'
import AnswerSlot from '../AnswerSlot/AnswerSlot'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type NumberTreeView = Extract<ChildPart, { type: 'number_tree' }>

/** `number_tree`: the Part's `nodes` as a root-to-leaves tree -- each level (nodes sharing
 * the same `parent_key`) rendered as one row below its parent. A node with `given` shows
 * that printed value; a node without one is an Answer Slot (UX-DR9's tap-then-type, same
 * as `number_input`). */
export default function NumberTreeWidget({
  part,
  values,
  onSlotTap,
  slotState,
  disabled,
}: WidgetProps<NumberTreeView>) {
  const byParent = new Map<string | null, typeof part.nodes>()
  for (const node of part.nodes) {
    const key = node.parent_key ?? null
    byParent.set(key, [...(byParent.get(key) ?? []), node])
  }
  const root = part.nodes.find((n) => n.parent_key == null)

  function renderLevel(parentKey: string | null): ReactNode {
    const nodes = byParent.get(parentKey)
    if (!nodes || nodes.length === 0) return null
    return (
      <div className="widget-number-tree-level">
        {nodes.map((node) => (
          <div key={node.node_key} className="widget-number-tree-node">
            {node.given != null ? (
              <span className="widget-number-tree-given">{node.given}</span>
            ) : (
              <AnswerSlot
                label={`Ô ${node.node_key}`}
                value={values[node.node_key] ?? ''}
                state={slotState(node.node_key)}
                onClick={disabled ? undefined : () => onSlotTap(node.node_key)}
              />
            )}
            {renderLevel(node.node_key)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="widget-number-tree" aria-label={part.prompt || undefined}>
      {root && renderLevel(null)}
    </div>
  )
}
