import { Check, Copy, Download, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useExport, useExportEstimate, useFiles } from '../../api/hooks'
import type { ExportDetail, ExportFormat } from '../../api/types'
import { ErrorNote, Spinner } from '../../design/primitives'
import { cx } from '../../lib/cx'

interface Props {
  open: boolean
  onClose: () => void
  repoId: number | null
  repoName: string
}

const DETAILS: Array<{ id: ExportDetail; title: string; blurb: string }> = [
  { id: 'overview', title: 'Overview', blurb: 'Size, stack, architecture, auth surface, hotspots.' },
  { id: 'map', title: 'Repo map', blurb: 'Overview + every route and the signatures and docs of the important files.' },
  { id: 'source', title: 'Map + key source', blurb: 'The map, plus the code of the handlers, hubs and guards.' },
]

const BUDGETS = [4_000, 8_000, 16_000, 32_000, 64_000, 128_000]
const fmt = (n: number) => n.toLocaleString('en-US')

/** Folders worth exporting on their own: up to two segments deep, biggest first. */
export function scopeOptions(files: Array<{ path: string; loc: number }>): Array<{ path: string; loc: number }> {
  const totals = new Map<string, number>()
  for (const f of files) {
    const parts = f.path.split('/')
    if (parts.length < 2) continue
    const key = parts.slice(0, Math.min(2, parts.length - 1)).join('/')
    totals.set(key, (totals.get(key) ?? 0) + f.loc)
    if (parts.length > 2) {
      const top = parts[0]
      totals.set(top, (totals.get(top) ?? 0) + f.loc)
    }
  }
  return [...totals.entries()]
    .map(([path, loc]) => ({ path, loc }))
    .sort((a, b) => b.loc - a.loc || a.path.localeCompare(b.path))
    .slice(0, 40)
}

function extension(f: ExportFormat) {
  return f === 'markdown' ? 'md' : 'json'
}

/** Embeddings are a search index, not something an LLM can read. What it can
 *  use is compact text, so this exports the extracted facts within a budget. */
