import dagre from '@dagrejs/dagre'

import type { FlowEdge, FlowGraph, FlowNode } from '../api/types'

export const NODE_SIZE = {
  endpoint: { width: 244, height: 70 },
  function: { width: 220, height: 62 },
  external: { width: 200, height: 46 },
} as const

export function sizeOf(node: FlowNode): { width: number; height: number } {
  if (node.type === 'endpoint') return NODE_SIZE.endpoint
  if (node.type === 'external') return NODE_SIZE.external
  return NODE_SIZE.function
}

/** Left-to-right layered layout. Pure: same graph in, same positions out. */
export function layoutFlow(flow: FlowGraph): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 26, ranksep: 70, marginx: 16, marginy: 16 })
  g.setDefaultEdgeLabel(() => ({}))
  // dagre stores x/y *on the label object*, so every node needs its own copy.
  for (const n of flow.nodes) g.setNode(n.id, { ...sizeOf(n) })
  for (const e of flow.edges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  const out = new Map<string, { x: number; y: number }>()
  for (const n of flow.nodes) {
    const p = g.node(n.id)
    const { width, height } = sizeOf(n)
    // dagre returns centres; React Flow wants top-left.
    out.set(n.id, { x: p.x - width / 2, y: p.y - height / 2 })
  }
  return out
}

function neighbours(edges: FlowEdge[]): Map<string, { id: string; edge: FlowEdge }[]> {
  const adj = new Map<string, { id: string; edge: FlowEdge }[]>()
  const add = (a: string, b: string, edge: FlowEdge) => {
    const list = adj.get(a) ?? []
    list.push({ id: b, edge })
    adj.set(a, list)
  }
  for (const e of edges) {
    add(e.source, e.target, e)
    add(e.target, e.source, e)
  }
  return adj
}

/** Edge ids on the shortest path between the graph root and a node. */
export function pathEdgeIds(flow: FlowGraph, target: string | null): Set<string> {
  const result = new Set<string>()
  if (!target || target === flow.root) return result
  const adj = neighbours(flow.edges)
  const prev = new Map<string, { from: string; edge: string }>()
  const queue = [flow.root]
  const seen = new Set(queue)
  while (queue.length) {
    const cur = queue.shift() as string
    if (cur === target) break
    for (const { id, edge } of adj.get(cur) ?? []) {
      if (!seen.has(id)) {
        seen.add(id)
        prev.set(id, { from: cur, edge: edge.id })
        queue.push(id)
      }
    }
  }
  let at = target
  while (prev.has(at)) {
    const step = prev.get(at) as { from: string; edge: string }
    result.add(step.edge)
    at = step.from
  }
  return result
}

export interface OutlineItem {
  node: FlowNode
  /** how this node relates to its parent in the outline */
  relation: 'root' | 'calls' | 'called by' | 'handles' | 'handled by'
  children: OutlineItem[]
}

/** Text alternative to the canvas: the same graph as a nested list. */
export function buildOutline(flow: FlowGraph): OutlineItem | null {
  const byId = new Map(flow.nodes.map((n) => [n.id, n]))
  const root = byId.get(flow.root)
  if (!root) return null
  const adj = neighbours(flow.edges)
  const seen = new Set<string>([root.id])

  const build = (node: FlowNode, relation: OutlineItem['relation']): OutlineItem => {
    const children: OutlineItem[] = []
    for (const { id, edge } of adj.get(node.id) ?? []) {
      const child = byId.get(id)
      if (!child || seen.has(id)) continue
      seen.add(id)
      const outgoing = edge.source === node.id
      const rel: OutlineItem['relation'] =
        edge.kind === 'handles' ? (outgoing ? 'handles' : 'handled by') : outgoing ? 'calls' : 'called by'
      children.push(build(child, rel))
    }
    return { node, relation, children }
  }
  return build(root, 'root')
}
