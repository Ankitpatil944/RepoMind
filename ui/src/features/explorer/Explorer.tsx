import * as Tabs from '@radix-ui/react-tabs'
import { Box, ChevronDown, ChevronRight, FileCode2, Folder, FunctionSquare, Search } from 'lucide-react'
import { useDeferredValue, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import { useEndpoints, useFiles, useSymbols } from '../../api/hooks'
import type { Endpoint, SymbolHit } from '../../api/types'
import { EmptyState, ErrorNote, MethodPill, RoleBadge, roleOf, Spinner, type Role } from '../../design/primitives'
import { cx } from '../../lib/cx'
import type { ExplorerTab } from '../../lib/hash'
import { ancestors, buildFileTree, flattenVisible } from '../../lib/tree'

interface Props {
  repo: number
  tab: ExplorerTab
  onTab: (t: ExplorerTab) => void
  activeFile: string | null
  activeEndpoint: number | null
  activeChunk: number | null
  onSelectFile: (path: string) => void
  onSelectEndpoint: (e: Endpoint) => void
  onSelectSymbol: (s: SymbolHit) => void
}

const TAB_CLASS =
  'relative h-9 flex-1 text-[13px] font-medium text-text-2 transition-colors duration-150 hover:text-text-1 data-[state=active]:text-text-1 ' +
  "data-[state=active]:after:absolute data-[state=active]:after:inset-x-3 data-[state=active]:after:bottom-0 data-[state=active]:after:h-0.5 data-[state=active]:after:rounded data-[state=active]:after:bg-accent-500 data-[state=active]:after:content-['']"

export function Explorer(props: Props) {
  const { tab, onTab } = props
  return (
    <Tabs.Root value={tab} onValueChange={(v) => onTab(v as ExplorerTab)} className="flex h-full min-h-0 flex-col">
      <Tabs.List aria-label="Explorer" className="flex shrink-0 border-b border-border-subtle">
        <Tabs.Trigger value="endpoints" className={TAB_CLASS}>
          Endpoints
        </Tabs.Trigger>
        <Tabs.Trigger value="files" className={TAB_CLASS}>
          Files
        </Tabs.Trigger>
        <Tabs.Trigger value="symbols" className={TAB_CLASS}>
          Symbols
        </Tabs.Trigger>
      </Tabs.List>
      <Tabs.Content value="endpoints" className="min-h-0 flex-1 outline-none">
        <EndpointList {...props} />
      </Tabs.Content>
      <Tabs.Content value="files" className="min-h-0 flex-1 outline-none">
        <FileTree {...props} />
      </Tabs.Content>
      <Tabs.Content value="symbols" className="min-h-0 flex-1 outline-none">
        <SymbolList {...props} />
      </Tabs.Content>
    </Tabs.Root>
  )
}

function FilterBox({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  label: string
}) {
  return (
    <label className="relative block px-3 pt-3">
      <span className="sr-only">{label}</span>
      <Search size={14} className="pointer-events-none absolute left-5.5 top-[1.45rem] text-text-3" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-border-control bg-bg-2 pl-8 pr-2 text-[13px] text-text-1 placeholder:text-text-3"
      />
    </label>
  )
}

/* ------------------------------------------------------------- endpoints */

const ROLE_FILTERS: Array<{ value: Role | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'auth', label: 'Auth' },
  { value: 'protected', label: 'Protected' },
  { value: 'public', label: 'Public' },
]

