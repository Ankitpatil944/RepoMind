import { Handle, Position, useStore, type Node, type NodeProps } from '@xyflow/react'
import { ArrowDownLeft, ArrowUpRight, KeyRound } from 'lucide-react'

import type { FlowNode } from '../../api/types'
import { MethodPill, RoleBadge, roleOf } from '../../design/primitives'
import { cx } from '../../lib/cx'
import { cxColor } from '../overview/colors'

export type FlowNodeData = {
  node: FlowNode
  isRoot: boolean
  col?: number
  dim?: boolean
} & Record<string, unknown>
export type RFNode = Node<FlowNodeData, 'endpoint' | 'function' | 'external'>

const SELECTED =
  'border-sage shadow-[0_0_0_1px_var(--accent-400),0_0_24px_color-mix(in_srgb,var(--accent-400)_28%,transparent)] node-selected-ping'

/** Kind badge: EP endpoint, FN function, CLS class, TSX component, EXT outside the repo. */
function kindOf(n: FlowNode): { label: string; color: string } {
  if (n.type === 'endpoint') return { label: 'EP', color: 'var(--accent-400)' }
  if (n.type === 'external') return { label: 'EXT', color: 'var(--text-2)' }
  if (n.type === 'class') return { label: 'CLS', color: 'var(--lavender)' }
  if (n.file?.endsWith('.tsx') || n.file?.endsWith('.jsx')) return { label: n.file.endsWith('.tsx') ? 'TSX' : 'JSX', color: 'var(--lavender)' }
  return { label: 'FN', color: 'var(--teal)' }
}

function KindBadge({ node }: { node: FlowNode }) {
  const { label, color } = kindOf(node)
  return (
    <span
      className="inline-flex h-[18px] shrink-0 items-center rounded-[4px] border px-1.5 font-mono text-[10px] font-semibold tracking-wide"
      style={{ color, borderColor: `color-mix(in srgb, ${color} 45%, transparent)`, background: `color-mix(in srgb, ${color} 10%, transparent)` }}
      aria-hidden
    >
      {label}
    </span>
  )
}

/** 10-tick complexity meter; ticks grow in. The numeric chip beside it carries the meaning. */
function CxMeter({ value }: { value: number }) {
  const on = Math.min(10, Math.max(1, Math.round(value)))
  const color = cxColor(value)
  return (
    <div className="mt-1.5 flex h-2 items-end gap-[2px]" aria-hidden>
      {Array.from({ length: 10 }, (_, i) => (
        <span
          key={i}
          className="tick-grow block w-full rounded-[1px]"
          style={{
            height: `${40 + i * 6}%`,
            background: i < on ? color : 'var(--border-subtle)',
            animationDelay: `${i * 30}ms`,
          }}
        />
      ))}
    </div>
  )
}

/** Per-column stagger so nodes cascade in from the root. */
const enter = (data: FlowNodeData) => ({ animationDelay: `${Math.min(data.col ?? 0, 8) * 70}ms` })

const handles = (
  <>
    <Handle type="target" position={Position.Left} isConnectable={false} />
    <Handle type="source" position={Position.Right} isConnectable={false} />
  </>
)

/** True when the canvas is zoomed out far enough that detail is unreadable. */
const useCompact = () => useStore((s) => s.transform[2] < 0.5)

const COMPLEXITY_WORD = (n: number) => (n <= 5 ? 'low' : n <= 10 ? 'moderate' : 'high')

/** Complexity is a number + a word, so it never depends on colour alone. */
function Metrics({ node }: { node: FlowNode }) {
  const cx_ = node.complexity ?? 0
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1">
      {!!node.loc && <span className="metric-chip" title="Lines of code">{node.loc} loc</span>}
      {cx_ > 0 && (
        <span
          className="metric-chip"
          style={{ color: cxColor(cx_) }}
          title={`Cyclomatic-style complexity ${cx_} (${COMPLEXITY_WORD(cx_)})`}
        >
          cx {cx_} · {COMPLEXITY_WORD(cx_)}
        </span>
      )}
      {node.fan_in !== undefined && (
        <span className="metric-chip" title="Functions that call this">
          <ArrowDownLeft size={10} aria-hidden />
          {node.fan_in}
        </span>
      )}
      {node.fan_out !== undefined && (
        <span className="metric-chip" title="Calls made by this function">
          <ArrowUpRight size={10} aria-hidden />
          {node.fan_out}
        </span>
      )}
    </div>
  )
}

