import * as Tabs from '@radix-ui/react-tabs'
import {
  Boxes,
  ExternalLink,
  Globe,
  KeyRound,
  LayoutDashboard,
  ListTree,
  Network,
  PanelLeft,
  PanelRight,
  ShieldCheck,
} from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAsk, useCapabilities, useEndpoints, useExplain, useFlow, useRepos } from '../api/hooks'
import type { ChunkRef, Endpoint, FlowNode, HotFunction, ModuleNode, Source, SymbolHit } from '../api/types'
import { Constellation } from '../design/Constellation'
import { EmptyState, ErrorNote, IconButton, MethodPill, RoleBadge, roleOf, Segmented, Spinner } from '../design/primitives'
import { cx } from '../lib/cx'
import { useAppState, type InspectorTab, type View } from '../lib/hash'
import { AskBar } from '../features/explain/AskBar'
import type { AskState, ExplainState } from '../features/explain/ExplainPane'
import { EvidencePane } from '../features/evidence/EvidencePane'
import { Explorer } from '../features/explorer/Explorer'
import { Outline } from '../features/graph/Outline'
import { CommandPalette } from '../features/palette/CommandPalette'
import { SummaryPane } from '../features/summary/SummaryPane'
import { Header } from './Header'
import { IndexDialog } from './IndexDialog'
import { usePanelWidth } from './usePanelWidth'

// Heavy dependencies (React Flow + dagre, CodeMirror, markdown) load on demand.
const FlowCanvas = lazy(() => import('../features/graph/FlowCanvas').then((m) => ({ default: m.FlowCanvas })))
const SourcePane = lazy(() => import('../features/source/SourcePane').then((m) => ({ default: m.SourcePane })))
const ExplainPane = lazy(() => import('../features/explain/ExplainPane').then((m) => ({ default: m.ExplainPane })))
const Overview = lazy(() => import('../features/overview/Overview').then((m) => ({ default: m.Overview })))
const ArchitectureCanvas = lazy(() =>
  import('../features/architecture/ArchitectureCanvas').then((m) => ({ default: m.ArchitectureCanvas })),
)

const Loading = ({ label }: { label: string }) => (
  <div className="p-4">
    <Spinner label={label} />
  </div>
)

type Pane = 'explorer' | 'graph' | 'inspector'

const TAB_CLASS =
  'relative h-10 px-3.5 text-[13px] font-medium text-text-2 transition-colors duration-150 hover:text-text-1 data-[state=active]:text-text-1 ' +
  "data-[state=active]:after:absolute data-[state=active]:after:inset-x-3 data-[state=active]:after:bottom-0 data-[state=active]:after:h-0.5 data-[state=active]:after:rounded data-[state=active]:after:bg-accent-500 data-[state=active]:after:content-['']"

const VIEWS: Array<{ id: View; label: string; Icon: typeof Network }> = [
  { id: 'overview', label: 'Overview', Icon: LayoutDashboard },
  { id: 'architecture', label: 'Architecture', Icon: Boxes },
  { id: 'flow', label: 'Call flow', Icon: Network },
]

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)
}