function EndpointList({ repo, activeEndpoint, onSelectEndpoint }: Props) {
  const { data, isLoading, error } = useEndpoints(repo)
  const [q, setQ] = useState('')
  const [role, setRole] = useState<Role | 'all'>('all')
  const deferred = useDeferredValue(q)

  const groups = useMemo(() => {
    const needle = deferred.trim().toLowerCase()
    const rows = (data ?? []).filter(
      (e) =>
        (role === 'all' || roleOf(e) === role) &&
        (!needle || `${e.method} ${e.path} ${e.handler ?? ''} ${e.file}`.toLowerCase().includes(needle)),
    )
    const byFile = new Map<string, Endpoint[]>()
    for (const e of rows) byFile.set(e.file, [...(byFile.get(e.file) ?? []), e])
    return [...byFile.entries()]
  }, [data, deferred, role])

  return (
    <div className="flex h-full flex-col">
      <FilterBox value={q} onChange={setQ} placeholder="Filter endpoints" label="Filter endpoints" />
      <div role="group" aria-label="Filter by auth role" className="flex flex-wrap gap-1 px-3 py-2">
        {ROLE_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={role === f.value}
            onClick={() => setRole(f.value)}
            className={cx(
              'h-6 rounded-full border px-2.5 text-[12px] transition-colors duration-150',
              role === f.value
                ? 'border-accent-500 bg-bg-3 text-text-1'
                : 'border-border-control text-text-2 hover:text-text-1',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto pb-3">
        {isLoading && <div className="p-4"><Spinner label="Loading endpoints" /></div>}
        {error && <div className="p-3"><ErrorNote>{error.message}</ErrorNote></div>}
        {data && groups.length === 0 && (
          <EmptyState title={data.length ? 'No matches' : 'No endpoints detected'}>
            {data.length
              ? 'Try a different filter.'
              : 'RepoMind found no FastAPI, Flask or Express routes in this project.'}
          </EmptyState>
        )}
        {groups.map(([file, eps]) => (
          <section key={file} aria-label={file} className="mt-1">
            <h3 className="truncate px-3 py-1 font-mono text-[11.5px] text-text-3" title={file}>
              {file}
            </h3>
            <ul>
              {eps.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => onSelectEndpoint(e)}
                    aria-current={e.id === activeEndpoint ? 'true' : undefined}
                    className={cx(
                      'flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3',
                      e.id === activeEndpoint && 'bg-bg-3 shadow-[inset_2px_0_0_var(--accent-500)]',
                    )}
                  >
                    <MethodPill method={e.method} />
                    <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={e.path}>
                      {e.path}
                    </span>
                    <RoleBadge role={roleOf(e)} compact />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- files */

function FileTree({ repo, activeFile, onSelectFile }: Props) {
  const { data, isLoading, error } = useFiles(repo)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [q, setQ] = useState('')
  const deferred = useDeferredValue(q).trim().toLowerCase()
  const [focusIdx, setFocusIdx] = useState(0)
  const refs = useRef<Array<HTMLLIElement | null>>([])

  // Reveal the active file's folders whenever it changes (e.g. from the graph).
  useEffect(() => {
    if (activeFile) setExpanded((prev) => new Set([...prev, ...ancestors(activeFile)]))
  }, [activeFile])

  const tree = useMemo(() => buildFileTree(data ?? []), [data])
  const filtered = useMemo(
    () => (deferred ? (data ?? []).filter((f) => f.path.toLowerCase().includes(deferred)) : null),
    [data, deferred],
  )
  const rows = useMemo(() => {
    if (filtered) {
      return filtered.map((f) => ({
        node: { name: f.path, path: f.path, kind: 'file' as const, children: [], file: f, fileCount: 1, endpoints: f.endpoints },
        depth: 0,
      }))
    }
    return flattenVisible(tree, expanded)
  }, [filtered, tree, expanded])

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })

  const onKey = (e: KeyboardEvent, i: number) => {
    const row = rows[i]
    const move = (to: number) => {
      const j = Math.max(0, Math.min(rows.length - 1, to))
      setFocusIdx(j)
      refs.current[j]?.focus()
    }
    if (e.key === 'ArrowDown') (e.preventDefault(), move(i + 1))
    else if (e.key === 'ArrowUp') (e.preventDefault(), move(i - 1))
    else if (e.key === 'Home') (e.preventDefault(), move(0))
    else if (e.key === 'End') (e.preventDefault(), move(rows.length - 1))
    else if (e.key === 'ArrowRight' && row.node.kind === 'dir' && !expanded.has(row.node.path)) toggle(row.node.path)
    else if (e.key === 'ArrowLeft' && row.node.kind === 'dir' && expanded.has(row.node.path)) toggle(row.node.path)
    else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (row.node.kind === 'dir') toggle(row.node.path)
      else onSelectFile(row.node.path)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <FilterBox value={q} onChange={setQ} placeholder="Filter files" label="Filter files" />
      <div className="min-h-0 flex-1 overflow-auto py-2">
        {isLoading && <div className="p-4"><Spinner label="Loading files" /></div>}
        {error && <div className="p-3"><ErrorNote>{error.message}</ErrorNote></div>}
        {data && rows.length === 0 && <EmptyState title="No files match" />}
        <ul role="tree" aria-label="Files">
          {rows.map(({ node, depth }, i) => {
            const isDir = node.kind === 'dir'
            const open = isDir && expanded.has(node.path)
            const active = !isDir && node.path === activeFile
            return (
              <li
                key={node.path}
                ref={(el) => {
                  refs.current[i] = el
                }}
                role="treeitem"
                aria-level={depth + 1}
                aria-expanded={isDir ? open : undefined}
                aria-selected={active}
                tabIndex={i === Math.min(focusIdx, rows.length - 1) ? 0 : -1}
                onFocus={() => setFocusIdx(i)}
                onKeyDown={(e) => onKey(e, i)}
                onClick={() => (isDir ? toggle(node.path) : onSelectFile(node.path))}
                style={{ paddingLeft: 12 + depth * 14 }}
                className={cx(
                  'flex h-7 items-center gap-1.5 pr-3 text-[13px] transition-colors duration-150 hover:bg-bg-3',
                  active && 'bg-bg-3 shadow-[inset_2px_0_0_var(--accent-500)]',
                )}
              >
                {isDir ? (
                  <>
                    {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
                    <Folder size={14} className="text-text-2" aria-hidden />
                  </>
                ) : (
                  <FileCode2 size={14} className="ml-[18px] text-text-2" aria-hidden />
                )}
                <span className="min-w-0 flex-1 truncate" title={node.path}>
                  {node.name}
                </span>
                {node.endpoints > 0 && (
                  <span className="shrink-0 rounded-full bg-bg-3 px-1.5 text-[11px] text-text-2" title="Endpoints">
                    {node.endpoints}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- symbols */

function SymbolList({ repo, activeChunk, onSelectSymbol }: Props) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 180)
    return () => clearTimeout(t)
  }, [q])
  const { data, isFetching, error } = useSymbols(repo, debounced)

  return (
    <div className="flex h-full flex-col">
      <FilterBox value={q} onChange={setQ} placeholder="Search functions and classes" label="Search symbols" />
      <div className="min-h-0 flex-1 overflow-auto py-2" aria-busy={isFetching}>
        {error && <div className="p-3"><ErrorNote>{error.message}</ErrorNote></div>}
        {data && data.length === 0 && <EmptyState title="No symbols match" />}
        <ul>
          {(data ?? []).map((s) => {
            const Icon = s.kind === 'class' ? Box : FunctionSquare
            return (
              <li key={s.chunk_id}>
                <button
                  type="button"
                  onClick={() => onSelectSymbol(s)}
                  aria-current={s.chunk_id === activeChunk ? 'true' : undefined}
                  className={cx(
                    'flex w-full items-start gap-2 px-3 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3',
                    s.chunk_id === activeChunk && 'bg-bg-3 shadow-[inset_2px_0_0_var(--accent-500)]',
                  )}
                >
                  <Icon size={14} className="mt-1 shrink-0 text-text-2" aria-hidden />
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[12.5px]">{s.qualified_name}</span>
                    <span className="block truncate font-mono text-[11.5px] text-text-2">
                      {s.file}:{s.start_line}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