export function EndpointNode({ data, selected }: NodeProps<RFNode>) {
  const n = data.node
  const compact = useCompact()
  if (compact) {
    return (
      <div
        className={cx(
          'node-card flex h-full w-full items-center gap-2 rounded-[9px] border bg-bg-2 px-3',
          selected ? SELECTED : 'border-border-control',
        )}
      >
        {handles}
        <span className="text-[22px] font-semibold leading-none">{n.method}</span>
        <span className="truncate font-mono text-[22px]">{n.path}</span>
      </div>
    )
  }
  return (
    <div
      className={cx(
        'node-card node-enter h-full w-full rounded-[9px] border bg-bg-2 px-3 py-2',
        'node-endpoint',
        selected ? SELECTED : 'border-border-control',
        data.isRoot && 'node-root',
      )}
      style={enter(data)}
    >
      {handles}
      <div className="flex items-center gap-2">
        <KindBadge node={n} />
        <MethodPill method={n.method ?? ''} />
        <RoleBadge role={roleOf(n)} compact />
        <span className="ml-auto text-[11px] font-medium uppercase tracking-wide text-text-2">
          {roleOf(n)}
        </span>
      </div>
      <div className="mt-1.5 truncate font-mono text-[13px] text-text-1" title={n.path}>
        {n.path}
      </div>
      <div className="mt-0.5 truncate font-mono text-[11.5px] text-text-2">
        {n.file}:{n.start_line}
      </div>
    </div>
  )
}

export function FunctionNode({ data, selected }: NodeProps<RFNode>) {
  const n = data.node
  const compact = useCompact()
  const hot = (n.complexity ?? 0) >= 10
  if (compact) {
    return (
      <div
        className={cx(
          'node-card flex h-full w-full items-center gap-2 rounded-[9px] border bg-bg-2 px-3',
          selected ? SELECTED : 'border-border-control',
          n.auth_related && 'node-auth',
        )}
      >
        {handles}
        <span className="truncate font-mono text-[22px] font-medium">{n.label}</span>
      </div>
    )
  }
  return (
    <div
      className={cx(
        'node-card node-enter h-full w-full rounded-[9px] border bg-bg-2 px-3 py-2',
        selected ? SELECTED : 'border-border-control',
        data.isRoot && 'node-root',
        data.isRoot && !selected && 'border-sage-border',
        n.auth_related && 'node-auth',
      )}
      style={enter(data)}
    >
      {handles}
      {hot && <span className="ring-pulse rounded-[9px]" aria-hidden />}
      <div className="flex items-center gap-2">
        <KindBadge node={n} />
        <span className="truncate font-mono text-[13px] font-medium text-cream" title={n.label}>
          {n.label}
        </span>
        {n.auth_related && (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-auth">
            <KeyRound size={12} aria-hidden />
            auth
          </span>
        )}
      </div>
      {n.signature && (
        <div className="mt-1 truncate font-mono text-[11.5px] text-text-2" title={n.signature}>
          {n.signature}
        </div>
      )}
      {n.doc && (
        <p className="doc-clamp mt-1 text-[12px] leading-snug text-text-2" title={n.doc}>
          {n.doc}
        </p>
      )}
      <Metrics node={n} />
      {!!n.complexity && <CxMeter value={n.complexity} />}
      <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-text-2">
        <span className="truncate font-mono">
          {n.file}:{n.start_line}
        </span>
        {!!n.hidden_calls && (
          <span className="ml-auto shrink-0" title="Further external calls not shown">
            +{n.hidden_calls} calls
          </span>
        )}
      </div>
    </div>
  )
}

export function ExternalNode({ data, selected }: NodeProps<RFNode>) {
  const n = data.node
  return (
    <div
      title="Defined outside this repository, or resolved dynamically"
      className={cx(
        'node-card node-enter flex h-full w-full items-center gap-2 rounded-[9px] border border-dashed bg-bg-1 px-3',
        selected ? SELECTED : 'border-[#3a4654]',
      )}
      style={enter(data)}
    >
      {handles}
      <KindBadge node={n} />
      <span className="min-w-0">
        <span className="block truncate font-mono text-[12.5px] text-text-1">{n.label}</span>
        <span className="block text-[10.5px] text-text-3">external · not indexed</span>
      </span>
      {n.auth_related && <KeyRound size={12} className="ml-auto shrink-0 text-auth" aria-label="auth-related call" />}
    </div>
  )
}

export const nodeTypes = {
  endpoint: EndpointNode,
  function: FunctionNode,
  external: ExternalNode,
}