export default function App() {
  const [s, set] = useAppState()
  const repos = useRepos()
  const repoList = repos.data ?? []
  const repo = repoList.find((r) => r.id === s.repo) ?? null

  const [pane, setPane] = useState<Pane>('graph')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [indexOpen, setIndexOpen] = useState(false)
  const [archSel, setArchSel] = useState<ModuleNode | null>(null)
  const askInput = useRef<HTMLInputElement>(null)
  const [explorerOpen, setExplorerOpen] = useState(true)
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const explorerPanel = usePanelWidth('rm.explorer.v2', 264, 200, 460, 'right')
  const inspectorPanel = usePanelWidth('rm.inspector.v2', 420, 320, 720, 'left')
  const capabilities = useCapabilities()
  const aiStatus = capabilities.data?.llm.status ?? null

  // The explorer lists endpoints/files, which the dependency map doesn't use:
  // hand that width to the canvas, and give it back on the other views.
  useEffect(() => {
    setExplorerOpen(s.view !== 'architecture')
  }, [s.view])

  // Pick the newest repo when none (or an unknown one) is in the URL.
  useEffect(() => {
    if (!repos.data?.length) return
    if (s.repo === null || !repos.data.some((r) => r.id === s.repo)) {
      set({ repo: Math.max(...repos.data.map((r) => r.id)) })
    }
  }, [repos.data, s.repo, set])

  const repoId = repo?.id ?? null
  const endpoints = useEndpoints(repoId)
  const flowQuery = useFlow(repoId, { endpointId: s.ep, chunkId: s.ch }, s.depth, s.dir)
  const flow = flowQuery.data
  const selectedNode = useMemo(
    () => flow?.nodes.find((n) => n.id === s.sel) ?? null,
    [flow, s.sel],
  )

  /* ---------------------------------------------------------- selection */

  const selectEndpoint = useCallback(
    (e: Endpoint) => {
      set({
        view: 'flow', ep: e.id, ch: null, sel: `e:${e.id}`,
        file: e.file, start: e.line, end: e.line, tab: 'summary',
      })
      setPane('graph')
    },
    [set],
  )
  const openChunk = useCallback(
    (r: ChunkRef | HotFunction) => {
      set({
        view: 'flow', ep: null, ch: r.chunk_id, sel: `c:${r.chunk_id}`,
        file: r.file, start: 'line' in r ? r.line : null, end: 'line' in r ? r.line : null, tab: 'summary',
      })
      setPane('graph')
    },
    [set],
  )
  const selectSymbol = useCallback(
    (sym: SymbolHit) => {
      set({
        view: 'flow', ep: null, ch: sym.chunk_id, sel: `c:${sym.chunk_id}`,
        file: sym.file, start: sym.start_line, end: sym.end_line, tab: 'summary',
      })
      setPane('graph')
    },
    [set],
  )
  const openFile = useCallback(
    (path: string) => {
      setArchSel(null)
      set({ file: path, start: null, end: null, sel: null, tab: 'summary' })
      setPane('inspector')
    },
    [set],
  )
  const selectNode = useCallback(
    (n: FlowNode) => {
      const patch: Parameters<typeof set>[0] = { sel: n.id }
      if (n.file) {
        patch.file = n.file
        patch.start = n.start_line ?? null
        patch.end = n.end_line ?? null
      }
      set(patch)
    },
    [set],
  )
  const refocus = useCallback(
    (n: FlowNode) => {
      if (n.type === 'endpoint' && n.endpoint_id !== undefined) {
        set({ ep: n.endpoint_id, ch: null, sel: n.id })
      } else if (n.chunk_id !== undefined) {
        set({ ch: n.chunk_id, ep: null, sel: n.id })
      }
    },
    [set],
  )
  const selectModule = useCallback(
    (m: ModuleNode) => {
      setArchSel(m)
      set({ sel: null, tab: 'summary', ...(m.kind === 'file' ? { file: m.path, start: null, end: null } : {}) })
      setPane('inspector')
    },
    [set],
  )
  const setView = useCallback((view: View) => set({ view }), [set])

  /* ---------------------------------------------------------------- AI */

  const askMut = useAsk()
  const explainMut = useExplain()
  const [ask, setAsk] = useState<AskState | null>(null)
  const [explain, setExplain] = useState<ExplainState | null>(null)

  const doAsk = useCallback(
    (question: string) => {
      if (repoId === null) return
      set({ tab: 'explain' })
      setPane('inspector')
      setAsk({ question, pending: true, result: null, error: null })
      askMut.mutate(
        { repo: repoId, question },
        {
          onSuccess: (result) => setAsk({ question, pending: false, result, error: null }),
          onError: (e) => setAsk({ question, pending: false, result: null, error: e.message }),
        },
      )
    },
    [repoId, askMut, set],
  )

  const doExplain = useCallback(
    (chunkId: number) => {
      if (repoId === null) return
      setExplain({ chunkId, pending: true, result: null, error: null })
      explainMut.mutate(
        { repo: repoId, chunkId },
        {
          onSuccess: (result) => setExplain({ chunkId, pending: false, result, error: null }),
          onError: (e) => setExplain({ chunkId, pending: false, result: null, error: e.message }),
        },
      )
    },
    [repoId, explainMut],
  )

  const cite = useCallback(
    (src: Source) => {
      set({
        view: 'flow',
        ep: null,
        ch: src.chunk_id ?? null,
        sel: src.chunk_id ? `c:${src.chunk_id}` : null,
        file: src.file,
        start: src.start_line,
        end: src.end_line,
        tab: 'source',
      })
    },
    [set],
  )

  /* ---------------------------------------------------------- shortcuts */

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
        return
      }
      if (isEditable(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '/') {
        e.preventDefault()
        askInput.current?.focus()
      } else if (e.key === '[') {
        setExplorerOpen((o) => !o)
      } else if (e.key === ']') {
        setInspectorOpen((o) => !o)
      } else if (e.key === 'Escape' && s.sel) {
        set({ sel: null })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [s.sel, set])

  /* ------------------------------------------------------------- render */

  if (repos.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner label="Connecting to RepoMind" />
      </div>
    )
  }

  if (repos.error) {
    return (
      <div className="mx-auto flex h-full max-w-lg items-center p-6">
        <ErrorNote title="Cannot reach the RepoMind API">
          {repos.error.message}
        </ErrorNote>
      </div>
    )
  }

  const external = selectedNode?.type === 'external' ? selectedNode.label : null
  const hasFocus = s.ep !== null || s.ch !== null
  // What the Summary tab describes: the selected graph node's function (for an
  // endpoint, its handler), else the graph's focus function, else a file/folder.
  const summaryChunk =
    selectedNode && selectedNode.type !== 'external'
      ? (selectedNode.chunk_id ?? selectedNode.handler_chunk_id ?? null)
      : s.sel === null && !archSel
        ? s.ch
        : null

  return (
    <div className="flex h-full flex-col">
      <Header
        repos={repoList}
        repo={repo}
        ai={aiStatus}
        onRepo={(id) => {
          setArchSel(null)
          set({ repo: id, ep: null, ch: null, sel: null, file: null, start: null, end: null, arch: '' })
        }}
        onPalette={() => setPaletteOpen(true)}
        onIndex={() => setIndexOpen(true)}
      />

      {repoList.length === 0 ? (
        <main className="min-h-0 flex-1">
          <EmptyState icon={<Constellation />} title="Turn a codebase into a map you can ask questions of">
            RepoMind traces routes through handlers, services and auth checks, then explains each path with cited source.
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setIndexOpen(true)}
                className="h-9 rounded-md bg-accent-600 px-4 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-500"
              >
                Index a project
              </button>
            </div>
          </EmptyState>
        </main>
      ) : (
        <>
          <div role="tablist" aria-label="Panels" className="flex shrink-0 border-b border-border-subtle bg-bg-1 lg:hidden">
            {(['explorer', 'graph', 'inspector'] as const).map((p) => (
              <button
                key={p}
                type="button"
                role="tab"
                aria-selected={pane === p}
                onClick={() => setPane(p)}
                className={cx(
                  'h-10 flex-1 text-[13px] font-medium capitalize',
                  pane === p ? 'text-text-1 shadow-[inset_0_-2px_0_var(--accent-500)]' : 'text-text-2',
                )}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="flex min-h-0 flex-1">
            {/* Explorer */}
            <aside
              aria-label="Explorer"
              style={{ width: explorerPanel.width }}
              className={cx(
                'min-h-0 shrink-0 flex-col border-r border-border-subtle bg-bg-1 max-lg:!w-full max-lg:flex-1',
                pane === 'explorer' ? 'flex' : 'hidden lg:flex',
                !explorerOpen && 'lg:!hidden',
              )}
            >
              {repoId !== null && (
                <Explorer
                  repo={repoId}
                  tab={s.ex}
                  onTab={(ex) => set({ ex })}
                  activeFile={s.file}
                  activeEndpoint={s.ep}
                  activeChunk={s.ch}
                  onSelectFile={openFile}
                  onSelectEndpoint={selectEndpoint}
                  onSelectSymbol={selectSymbol}
                />
              )}
            </aside>
            <div
              {...explorerPanel.separatorProps}
              aria-label="Resize explorer"
              className={cx(
                'hidden w-1 shrink-0 cursor-col-resize bg-transparent transition-colors duration-150 hover:bg-accent-500/60',
                explorerOpen && 'lg:block',
              )}
            />

            {/* Canvas */}
            <main
              aria-label="Workspace"
              className={cx('min-h-0 min-w-0 flex-1 flex-col bg-bg-0', pane === 'graph' ? 'flex' : 'hidden lg:flex')}
            >
              <div className="shrink-0 border-b border-border-subtle bg-bg-1">
                <div className="flex items-center px-2">
                  <IconButton
                    label={explorerOpen ? 'Hide explorer  [' : 'Show explorer  ['}
                    pressed={explorerOpen}
                    onClick={() => setExplorerOpen((o) => !o)}
                    className="max-lg:hidden"
                  >
                    <PanelLeft size={16} aria-hidden />
                  </IconButton>
                  <div role="tablist" aria-label="View" className="flex items-center">
                    {VIEWS.map(({ id, label, Icon }) => (
                      <button
                        key={id}
                        type="button"
                        role="tab"
                        aria-selected={s.view === id}
                        onClick={() => setView(id)}
                        className={cx(
                          'relative inline-flex h-10 items-center gap-1.5 whitespace-nowrap px-3.5 text-[13px] font-medium transition-colors duration-150',
                          s.view === id
                            ? "text-text-1 after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded after:bg-accent-500 after:content-['']"
                            : 'text-text-2 hover:text-text-1',
                        )}
                      >
                        <Icon size={14} aria-hidden />
                        {label}
                      </button>
                    ))}
                  </div>
                  <IconButton
                    label={inspectorOpen ? 'Hide inspector  ]' : 'Show inspector  ]'}
                    pressed={inspectorOpen}
                    onClick={() => setInspectorOpen((o) => !o)}
                    className="ml-auto max-lg:hidden"
                  >
                    <PanelRight size={16} aria-hidden />
                  </IconButton>
                </div>

                {s.view === 'flow' && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-border-subtle px-3 py-1.5">
                    <Segmented
                      label="Direction"
                      value={s.dir}
                      onChange={(dir) => set({ dir })}
                      options={[
                        { value: 'down', label: 'Calls' },
                        { value: 'up', label: 'Callers' },
                        { value: 'both', label: 'Both' },
                      ]}
                    />
                    <Segmented
                      label="Depth"
                      value={String(s.depth)}
                      onChange={(v) => set({ depth: Number(v) })}
                      options={[1, 2, 3, 4].map((d) => ({ value: String(d), label: `${d} hop${d > 1 ? 's' : ''}` }))}
                    />
                    <IconButton
                      label={s.outline ? 'Show graph' : 'Show as outline (text)'}
                      pressed={s.outline}
                      onClick={() => set({ outline: !s.outline })}
                      className="ml-auto"
                    >
                      <ListTree size={16} aria-hidden />
                    </IconButton>
                  </div>
                )}
              </div>

              <div className="relative min-h-0 flex-1" key={s.view}>
                {s.view === 'overview' && repo && (
                  <Suspense fallback={<Loading label="Summarising the repository" />}>
                    <Overview
                      repo={repo}
                      endpoints={endpoints.data ?? []}
                      onOpenChunk={openChunk}
                      onOpenFile={openFile}
                      onOpenEndpoint={selectEndpoint}
                      onOpenArchitecture={() => setView('architecture')}
                      onShowEndpoints={() => set({ ex: 'endpoints' })}
                    />
                  </Suspense>
                )}

                {s.view === 'architecture' && repoId !== null && (
                  <Suspense fallback={<Loading label="Loading architecture" />}>
                    <ArchitectureCanvas
                      repo={repoId}
                      root={s.arch}
                      selected={archSel?.id ?? null}
                      onRoot={(arch) => {
                        setArchSel(null)
                        set({ arch })
                      }}
                      onSelect={selectModule}
                      onOpenFile={openFile}
                    />
                  </Suspense>
                )}

                {s.view === 'flow' && (
                  <div className="view-enter relative h-full">
                    {!hasFocus && !endpoints.isLoading && (
                      <EmptyState icon={<Network size={30} aria-hidden />} title="Pick an endpoint or function">
                        Choose one from the explorer, search with <kbd className="font-mono">Ctrl K</kbd>, or
                        start from the Overview.
                        <TopEndpoints endpoints={endpoints.data ?? []} onPick={selectEndpoint} />
                      </EmptyState>
                    )}
                    {hasFocus && flowQuery.isLoading && (
                      <div className="p-4">
                        <Spinner label="Tracing calls" />
                      </div>
                    )}
                    {hasFocus && flowQuery.error && (
                      <div className="p-4">
                        <ErrorNote title="Could not build the graph">{flowQuery.error.message}</ErrorNote>
                      </div>
                    )}
                    {flow && hasFocus && !flowQuery.error &&
                      (s.outline ? (
                        <Outline flow={flow} selected={s.sel} onSelect={selectNode} />
                      ) : (
                        <Suspense fallback={<Loading label="Loading graph" />}>
                          <div className="graph-stage h-full w-full">
                            <FlowCanvas flow={flow} selected={s.sel} onSelect={selectNode} onRefocus={refocus} />
                          </div>
                        </Suspense>
                      ))}

                    {flow?.truncated && (
                      <div
                        role="status"
                        className="absolute left-3 top-3 rounded-md border border-border-control bg-bg-2 px-2.5 py-1.5 text-[12.5px]"
                      >
                        Showing the first {flow.nodes.length} nodes. Lower the depth or focus a narrower function.
                      </div>
                    )}
                    {flow && !flow.truncated && flow.nodes.length > 30 && s.depth > 1 && (
                      <div
                        role="status"
                        className="absolute left-3 top-3 rounded-md border border-border-control bg-bg-2 px-2.5 py-1.5 text-[12.5px]"
                      >
                        {flow.nodes.length} nodes. Try fewer hops, or the outline view, to simplify.
                      </div>
                    )}
                    {flow && hasFocus && <Legend />}
                  </div>
                )}
              </div>
            </main>

            <div
              {...inspectorPanel.separatorProps}
              aria-label="Resize inspector"
              className={cx(
                'hidden w-1 shrink-0 cursor-col-resize bg-transparent transition-colors duration-150 hover:bg-accent-500/60',
                inspectorOpen && 'lg:block',
              )}
            />

            {/* Inspector */}
            <aside
              aria-label="Inspector"
              style={{ width: inspectorPanel.width }}
              className={cx(
                'min-h-0 shrink-0 flex-col border-l border-border-subtle bg-bg-1 max-lg:!w-full max-lg:flex-1',
                pane === 'inspector' ? 'flex' : 'hidden lg:flex',
                !inspectorOpen && 'lg:!hidden',
              )}
            >
              <Tabs.Root
                value={s.tab}
                onValueChange={(v) => set({ tab: v as InspectorTab })}
                className="flex h-full min-h-0 flex-col"
              >
                <Tabs.List aria-label="Inspector" className="flex shrink-0 border-b border-border-subtle">
                  <Tabs.Trigger value="summary" className={TAB_CLASS}>
                    Summary
                  </Tabs.Trigger>
                  <Tabs.Trigger value="source" className={TAB_CLASS}>
                    Source
                  </Tabs.Trigger>
                  <Tabs.Trigger value="explain" className={TAB_CLASS}>
                    Explain
                  </Tabs.Trigger>
                  <Tabs.Trigger value="evidence" className={TAB_CLASS}>
                    Evidence
                  </Tabs.Trigger>
                </Tabs.List>
                <Tabs.Content value="summary" className="min-h-0 flex-1 outline-none">
                  {repoId !== null &&
                    (external ? (
                      <EmptyState title={external}>
                        This call is defined outside the repository (a library) or resolved dynamically, so
                        there is nothing to summarise here.
                      </EmptyState>
                    ) : (
                      <SummaryPane
                        repo={repoId}
                        chunkId={summaryChunk}
                        file={s.file}
                        module={archSel}
                        onOpenChunk={openChunk}
                        onOpenFile={openFile}
                        onViewSource={() => set({ tab: 'source' })}
                      />
                    ))}
                </Tabs.Content>
                <Tabs.Content value="source" className="min-h-0 flex-1 outline-none">
                  {repoId !== null && (
                    <Suspense fallback={<Loading label="Loading editor" />}>
                      <SourcePane
                        repo={repoId}
                        file={s.file}
                        start={s.start}
                        end={s.end}
                        externalLabel={external}
                        onJump={(start, end) => set({ start, end })}
                      />
                    </Suspense>
                  )}
                </Tabs.Content>
                <Tabs.Content value="explain" className="min-h-0 flex-1 outline-none">
                  <Suspense fallback={<Loading label="Loading" />}>
                    <ExplainPane
                      node={selectedNode}
                      ask={ask}
                      explain={explain}
                      aiStatus={aiStatus}
                      onExplain={doExplain}
                      onCite={cite}
                      onShowSummary={() => set({ tab: 'summary' })}
                    />
                  </Suspense>
                </Tabs.Content>
                <Tabs.Content value="evidence" className="min-h-0 flex-1 outline-none">
                  <EvidencePane node={selectedNode} flow={flow} onSelect={selectNode} />
                </Tabs.Content>
              </Tabs.Root>
            </aside>
          </div>

          <AskBar ref={askInput} disabled={repoId === null} pending={!!ask?.pending} aiStatus={aiStatus} onAsk={doAsk} />
        </>
      )}

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        repo={repoId}
        onEndpoint={selectEndpoint}
        onSymbol={selectSymbol}
        onFile={openFile}
        onAsk={doAsk}
      />
      <IndexDialog
        open={indexOpen}
        onClose={() => setIndexOpen(false)}
        onIndexed={(id) => {
          setArchSel(null)
          set({ repo: id, ep: null, ch: null, sel: null, file: null, start: null, end: null, arch: '', view: 'overview' })
        }}
      />
    </div>
  )
}

