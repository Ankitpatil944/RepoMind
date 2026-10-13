import { AlertTriangle, FileCode2 } from 'lucide-react'

import { useFileContent } from '../../api/hooks'
import { EmptyState, ErrorNote, Spinner } from '../../design/primitives'
import { CodePane } from './CodePane'

interface Props {
  repo: number
  file: string | null
  start: number | null
  end: number | null
  externalLabel?: string | null
  onJump: (start: number, end: number) => void
}

export function SourcePane({ repo, file, start, end, externalLabel, onJump }: Props) {
  const { data, isLoading, error } = useFileContent(repo, file)

  if (externalLabel) {
    return (
      <EmptyState icon={<FileCode2 size={28} aria-hidden />} title={externalLabel}>
        This call is defined outside the repository (a library) or resolved dynamically, so there is
        no source to show.
      </EmptyState>
    )
  }
  if (!file) {
    return (
      <EmptyState icon={<FileCode2 size={28} aria-hidden />} title="No file selected">
        Pick an endpoint, a symbol or a file to see its source here.
      </EmptyState>
    )
  }
  if (isLoading) {
    return (
      <div className="p-4">
        <Spinner label="Loading source" />
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="p-3">
        <ErrorNote title="Source unavailable">
          {error?.message ?? 'Unknown error'}. The index still works; only the preview needs the
          project folder to be mounted.
        </ErrorNote>
      </div>
    )
  }

  const inFile = data.symbols
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-3 py-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={data.path}>
          {data.path}
        </span>
        <label className="flex items-center gap-1.5 text-[12px] text-text-2">
          <span>Jump to</span>
          <select
            aria-label="Jump to symbol"
            className="h-7 max-w-[11rem] rounded-md border border-border-control bg-bg-2 px-1.5 text-[12px] text-text-1"
            value=""
            onChange={(e) => {
              const s = inFile.find((x) => String(x.chunk_id) === e.target.value)
              if (s) onJump(s.start_line, s.end_line)
            }}
          >
            <option value="">symbol…</option>
            {inFile.map((s) => (
              <option key={s.chunk_id} value={s.chunk_id}>
                {s.qualified_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {data.changed_since_indexed && (
        <div
          role="status"
          className="flex shrink-0 items-start gap-2 border-b border-border-subtle bg-bg-2 px-3 py-2 text-[12.5px] text-text-1"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" aria-hidden />
          <span>
            This file changed on disk since it was indexed, so line numbers may be off. Re-run
            ingest to refresh.
          </span>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <CodePane
          content={data.content}
          language={data.language}
          start={start}
          end={end}
          label={`Source of ${data.path}`}
        />
      </div>
    </div>
  )
}
