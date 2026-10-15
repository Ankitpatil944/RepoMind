import { FolderPlus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { type IngestProgress, useIngest } from '../api/hooks'
import { ErrorNote, Spinner } from '../design/primitives'

interface Props {
  open: boolean
  onClose: () => void
  onIndexed: (repoId: number) => void
}

const PHASES: Record<string, string> = {
  queued: 'Waiting to start',
  starting: 'Starting',
  cloning: 'Cloning repository',
  parsing: 'Reading files',
  linking: 'Linking calls',
  embedding: 'Building the search index (first run may download models)',
}

function progressLabel(p: IngestProgress | null): string {
  if (!p) return 'Indexing'
  const base = PHASES[p.phase] ?? 'Indexing'
  return p.phase === 'parsing' && p.total > 0 ? `${base}: ${p.done} / ${p.total}` : base
}

/** Native <dialog>: focus trap, Esc to close and inert background come free. */
export function IndexDialog({ open, onClose, onIndexed }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [path, setPath] = useState('')
  const ingest = useIngest()

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const run = (value: string) => {
    ingest.mutate(value, {
      onSuccess: (r) => {
        onIndexed(r.repo_id)
        onClose()
      },
    })
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="index-title"
      className="m-auto w-[min(520px,92vw)] rounded-xl border border-border-control bg-bg-1 p-0 text-text-1 backdrop:bg-bg-0/70"
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="index-title" className="text-[16px] font-semibold">
              Index a project
            </h2>
            <p className="mt-1 text-text-2">
              Enter a folder name from <span className="font-mono text-text-1">repos/</span>, or paste a public
              GitHub / GitLab URL. Re-indexing only processes files that changed.
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

        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            const v = path.trim()
            if (v) run(v.startsWith('/') || v.startsWith('https://') ? v : `/repos/${v}`)
          }}
        >
          <label className="sr-only" htmlFor="index-path">
            Folder name or Git URL
          </label>
          <input
            id="index-path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="my-project or https://github.com/owner/repo"
            className="h-9 min-w-0 flex-1 rounded-md border border-border-control bg-bg-2 px-3 font-mono text-[13px] placeholder:text-text-3"
          />
          <button
            type="submit"
            disabled={!path.trim() || ingest.isPending}
            className="h-9 rounded-md bg-accent-600 px-3.5 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Index
          </button>
        </form>

        <div className="mt-4 rounded-lg border border-border-subtle bg-bg-2 p-3">
          <p className="text-[13px] text-text-2">No project handy? Try the bundled sample.</p>
          <button
            type="button"
            disabled={ingest.isPending}
            onClick={() => run('/samples/shop_api')}
            className="mt-2 inline-flex h-8 items-center gap-2 rounded-md border border-border-control px-3 text-[13px] transition-colors duration-150 hover:bg-bg-3 disabled:opacity-50"
          >
            <FolderPlus size={14} aria-hidden />
            Index sample project (shop_api)
          </button>
        </div>

        <div className="mt-3" aria-live="polite">
          {ingest.isPending && <Spinner label={progressLabel(ingest.progress)} />}
          {ingest.error && <ErrorNote title="Could not index">{ingest.error.message}</ErrorNote>}
        </div>
      </div>
    </dialog>
  )
}
