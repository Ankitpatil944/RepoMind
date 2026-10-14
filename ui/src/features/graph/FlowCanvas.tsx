import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
} from '@xyflow/react'
import { Network } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { FlowGraph, FlowNode } from '../../api/types'
import { EmptyState } from '../../design/primitives'
import { layoutFlow, neighbourhood, pathEdgeIds, sizeOf } from '../../lib/graph'
import { edgeTypes, type RFEdge } from './edges'
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
  // Hovering spotlights a node and its direct neighbours; everything else recedes.
  const [hover, setHover] = useState<string | null>(null)
  const spotlight = useMemo(() => neighbourhood(flow, hover), [flow, hover])
  // Column index (0 = leftmost) drives the staggered reveal: the graph grows
  // outward from the root instead of appearing all at once.
  const columns = useMemo(() => {
    const xs = [...new Set([...positions.values()].map((p) => Math.round(p.x)))].sort((a, b) => a - b)
    return new Map(xs.map((x, i) => [x, i]))
  }, [positions])

  const nodes: RFNode[] = useMemo(
    () =>
      flow.nodes.map((n) => {
        const { width, height } = sizeOf(n)
        const pos = positions.get(n.id) ?? { x: 0, y: 0 }
        return {
          id: n.id,
          type: n.type === 'endpoint' ? 'endpoint' : n.type === 'external' ? 'external' : 'function',
          position: pos,
          width,
          height,
          selected: n.id === selected,
          draggable: false,
          className: hover && !spotlight.has(n.id) ? 'node-dim' : undefined,
          data: { node: n, isRoot: n.id === flow.root, col: columns.get(Math.round(pos.x)) ?? 0 },
          ariaLabel: `${n.type} ${n.label}`,
        }
      }),
    [flow, positions, selected, columns, hover, spotlight],
  )

  const edges: RFEdge[] = useMemo(
    () =>
      flow.edges.map((e) => {
        const isActive = active.has(e.id) || (!!hover && (e.source === hover || e.target === hover))
        const receded = !!hover && e.source !== hover && e.target !== hover
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'flow',
          data: {
            active: isActive,
            dim: receded || (!isActive && active.size > 0),
            delay: ((columns.get(Math.round(positions.get(e.source)?.x ?? 0)) ?? 0) * 0.35) % 3,
          },
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
    [flow, active, columns, positions, hover],
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
      edgeTypes={edgeTypes}
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
      onNodeMouseEnter={(_, n) => setHover(n.id)}
      onNodeMouseLeave={() => setHover(null)}
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
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="var(--border-subtle)" />
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
