import { MethodPill, RoleBadge, roleOf } from '../../design/primitives'
import type { FlowGraph, FlowNode } from '../../api/types'
import { buildOutline, type OutlineItem } from '../../lib/graph'
import { cx } from '../../lib/cx'

interface Props {
  flow: FlowGraph
  selected: string | null
  onSelect: (node: FlowNode) => void
}

/** The graph as a nested text list: a keyboard- and screen-reader-friendly
 *  alternative to the canvas, and easier to scan on large graphs. */
export function Outline({ flow, selected, onSelect }: Props) {
  const root = buildOutline(flow)
  if (!root) return null
  return (
    <nav aria-label="Call graph outline" className="h-full overflow-auto p-4">
      <ul className="space-y-0.5">
        <Item item={root} selected={selected} onSelect={onSelect} />
      </ul>
    </nav>
  )
}

function Item({
  item,
  selected,
  onSelect,
}: {
  item: OutlineItem
  selected: string | null
  onSelect: (node: FlowNode) => void
}) {
  const n = item.node
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(n)}
        aria-current={n.id === selected ? 'true' : undefined}
        className={cx(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3',
          n.id === selected && 'bg-bg-3 outline outline-1 outline-accent-500',
        )}
      >
        {item.relation !== 'root' && (
          <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-text-3">{item.relation}</span>
        )}
        {n.type === 'endpoint' ? (
          <>
            <MethodPill method={n.method ?? ''} />
            <span className="truncate font-mono text-[13px]">{n.path}</span>
            <RoleBadge role={roleOf(n)} />
          </>
        ) : (
          <>
            <span className="truncate font-mono text-[13px]">{n.label}</span>
            {n.type === 'external' ? (
              <span className="text-[12px] text-text-2">external</span>
            ) : (
              <span className="truncate font-mono text-[12px] text-text-2">
                {n.file}:{n.start_line}
              </span>
            )}
          </>
        )}
      </button>
      {item.children.length > 0 && (
        <ul className="ml-4 mt-0.5 space-y-0.5 border-l border-border-subtle pl-2">
          {item.children.map((c) => (
            <Item key={c.node.id} item={c} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  )
}