export function ExportDialog({ open, onClose, repoId, repoName }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [detail, setDetail] = useState<ExportDetail>('map')
  const [budget, setBudget] = useState(16_000)
  const [format, setFormat] = useState<ExportFormat>('markdown')
  const [focus, setFocus] = useState('')
  const [copied, setCopied] = useState<'ok' | 'failed' | null>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const files = useFiles(open ? repoId : null)
  const scopes = useMemo(() => scopeOptions(files.data ?? []), [files.data])
  const estimate = useExportEstimate(open ? repoId : null, focus)
  const result = useExport(open ? repoId : null, { detail, maxTokens: budget, format, focus })

  const raw = estimate.data?.full_source_tokens ?? 0
  const pct = (tokens: number) => (raw ? Math.max(0.2, (tokens / raw) * 100) : 0)
  const data = result.data

  const preview = useMemo(() => (data ? data.content.split('\n').slice(0, 36).join('\n') : ''), [data])

  async function copy() {
    if (!data) return
    try {
      await navigator.clipboard.writeText(data.content)
      setCopied('ok')
    } catch {
      setCopied('failed')
    }
    setTimeout(() => setCopied(null), 2200)
  }

  function download() {
    if (!data) return
    const type = format === 'markdown' ? 'text/markdown' : 'application/json'
    const url = URL.createObjectURL(new Blob([data.content], { type: `${type};charset=utf-8` }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${repoName}${focus ? `-${focus.replace(/\//g, '_')}` : ''}-${detail}.${extension(format)}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="export-title"
      className="m-auto max-h-[90vh] w-[min(760px,94vw)] overflow-auto rounded-xl border border-border-control bg-bg-1 p-0 text-text-1 backdrop:bg-bg-0/70"
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="export-title" className="text-[16px] font-semibold">
              Export for an LLM
            </h2>
            <p className="mt-1 text-text-2">
              Embeddings are a search index, not context an LLM can read. This exports the same facts as
              compact, token-budgeted text, so a model sees the shape of the codebase without paying for
              every line of it.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-text-2 hover:bg-bg-3 hover:text-text-1"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <section aria-label="Cost comparison" className="mt-4 rounded-lg border border-border-subtle bg-bg-2 p-3">
          <h3 className="mb-2 text-[11.5px] font-medium uppercase tracking-wide text-text-3">
            Estimated tokens (about 4 characters each)
          </h3>
          {estimate.isLoading && <Spinner label="Measuring" />}
          {estimate.data && (
            <ul className="space-y-1.5 text-[13px]">
              {[
                { key: 'raw', label: 'Paste all the source', tokens: raw, muted: true },
                { key: 'o', label: 'Overview', tokens: estimate.data.overview_tokens },
                { key: 'm', label: 'Repo map (uncapped)', tokens: estimate.data.map_tokens },
                { key: 's', label: 'Map + key source (uncapped)', tokens: estimate.data.source_tokens },
              ].map((r) => (
                <li key={r.key} className="grid grid-cols-[11rem_1fr_6.5rem] items-center gap-3">
                  <span className={cx(r.muted && 'text-text-2')}>{r.label}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-bg-3" aria-hidden>
                    <span
                      className={cx('bar-grow block h-full rounded-full', r.muted ? 'bg-text-3' : 'bg-accent-500')}
                      style={{ width: `${Math.min(100, pct(r.tokens))}%` }}
                    />
                  </span>
                  <span className="text-right font-mono text-[12px]">
                    ~{fmt(r.tokens)}
                    {!r.muted && raw > 0 && (
                      <span className="ml-1 text-text-2">{Math.max(1, Math.round((r.tokens / raw) * 100))}%</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_auto]">
          <fieldset>
            <legend className="mb-1.5 text-[12px] font-medium text-text-2">What to include</legend>
            <div className="space-y-1.5">
              {DETAILS.map((d) => (
                <label
                  key={d.id}
                  className={cx(
                    'flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors duration-150',
                    detail === d.id ? 'border-accent-500 bg-bg-2' : 'border-border-subtle hover:bg-bg-2',
                  )}
                >
                  <input
                    type="radio"
                    name="detail"
                    value={d.id}
                    checked={detail === d.id}
                    onChange={() => setDetail(d.id)}
                    className="mt-1 accent-[var(--accent-500)]"
                  />
                  <span>
                    <span className="block text-[13.5px] font-medium">
                      {d.title}
                      {d.id === 'map' && <span className="ml-2 text-[11px] font-normal text-accent-400">recommended</span>}
                    </span>
                    <span className="block text-[12.5px] text-text-2">{d.blurb}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="space-y-3 sm:w-64">
            <label className="block text-[12px] font-medium text-text-2">
              Scope
              <select
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-border-control bg-bg-2 px-2 text-[13px] text-text-1"
              >
                <option value="">Whole repository</option>
                {scopes.map((s) => (
                  <option key={s.path} value={s.path}>
                    {s.path} ({fmt(s.loc)} lines)
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-[12px] font-medium text-text-2">
              Token budget
              <select
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                className="mt-1 h-9 w-full rounded-md border border-border-control bg-bg-2 px-2 text-[13px] text-text-1"
              >
                {BUDGETS.map((b) => (
                  <option key={b} value={b}>
                    {fmt(b)} tokens
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-[12px] font-medium text-text-2">
              Format
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as ExportFormat)}
                className="mt-1 h-9 w-full rounded-md border border-border-control bg-bg-2 px-2 text-[13px] text-text-1"
              >
                <option value="markdown">Markdown</option>
                <option value="json">JSON (compact)</option>
              </select>
            </label>
          </div>
        </div>

        <div className="mt-4" aria-live="polite">
          {result.isFetching && !data && <Spinner label="Building the export" />}
          {result.error && <ErrorNote title="Could not build the export">{result.error.message}</ErrorNote>}
          {data && (
            <>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                <span>
                  <span className="font-mono font-medium">~{fmt(data.estimated_tokens)}</span> tokens
                  <span className="text-text-2"> of a {fmt(data.budget)} budget</span>
                </span>
                {data.truncated && (
                  <span className="text-warn">
                    trimmed: {Object.entries(data.omitted)
                      .filter(([, v]) => v > 0)
                      .map(([k, v]) => `${fmt(v)} ${k}`)
                      .join(', ')}{' '}
                    left out
                  </span>
                )}
                {data.test_files_left_out > 0 && (
                  <span className="text-text-2">{data.test_files_left_out} test files excluded</span>
                )}
                {data.redactions.total > 0 && (
                  <span className="text-ok" title={Object.entries(data.redactions.by_kind).map(([k, v]) => `${v} ${k}`).join(', ')}>
                    {data.redactions.total} possible secret{data.redactions.total === 1 ? '' : 's'} redacted
                  </span>
                )}
              </div>
              {data.freshness.available &&
                data.freshness.changed_count + data.freshness.missing_count + data.freshness.new_count > 0 && (
                <p role="alert" className="mt-2 rounded-md border border-border-control bg-bg-2 px-2.5 py-1.5 text-[12.5px] text-warn">
                  Since this repo was indexed: {data.freshness.changed_count} file
                  {data.freshness.changed_count === 1 ? '' : 's'} changed on disk
                  {data.freshness.missing_count ? `, ${data.freshness.missing_count} are gone` : ''}
                  {data.freshness.new_count ? `, ${data.freshness.new_count} new` : ''}. Re-run{' '}
                  <strong>Index project</strong> for a fresh export.
                </p>
              )}
              {!data.freshness.available && (
                <p className="mt-2 text-[12.5px] text-text-2">
                  The source folder is not mounted, so changes since indexing cannot be checked.
                </p>
              )}
              <pre
                tabIndex={0}
                aria-label="Export preview"
                className="mt-2 max-h-56 overflow-auto rounded-lg border border-border-subtle bg-bg-0 p-3 font-mono text-[11.5px] leading-relaxed text-text-2"
              >
                {preview}
                {data.content.split('\n').length > 36 ? '\n...' : ''}
              </pre>
            </>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copy}
            disabled={!data}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-accent-600 px-3.5 text-[13px] font-semibold text-on-accent transition-colors duration-150 hover:bg-[#cdd8b3] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {copied === 'ok' ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
            {copied === 'ok' ? 'Copied' : 'Copy to clipboard'}
          </button>
          <button
            type="button"
            onClick={download}
            disabled={!data}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-border-control px-3.5 text-[13px] transition-colors duration-150 hover:bg-bg-3 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download size={15} aria-hidden />
            Download .{extension(format)}
          </button>
          {copied === 'failed' && (
            <span role="status" className="text-[12.5px] text-warn">
              Clipboard blocked by the browser. Use Download instead.
            </span>
          )}
          <span className="ml-auto text-[12px] text-text-3">
            Same thing from a terminal: <code className="font-mono">app.cli export {repoName}</code>
          </span>
        </div>
      </div>
    </dialog>
  )
}
