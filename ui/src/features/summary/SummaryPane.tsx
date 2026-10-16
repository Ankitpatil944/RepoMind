import { ArrowDownLeft, FileCode2, Folder, Lightbulb } from 'lucide-react'
import type { ReactNode } from 'react'

import { useFacts, useFileInfo } from '../../api/hooks'
import type { ChunkFacts, ChunkRef, FileInfo, ModuleNode } from '../../api/types'
import { EmptyState, ErrorNote, MethodPill, RoleBadge, roleOf, Spinner } from '../../design/primitives'
import { cx } from '../../lib/cx'

interface Props {
  repo: number
  chunkId: number | null
  file: string | null
  module: ModuleNode | null
  onOpenChunk: (ref: ChunkRef) => void
  onOpenFile: (path: string) => void
  onViewSource: () => void
}

/** Plain-language description of whatever is selected, built from static
 *  analysis only. This is the "explain" experience that needs no LLM. */
export function SummaryPane({ repo, chunkId, file, module, onOpenChunk, onOpenFile, onViewSource }: Props) {
  if (chunkId !== null) {
    return <ChunkSummary repo={repo} chunkId={chunkId} onOpenChunk={onOpenChunk} onViewSource={onViewSource} />
  }
  if (module && module.kind === 'dir') return <DirSummary m={module} />
  const path = module?.kind === 'file' ? module.path : file
  if (path) return <FileSummary repo={repo} path={path} onOpenChunk={onOpenChunk} onOpenFile={onOpenFile} />
  return (
    <EmptyState icon={<Lightbulb size={28} aria-hidden />} title="Select something to understand it">
      Pick a function, a file or a folder. You get its signature, documentation, size, complexity,
      callers and callees, all derived from the code itself. No AI needed.
    </EmptyState>
  )
}

/* ---------------------------------------------------------------- shared */

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-1.5 text-[11.5px] font-medium uppercase tracking-wide text-text-3">
        {title}
        {count !== undefined && <span className="ml-1.5 normal-case text-text-2">({count})</span>}
      </h3>
      {children}
    </section>
  )
}

/** Render `backticked` spans as inline code, leaving everything else as text. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/g).map((part, i) =>
        part.startsWith('`') && part.endsWith('`') ? (
          <code key={i} className="rounded bg-bg-3 px-1 py-px font-mono text-[12.5px]">
            {part.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-bg-2 px-2.5 py-1.5" title={hint}>
      <div className="text-[11px] text-text-2">{label}</div>
      <div className="font-mono text-[14px] font-medium tabular-nums">{value}</div>
    </div>
  )
}

function RefList({ items, onOpen }: { items: ChunkRef[]; onOpen: (r: ChunkRef) => void }) {
  return (
    <ul className="space-y-1">
      {items.map((r) => (
        <li key={`${r.chunk_id}`}>
          <button
            type="button"
            onClick={() => onOpen(r)}
            className="flex w-full items-center gap-2 rounded-md border border-border-subtle bg-bg-2 px-2.5 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
          >
            <span className="truncate font-mono text-[12.5px]">{r.name}</span>
            <span className="ml-auto truncate font-mono text-[11.5px] text-text-2">
              {r.file}:{r.line}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

const CX_TONE = { low: 'text-ok', moderate: 'text-warn', high: 'text-danger' } as const

/* ----------------------------------------------------------------- chunk */

