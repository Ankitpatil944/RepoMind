import { ArrowDownRight, ArrowUpRight, Info } from 'lucide-react'

import type { FlowGraph, FlowNode } from '../../api/types'
import { EmptyState, MethodPill, RoleBadge, roleOf } from '../../design/primitives'

interface Props {
  node: FlowNode | null
  flow: FlowGraph | undefined
  onSelect: (n: FlowNode) => void
}

export function EvidencePane({ node, flow, onSelect }: Props) {
  if (!node) {
    return (
      <EmptyState icon={<Info size={28} aria-hidden />} title="Nothing selected">
        Select a node to see why it was classified the way it was, and what connects to it.
      </EmptyState>
    )
  }

  const byId = new Map((flow?.nodes ?? []).map((n) => [n.id, n]))
  const calls = (flow?.edges ?? []).filter((e) => e.source === node.id && e.kind === 'calls')
  const calledBy = (flow?.edges ?? []).filter((e) => e.target === node.id && e.kind === 'calls')

  return (
    <div className="h-full space-y-5 overflow-auto p-4">
      <header>
        {node.type === 'endpoint' ? (
          <div className="flex flex-wrap items-center gap-2">
            <MethodPill method={node.method ?? ''} />
            <span className="font-mono text-[14px]">{node.path}</span>
            <RoleBadge role={roleOf(node)} />
          </div>
        ) : (
          <div className="font-mono text-[14px]">{node.label}</div>
        )}
        {node.file && (
          <div className="mt-1 font-mono text-[12.5px] text-text-2">
            {node.file}:{node.start_line}
            {node.end_line && node.end_line !== node.start_line ? `-${node.end_line}` : ''}
          </div>
        )}
      </header>

      {node.type === 'endpoint' && (
        <section aria-label="Why it was classified this way">
          <h3 className="mb-1.5 text-[12px] font-medium uppercase tracking-wide text-text-3">
            Why this classification
          </h3>
          {node.evidence && node.evidence.length > 0 ? (
            <ul className="space-y-1.5">
              {node.evidence.map((line) => (
                <li key={line} className="rounded-md border border-border-subtle bg-bg-2 px-2.5 py-1.5 text-[13px]">
                  {line}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-text-2">
              No authentication signal was found in this route&apos;s path, decorators, middleware or call
              chain. That means none was detected, which is not proof that the route is public.
            </p>
          )}
        </section>
      )}

      {node.type === 'external' && (
        <p className="text-text-2">
          <span className="font-mono text-text-1">{node.label}</span> is defined outside this repository
          (a library) or is resolved dynamically.
          {node.auth_related && ' Its name matches an authentication/authorization pattern.'}
        </p>
      )}

      {node.type !== 'endpoint' && node.type !== 'external' && node.auth_related && (
        <p className="text-text-2">The name of this function matches an authentication pattern.</p>
      )}

      <Connections title="Calls" icon={<ArrowDownRight size={13} aria-hidden />} ids={calls.map((e) => e.target)} byId={byId} onSelect={onSelect} />
      <Connections title="Called by" icon={<ArrowUpRight size={13} aria-hidden />} ids={calledBy.map((e) => e.source)} byId={byId} onSelect={onSelect} />

      {!!node.hidden_calls && (
        <p className="text-[12.5px] text-text-2">
          {node.hidden_calls} more external call{node.hidden_calls > 1 ? 's' : ''} not drawn to keep the
          graph readable.
        </p>
      )}
    </div>
  )
}

function Connections({
  title,
  icon,
  ids,
  byId,
  onSelect,
}: {
  title: string
  icon: React.ReactNode
  ids: string[]
  byId: Map<string, FlowNode>
  onSelect: (n: FlowNode) => void
}) {
  const nodes = ids.map((id) => byId.get(id)).filter((n): n is FlowNode => !!n)
  if (nodes.length === 0) return null
  return (
    <section aria-label={title}>
      <h3 className="mb-1.5 flex items-center gap-1 text-[12px] font-medium uppercase tracking-wide text-text-3">
        {icon}
        {title} ({nodes.length})
      </h3>
      <ul className="space-y-1">
        {nodes.map((n) => (
          <li key={n.id}>
            <button
              type="button"
              onClick={() => onSelect(n)}
              className="flex w-full items-center gap-2 rounded-md border border-border-subtle bg-bg-2 px-2.5 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
            >
              <span className="truncate font-mono text-[12.5px]">{n.label}</span>
              {n.type === 'external' ? (
                <span className="ml-auto text-[12px] text-text-2">external</span>
              ) : n.file ? (
                <span className="ml-auto truncate font-mono text-[11.5px] text-text-2">
                  {n.file}:{n.start_line}
                </span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