function TopEndpoints({ endpoints, onPick }: { endpoints: Endpoint[]; onPick: (e: Endpoint) => void }) {
  const top = [...endpoints]
    .sort((a, b) => Number(b.handles_authentication) - Number(a.handles_authentication))
    .slice(0, 5)
  if (top.length === 0) return null
  return (
    <ul className="mt-4 space-y-1 text-left">
      {top.map((e) => (
        <li key={e.id}>
          <button
            type="button"
            onClick={() => onPick(e)}
            className="flex w-full items-center gap-2 rounded-md border border-border-subtle bg-bg-2 px-3 py-2 transition-colors duration-150 hover:bg-bg-3"
          >
            <MethodPill method={e.method} />
            <span className="truncate font-mono text-[12.5px]">{e.path}</span>
            <RoleBadge role={roleOf(e)} compact className="ml-auto" />
          </button>
        </li>
      ))}
    </ul>
  )
}

function Legend() {
  return (
    <ul
      aria-label="Legend"
      className="pointer-events-none absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-4 whitespace-nowrap rounded-md border border-border-subtle bg-bg-1/90 px-3 py-1.5 text-[12px] text-text-2"
    >
      <li className="flex items-center gap-1.5">
        <KeyRound size={13} className="text-auth" aria-hidden /> Auth
      </li>
      <li className="flex items-center gap-1.5">
        <ShieldCheck size={13} className="text-ok" aria-hidden /> Protected
      </li>
      <li className="flex items-center gap-1.5">
        <Globe size={13} aria-hidden /> Public
      </li>
      <li className="flex items-center gap-1.5">
        <ExternalLink size={13} aria-hidden /> External (dashed)
      </li>
    </ul>
  )
}
