import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import { ChevronRight, FileCode2, Folder, Home, Route } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useModules } from '../../api/hooks'
import type { ModuleGraph, ModuleNode } from '../../api/types'
import { EmptyState, ErrorNote, Spinner } from '../../design/primitives'
import { cx } from '../../lib/cx'
import { edgeTypes, type RFEdge } from '../graph/edges'
import { FitController, type FitCandidate } from '../graph/FitController'
import { layoutBounds, layoutGrid } from '../../lib/graph'
import { langColor } from '../overview/colors'

type ModuleData = { m: ModuleNode; maxLoc: number; col: number; dim: boolean } & Record<string, unknown>
type RFModule = Node<ModuleData, 'module'>

const SIZE = { width: 224, height: 92 }
const SELECTED =
  'border-accent-500 shadow-[0_0_0_1px_var(--accent-500),0_0_24px_color-mix(in_srgb,var(--accent-500)_28%,transparent)] node-selected-ping'

function ModuleCard({ data, selected }: NodeProps<RFModule>) {
  const m = data.m
  const Icon = m.kind === 'dir' ? Folder : FileCode2
  const pct = Math.max(4, Math.round((m.loc / data.maxLoc) * 100))
  return (
    <div
      className={cx(
        'node-card node-enter h-full w-full rounded-lg border bg-bg-2 px-3 py-2',
        selected ? SELECTED : 'border-border-control',
      )}
      style={{ animationDelay: `${Math.min(data.col, 8) * 70}ms` }}
      title={m.kind === 'dir' ? 'Double-click to open this folder' : m.path}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <div className="flex items-center gap-2">
        <Icon size={14} className="shrink-0 text-text-2" aria-hidden />
        <span className="truncate font-mono text-[13px] font-medium">{m.label}</span>
        {m.endpoints > 0 && (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-text-1">
            <Route size={11} aria-hidden />
            {m.endpoints}
          </span>
        )}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-3" aria-hidden>
        <div
          className="bar-grow h-full rounded-full"
          style={{ width: `${pct}%`, background: langColor(m.languages[0] ?? '') }}
        />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        <span className="metric-chip">{m.loc.toLocaleString()} loc</span>
        {m.kind === 'dir' && <span className="metric-chip">{m.files} files</span>}
        <span className="metric-chip">{m.symbols} symbols</span>
        {m.complexity > 0 && <span className="metric-chip">cx {m.complexity}</span>}
      </div>
    </div>
  )
}

const nodeTypes = { module: ModuleCard }

function layout(g: ModuleGraph): Map<string, { x: number; y: number }> {
  // Independent modules (e.g. separate microservices): a grid reads better than one column.
  if (g.edges.length === 0) return layoutGrid(g.nodes.map((n) => n.id), SIZE)
  const d = new dagre.graphlib.Graph()
  d.setGraph({ rankdir: 'LR', nodesep: 20, ranksep: 64, marginx: 16, marginy: 16 })
  d.setDefaultEdgeLabel(() => ({}))
  for (const n of g.nodes) d.setNode(n.id, { ...SIZE })
  for (const e of g.edges) d.setEdge(e.source, e.target)
  dagre.layout(d)
  return new Map(
    g.nodes.map((n) => {
      const p = d.node(n.id)
      return [n.id, { x: p.x - SIZE.width / 2, y: p.y - SIZE.height / 2 }]
    }),
  )
}

interface Props {
  repo: number
  root: string
  selected: string | null
  onRoot: (path: string) => void
  onSelect: (m: ModuleNode) => void
  onOpenFile: (path: string) => void
}

