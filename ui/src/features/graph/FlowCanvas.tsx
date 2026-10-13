import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
} from '@xyflow/react'
import { Network } from 'lucide-react'
import { useMemo } from 'react'

import type { FlowGraph, FlowNode } from '../../api/types'
import { EmptyState } from '../../design/primitives'
import { layoutFlow, pathEdgeIds, sizeOf } from '../../lib/graph'
import { nodeTypes, type RFNode } from './nodes'

interface Props {
  flow: FlowGraph
  selected: string | null
  onSelect: (node: FlowNode) => void
  onRefocus: (node: FlowNode) => void
}

const MINIMAP_COLOR: Record<string, string> = {
  endpoint: 'var(--text-2)',
  function: 'var(--border-control)',
  external: 'var(--border-subtle)',
}

export function FlowCanvas({ flow, selected, onSelect, onRefocus }: Props) {
  const positions = useMemo(() => layoutFlow(flow), [flow])
  const byId = useMemo(() => new Map(flow.nodes.map((n) => [n.id, n])), [flow])
  const active = useMemo(() => pathEdgeIds(flow, selected), [flow, selected])

  const nodes: RFNode[] = useMemo(
    () =>
      flow.nodes.map((n) => {
        const { width, height } = sizeOf(n)
        return {
          id: n.id,
          type: n.type === 'endpoint' ? 'endpoint' : n.type === 'external' ? 'external' : 'function',
          position: positions.get(n.id) ?? { x: 0, y: 0 },
          width,
          height,
          selected: n.id === selected,
          draggable: false,
          data: { node: n, isRoot: n.id === flow.root },
          ariaLabel: `${n.type} ${n.label}`,
        }
      }),
    [flow, positions, selected],
  )

  const edges: Edge[] = useMemo(
    () =>
      flow.edges.map((e) => {
        const isActive = active.has(e.id)
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          className: isActive ? 'edge-active' : active.size ? 'edge-dim' : undefined,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: isActive ? 'var(--accent-500)' : 'var(--border-control)',
          },
          focusable: false,
        }
      }),
    [flow, active],
  )

  if (flow.nodes.length === 0) {
    return (
      <EmptyState icon={<Network size={28} aria-hidden />} title="Nothing to draw">
        This item has no resolved calls.
      </EmptyState>
    )
  }

  return (
    <ReactFlow
      key={`${flow.root}|${flow.depth}|${flow.direction}`}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
      minZoom={0.2}
      maxZoom={1.6}
      nodesDraggable={false}
      nodesConnectable={false}
      zoomOnDoubleClick={false}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, n) => onSelect(n.data.node)}
      onNodeDoubleClick={(_, n) => onRefocus(n.data.node)}
      // Keyboard selection (Enter/Space on a focused node) arrives here, not via
      // onNodeClick. `onNodesChange` only reports *user* selection, unlike
      // `onSelectionChange`, which also echoes our own controlled `selected`
      // flags back and caused an update loop.
      onNodesChange={(changes) => {
        for (const c of changes) {
          if (c.type === 'select' && c.selected && c.id !== selected) {
            const n = byId.get(c.id)
            if (n) onSelect(n)
          }
        }
      }}
      aria-label="Call graph"
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border-subtle)" />
      <Controls showInteractive={false} position="bottom-left" />
      <MiniMap
        pannable
        zoomable
        position="bottom-right"
        nodeColor={(n) => MINIMAP_COLOR[n.type ?? 'function']}
        nodeStrokeWidth={0}
        ariaLabel="Graph overview"
      />
    </ReactFlow>
  )
}