function ChunkSummary({
  repo,
  chunkId,
  onOpenChunk,
  onViewSource,
}: {
  repo: number
  chunkId: number
  onOpenChunk: (r: ChunkRef) => void
  onViewSource: () => void
}) {
  const { data: f, isLoading, error } = useFacts(repo, chunkId)
  if (isLoading) return <PaneSkeleton />
  if (error || !f) {
    return (
      <div className="p-4">
        <ErrorNote title="No facts for this item">{error?.message ?? 'Unknown error'}</ErrorNote>
      </div>
    )
  }
  return (
    <div className="h-full overflow-auto p-4">
      <div className="rise-in">
        <div className="flex flex-wrap items-center gap-2">
          <span className="metric-chip uppercase">{f.kind}</span>
          <h2 className="min-w-0 break-all font-mono text-[15px] font-semibold">{f.qualified_name}</h2>
        </div>
        <p className="mt-1 font-mono text-[12px] text-text-2">
          {f.file}:{f.start_line}-{f.end_line}
        </p>
        {f.signature && (
          <pre className="mt-3 overflow-x-auto rounded-lg border border-border-subtle bg-bg-0 p-2.5 font-mono text-[12.5px]">
            <span style={{ color: 'var(--syn-function)' }}>{f.signature}</span>
          </pre>
        )}
        {f.doc && (
          <blockquote className="serif mt-3 border-l-2 border-sage-border pl-3 text-[21px] leading-snug text-cream">
            {f.doc}
          </blockquote>
        )}
      </div>

      <div className="rise-in mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" style={{ animationDelay: '60ms' }}>
        <Metric label="Lines" value={f.loc} />
        <Metric
          label="Complexity"
          value={
            <span className={cx(f.complexity_label && CX_TONE[f.complexity_label])}>
              {f.complexity}
              {f.complexity_label && <span className="ml-1 text-[11px] font-normal">{f.complexity_label}</span>}
            </span>
          }
          hint="1 + number of branch points (if/for/while/except/and/or)"
        />
        <Metric label="Callers" value={f.callers.length} />
        <Metric label="Calls" value={f.callees_internal.length + f.callees_external.length} />
      </div>

      <FactSummary f={f} />

      {f.endpoints.length > 0 && (
        <Section title="HTTP routes handled" count={f.endpoints.length}>
          <ul className="space-y-1.5">
            {f.endpoints.map((e) => (
              <li key={e.id} className="rounded-lg border border-border-subtle bg-bg-2 p-2.5">
                <div className="flex items-center gap-2">
                  <MethodPill method={e.method} />
                  <span className="font-mono text-[12.5px]">{e.path}</span>
                  <RoleBadge role={roleOf(e)} className="ml-auto" />
                </div>
                {e.evidence.length > 0 && (
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12.5px] text-text-2">
                    {e.evidence.map((ev) => (
                      <li key={ev}>{ev}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {f.callers.length > 0 && (
        <Section title="Called by" count={f.callers.length}>
          <RefList items={f.callers} onOpen={onOpenChunk} />
        </Section>
      )}
      {f.callees_internal.length > 0 && (
        <Section title="Calls in this repo" count={f.callees_internal.length}>
          <RefList items={f.callees_internal} onOpen={onOpenChunk} />
        </Section>
      )}
      {f.callees_external.length > 0 && (
        <Section title="Calls outside this repo" count={f.callees_external.length}>
          <ul className="flex flex-wrap gap-1.5">
            {f.callees_external.map((c) => (
              <li key={c} className="rounded-md border border-dashed border-border-control px-2 py-0.5 font-mono text-[12px]">
                {c}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <button
        type="button"
        onClick={onViewSource}
        className="mt-6 inline-flex h-8 items-center gap-2 rounded-md border border-border-control px-3 text-[13px] transition-colors duration-150 hover:bg-bg-3"
      >
        <FileCode2 size={14} aria-hidden />
        View source
      </button>
    </div>
  )
}

function FactSummary({ f }: { f: ChunkFacts }) {
  return (
    <section aria-label="What the code tells us" className="rise-in mt-5" style={{ animationDelay: '120ms' }}>
      <h3 className="mb-1.5 flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-wide text-text-3">
        <Lightbulb size={12} aria-hidden /> What the code tells us
      </h3>
      <ul className="space-y-1.5 text-[14px] leading-relaxed">
        {f.summary.map((line, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent-400" aria-hidden />
            <span>
              <Rich text={line} />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[12px] text-text-3">Derived from static analysis, not generated by an AI model.</p>
    </section>
  )
}

/* ------------------------------------------------------------------ file */

function FileSummary({
  repo,
  path,
  onOpenChunk,
  onOpenFile,
}: {
  repo: number
  path: string
  onOpenChunk: (r: ChunkRef) => void
  onOpenFile: (path: string) => void
}) {
  const { data: info, isLoading, error } = useFileInfo(repo, path)
  if (isLoading) return <PaneSkeleton />
  if (error || !info) {
    return (
      <div className="p-4">
        <ErrorNote title="No information for this file">{error?.message ?? 'Unknown error'}</ErrorNote>
      </div>
    )
  }
  return <FileBody info={info} onOpenChunk={onOpenChunk} onOpenFile={onOpenFile} />
}

function FileBody({
  info,
  onOpenChunk,
  onOpenFile,
}: {
  info: FileInfo
  onOpenChunk: (r: ChunkRef) => void
  onOpenFile: (path: string) => void
}) {
  const maxLoc = Math.max(1, ...info.symbols.map((s) => s.loc))
  return (
    <div className="h-full overflow-auto p-4">
      <div className="rise-in">
        <div className="flex items-center gap-2">
          <FileCode2 size={16} className="text-text-2" aria-hidden />
          <h2 className="break-all font-mono text-[15px] font-semibold">{info.path}</h2>
        </div>
        <p className="mt-1 text-[12.5px] text-text-2">
          {info.language} · {info.loc.toLocaleString()} lines · {info.symbols.length} symbols
        </p>
        {info.doc && (
          <blockquote className="serif mt-3 border-l-2 border-sage-border pl-3 text-[21px] leading-snug text-cream">{info.doc}</blockquote>
        )}
      </div>

      {info.endpoints.length > 0 && (
        <Section title="HTTP routes defined" count={info.endpoints.length}>
          <ul className="space-y-1">
            {info.endpoints.map((e) => (
              <li key={`${e.method}${e.path}${e.line}`} className="flex items-center gap-2">
                <MethodPill method={e.method} />
                <span className="font-mono text-[12.5px]">{e.path}</span>
                <span className="ml-auto font-mono text-[11.5px] text-text-2">line {e.line}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {info.symbols.length > 0 && (
        <Section title="Contents" count={info.symbols.length}>
          <ul className="space-y-1">
            {info.symbols.map((s) => (
              <li key={s.chunk_id}>
                <button
                  type="button"
                  onClick={() =>
                    onOpenChunk({ chunk_id: s.chunk_id, name: s.name, file: info.path, line: s.start_line })
                  }
                  className="group relative w-full overflow-hidden rounded-md border border-border-subtle bg-bg-2 px-2.5 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
                >
                  <span
                    className="bar-grow absolute inset-y-0 left-0 bg-bg-3 group-hover:bg-bg-2"
                    style={{ width: `${(s.loc / maxLoc) * 100}%` }}
                    aria-hidden
                  />
                  <span className="relative block">
                    <span className="flex items-center gap-2">
                      <span className="truncate font-mono text-[12.5px] font-medium">{s.name}</span>
                      <span className="ml-auto flex shrink-0 gap-1">
                        {s.fan_in > 0 && (
                          <span className="metric-chip" title="Callers">
                            <ArrowDownLeft size={10} aria-hidden />
                            {s.fan_in}
                          </span>
                        )}
                        <span className="metric-chip">{s.loc} loc</span>
                        {s.complexity > 1 && <span className="metric-chip">cx {s.complexity}</span>}
                      </span>
                    </span>
                    {s.signature && (
                      <span className="mt-0.5 block truncate font-mono text-[11.5px] text-text-2">
                        {s.signature}
                      </span>
                    )}
                    {s.doc && <span className="mt-0.5 block truncate text-[12px] text-text-2">{s.doc}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Imports from this repo" count={info.imports.internal.length}>
        {info.imports.internal.length === 0 ? (
          <p className="text-text-2">Imports nothing else from this project.</p>
        ) : (
          <PathList paths={info.imports.internal} onOpen={onOpenFile} />
        )}
      </Section>
      {info.imported_by.length > 0 && (
        <Section title="Imported by" count={info.imported_by.length}>
          <PathList paths={info.imported_by} onOpen={onOpenFile} />
        </Section>
      )}
      {info.imports.third_party.length > 0 && (
        <Section title="Third-party libraries" count={info.imports.third_party.length}>
          <ul className="flex flex-wrap gap-1.5">
            {info.imports.third_party.map((n) => (
              <li key={n} className="rounded-md border border-border-control bg-bg-2 px-2 py-0.5 font-mono text-[12px]">
                {n}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {info.imports.stdlib.length > 0 && (
        <Section title="Standard library" count={info.imports.stdlib.length}>
          <ul className="flex flex-wrap gap-1.5">
            {info.imports.stdlib.map((n) => (
              <li key={n} className="rounded-md bg-bg-2 px-2 py-0.5 font-mono text-[12px] text-text-2">
                {n}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}

function PathList({ paths, onOpen }: { paths: string[]; onOpen: (p: string) => void }) {
  return (
    <ul className="space-y-1">
      {paths.map((p) => (
        <li key={p}>
          <button
            type="button"
            onClick={() => onOpen(p)}
            className="w-full truncate rounded-md border border-border-subtle bg-bg-2 px-2.5 py-1.5 text-left font-mono text-[12.5px] transition-colors duration-150 hover:bg-bg-3"
          >
            {p}
          </button>
        </li>
      ))}
    </ul>
  )
}

/* ------------------------------------------------------------- directory */

function DirSummary({ m }: { m: ModuleNode }) {
  return (
    <div className="h-full overflow-auto p-4">
      <div className="rise-in flex items-center gap-2">
        <Folder size={16} className="text-text-2" aria-hidden />
        <h2 className="break-all font-mono text-[15px] font-semibold">{m.path}/</h2>
      </div>
      <div className="rise-in mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" style={{ animationDelay: '60ms' }}>
        <Metric label="Files" value={m.files} />
        <Metric label="Lines" value={m.loc.toLocaleString()} />
        <Metric label="Symbols" value={m.symbols} />
        <Metric label="Routes" value={m.endpoints} />
      </div>
      <p className="mt-4 text-[14px] leading-relaxed">
        This folder holds {m.files} file{m.files === 1 ? '' : 's'} ({m.languages.join(', ')}) with{' '}
        {m.symbols} functions and classes
        {m.endpoints > 0 ? `, defining ${m.endpoints} HTTP route${m.endpoints === 1 ? '' : 's'}` : ''}. It is
        connected to {m.degree} import link{m.degree === 1 ? '' : 's'} with other modules.
      </p>
      <p className="mt-2 text-[12.5px] text-text-2">Double-click the folder in the map to look inside it.</p>
    </div>
  )
}

function PaneSkeleton() {
  return (
    <div className="space-y-3 p-4" aria-busy="true">
      <div className="skeleton h-6 w-2/3" />
      <div className="skeleton h-14" />
      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="skeleton h-12" />
        ))}
      </div>
      <div className="skeleton h-32" />
      <Spinner label="Reading the code" />
    </div>
  )
}