export function ArchitectureCanvas({ repo, root, selected, onRoot, onSelect, onOpenFile }: Props) {
  const { data, isLoading, error } = useModules(repo, root, 'dir')
  const [hover, setHover] = useState<string | null>(null)

  // Many repos keep everything under one folder (services/, src/, packages/).
  // A map of "services, libs, one script" says nothing, so open inside it once.
  // Going back to the root by hand is respected: this runs once per repo.
  const decided = useRef<number | null>(null)
  useEffect(() => {
    if (!data || root !== '' || decided.current === repo || data.root !== '') return
    decided.current = repo
    const total = data.nodes.reduce((a, n) => a + n.loc, 0)
    const top = [...data.nodes].sort((a, b) => b.loc - a.loc)[0]
    if (top && top.kind === 'dir' && total > 0 && top.loc / total >= 0.85 && data.nodes.length <= 6) {
      onRoot(top.path)
    }
  }, [data, root, repo, onRoot])

  const positions = useMemo(() => (data ? layout(data) : new Map()), [data])
  const maxLoc = useMemo(() => Math.max(1, ...(data?.nodes ?? []).map((n) => n.loc)), [data])
  // Frames to try: everything, then the most-connected module and its neighbours.
  const candidates = useMemo<FitCandidate[]>(() => {
    if (!data || data.nodes.length === 0) return []
    const sized = data.nodes.map((n) => ({ id: n.id, ...SIZE }))
    const top = [...data.nodes].sort((a, b) => b.degree - a.degree)[0]
    const ids = new Set([top.id])
    for (const e of data.edges) {
      if (e.source === top.id) ids.add(e.target)
      if (e.target === top.id) ids.add(e.source)
    }
    const near = [...ids]
    return [
      { ids: [], bounds: layoutBounds(sized, positions) },
      {
        ids: near,
        bounds: layoutBounds(
          sized.filter((n) => ids.has(n.id)),
          positions,
        ),
      },
    ]
  }, [data, positions])
  const byId = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data])
  const spotlight = useMemo(() => {
    const s = new Set<string>()
    if (!hover || !data) return s
    s.add(hover)
    for (const e of data.edges) {
      if (e.source === hover) s.add(e.target)
      if (e.target === hover) s.add(e.source)
    }
    return s
  }, [data, hover])

  const columns = useMemo(() => {
    const xs = [...new Set([...positions.values()].map((p) => Math.round(p.x)))].sort((a, b) => a - b)
    return new Map(xs.map((x, i) => [x, i]))
  }, [positions])

  const nodes: RFModule[] = useMemo(
    () =>
      (data?.nodes ?? []).map((m) => {
        const pos = positions.get(m.id) ?? { x: 0, y: 0 }
        return {
          id: m.id,
          type: 'module' as const,
          position: pos,
          width: SIZE.width,
          height: SIZE.height,
          draggable: false,
          selected: m.id === selected,
          className: hover && !spotlight.has(m.id) ? 'node-dim' : undefined,
          data: { m, maxLoc, col: columns.get(Math.round(pos.x)) ?? 0, dim: false },
          ariaLabel: `${m.kind} ${m.path}`,
        }
      }),
    [data, positions, maxLoc, columns, selected, hover, spotlight],
  )

  const maxWeight = Math.max(1, ...(data?.edges ?? []).map((e) => e.weight))
  const edges: RFEdge[] = useMemo(
    () =>
      (data?.edges ?? []).map((e) => {
        const touches = !!hover && (e.source === hover || e.target === hover)
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'flow' as const,
          style: { strokeWidth: 1.25 + (e.weight / maxWeight) * 3 },
          data: {
            active: touches,
            dim: !!hover && !touches,
            delay: ((columns.get(Math.round(positions.get(e.source)?.x ?? 0)) ?? 0) * 0.35) % 3,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: touches ? 'var(--accent-500)' : 'var(--border-control)',
          },
          focusable: false,
        }
      }),
    [data, hover, maxWeight, columns, positions],
  )

  return (
    <div className="view-enter flex h-full min-h-0 flex-col">
      <nav
        aria-label="Folder path"
        className="flex shrink-0 flex-wrap items-center gap-1 border-b border-border-subtle bg-bg-1 px-3 py-1.5 text-[12.5px]"
      >
        <button type="button" onClick={() => onRoot('')} className="link-btn" aria-label="Repository root">
          <Home size={13} aria-hidden /> root
        </button>
        {(data?.breadcrumb ?? root.split('/').filter(Boolean)).map((part, i, all) => {
          const path = all.slice(0, i + 1).join('/')
          return (
            <span key={path} className="inline-flex items-center gap-1">
              <ChevronRight size={12} className="text-text-3" aria-hidden />
              <button
                type="button"
                onClick={() => onRoot(path)}
                aria-current={i === all.length - 1 ? 'page' : undefined}
                className={cx('link-btn', i === all.length - 1 && 'text-text-1')}
              >
                {part}
              </button>
            </span>
          )
        })}
        <span className="ml-auto text-text-2">
          Arrows point from a module to the modules it imports. Double-click a folder to open it.
        </span>
      </nav>

      <div className="graph-stage relative min-h-0 flex-1">
        {isLoading && (
          <div className="p-4">
            <Spinner label="Mapping modules" />
          </div>
        )}
        {error && (
          <div className="p-4">
            <ErrorNote title="Could not build the module map">{error.message}</ErrorNote>
          </div>
        )}
        {data && data.nodes.length === 0 && (
          <EmptyState icon={<Folder size={28} aria-hidden />} title="Nothing here">
            No indexed files under this folder.
          </EmptyState>
        )}
        {data && data.nodes.length > 0 && (
          <ReactFlow
            key={`${repo}|${root}`}
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            colorMode="dark"
            defaultViewport={{ x: 24, y: 24, zoom: 0.85 }}
            minZoom={0.2}
            maxZoom={1.6}
            nodesDraggable={false}
            nodesConnectable={false}
            zoomOnDoubleClick={false}
            aria-label="Module dependency map"
            onNodeClick={(_, n) => onSelect(n.data.m)}
            onNodeDoubleClick={(_, n) => {
              const m = n.data.m
              if (m.kind === 'dir') onRoot(m.path)
              else onOpenFile(m.path)
            }}
            onNodeMouseEnter={(_, n) => setHover(n.id)}
            onNodeMouseLeave={() => setHover(null)}
            onNodesChange={(changes) => {
              for (const c of changes) {
                if (c.type === 'select' && c.selected && c.id !== selected) {
                  const m = byId.get(c.id)
                  if (m) onSelect(m)
                }
              }
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="var(--border-subtle)" />
            <Controls showInteractive={false} position="bottom-left" />
            <FitController candidates={candidates} deps={`${repo}|${root}|${data.nodes.length}`} />
            <MiniMap pannable zoomable position="bottom-right" style={{ width: 150, height: 96, marginBottom: 28 }} nodeColor="var(--border-control)" nodeStrokeWidth={0} />
          </ReactFlow>
        )}
        {data?.truncated && (
          <div role="status" className="absolute left-3 top-3 rounded-md border border-border-control bg-bg-2 px-2.5 py-1.5 text-[12.5px]">
            Showing the most connected 60 modules. Open a folder to see the rest.
          </div>
        )}
      </div>
    </div>
  )
}
