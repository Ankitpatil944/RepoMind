import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { Box, ExternalLink, FunctionSquare, KeyRound, Route } from 'lucide-react'

import type { FlowNode } from '../../api/types'
import { MethodPill, RoleBadge, roleOf } from '../../design/primitives'
import { cx } from '../../lib/cx'

export type FlowNodeData = { node: FlowNode; isRoot: boolean } & Record<string, unknown>
export type RFNode = Node<FlowNodeData, 'endpoint' | 'function' | 'external'>

const SELECTED =
  'border-accent-500 shadow-[0_0_0_1px_var(--accent-500),0_0_24px_color-mix(in_srgb,var(--accent-500)_28%,transparent)]'

const handles = (
  <>
    <Handle type="target" position={Position.Left} isConnectable={false} />
    <Handle type="source" position={Position.Right} isConnectable={false} />
  </>
)

export function EndpointNode({ data, selected }: NodeProps<RFNode>) {
  const n = data.node
  return (
    <div
      className={cx(
        'node-enter h-full w-full rounded-lg border bg-bg-2 px-3 py-2',
        selected ? SELECTED : 'border-border-control',
      )}
    >
      {handles}
      <div className="flex items-center gap-2">
        <Route size={14} className="shrink-0 text-text-2" aria-hidden />
        <MethodPill method={n.method ?? ''} />
        <RoleBadge role={roleOf(n)} compact />
      </div>
      <div className="mt-1 truncate font-mono text-[12.5px] text-text-1" title={n.path}>
        {n.path}
      </div>
    </div>
  )
}

export function FunctionNode({ data, selected }: NodeProps<RFNode>) {
  const n = data.node
  const Icon = n.type === 'class' ? Box : FunctionSquare
  return (
    <div
      className={cx(
        'node-enter h-full w-full rounded-lg border bg-bg-2 px-3 py-2',
        selected ? SELECTED : 'border-border-control',
        data.isRoot && !selected && 'border-text-3',
      )}
    >
      {handles}
      <div className="flex items-center gap-2">
        <Icon size={14} className="shrink-0 text-text-2" aria-hidden />
        <span className="truncate font-mono text-[12.5px] text-text-1" title={n.label}>
          {n.label}
        </span>
        {n.auth_related && (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-auth">
            <KeyRound size={12} aria-hidden />
            auth
          </span>
        )}
      </div>
      <div className="mt-0.5 flex items-center gap-2 text-[11.5px] text-text-2">
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
        'node-enter flex h-full w-full items-center gap-2 rounded-lg border border-dashed bg-bg-1 px-3',
        selected ? SELECTED : 'border-border-control',
      )}
    >
      {handles}
      <ExternalLink size={13} className="shrink-0 text-text-2" aria-hidden />
      <span className="truncate font-mono text-[12.5px] text-text-1">{n.label}</span>
      {n.auth_related && <KeyRound size={12} className="ml-auto shrink-0 text-auth" aria-label="auth-related call" />}
    </div>
  )
}

export const nodeTypes = {
  endpoint: EndpointNode,
  function: FunctionNode,
  external: ExternalNode,
}
