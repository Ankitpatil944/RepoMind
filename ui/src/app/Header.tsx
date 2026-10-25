import { Download, FolderPlus, Search, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import type { Repo } from '../api/types'
import { Kbd } from '../design/primitives'

interface Props {
  repos: Repo[]
  repo: Repo | null
  /** null while unknown */
  ai: 'ready' | 'unreachable' | 'error' | null
  /** the ask box, rendered between the repo picker and the actions */
  ask: ReactNode
  onRepo: (id: number) => void
  onPalette: () => void
  onIndex: () => void
  onExport: () => void
}

function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--bg-2)" stroke="var(--border-control)" />
      <path d="M12 15.5l8-5M12 16.5l8 5" stroke="var(--teal)" strokeWidth="1.5" />
      <circle cx="9" cy="16" r="3" fill="var(--accent-400)">
        <animate attributeName="r" values="3;4;3" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <circle cx="23" cy="9.5" r="3" fill="var(--text-2)" />
      <circle cx="23" cy="22.5" r="3" fill="var(--text-2)" />
    </svg>
  )
}

const BTN =
  'inline-flex h-[34px] items-center gap-2 whitespace-nowrap rounded-[7px] border border-border-control bg-raised px-3 text-[13px] font-medium text-text-1 transition-colors duration-150 hover:border-border-hover hover:bg-bg-3'

export function Header({ repos, repo, ai, ask, onRepo, onPalette, onIndex, onExport }: Props) {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border-subtle bg-bg-1 px-3 py-2 sm:h-14 sm:flex-nowrap sm:gap-3 sm:px-5 sm:py-0">
      <div className="flex items-center gap-2.5">
        <Mark />
        <span className="wordmark serif hidden text-[24px] leading-none sm:inline">RepoMind</span>
      </div>

      {repos.length > 0 && (
        <label className="flex min-w-0 items-center gap-2">
          <span className="sr-only">Repository</span>
          <select
            value={repo?.id ?? ''}
            onChange={(e) => onRepo(Number(e.target.value))}
            className="h-[34px] min-w-0 max-w-[11rem] rounded-[7px] sm:max-w-[14rem] border border-border-control bg-raised px-2.5 font-mono text-[12.5px] text-text-1"
          >
            {repos.map((r) => (
              <option key={r.id} value={r.id}>
                {/* The id only disambiguates two indexed repos with the same name. */}
                {repos.some((o) => o.id !== r.id && o.name === r.name) ? `${r.name} · #${r.id}` : r.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {/* Phones: the ask box gets its own full-width row under the logo, picker and actions. */}
      <div className="order-last flex min-w-0 basis-full sm:order-none sm:mx-auto sm:min-w-[9rem] sm:max-w-xl sm:flex-1 sm:basis-auto">
        {ask}
      </div>

      <div className="ml-auto flex items-center gap-2 sm:ml-0">
        <button type="button" onClick={onPalette} className={BTN} aria-label="Open command palette" title="Command palette">
          <Search size={14} aria-hidden />
          <span className="hidden xl:inline">Search</span>
          <span className="hidden lg:inline-flex">
            <Kbd>{isMac ? '⌘' : 'Ctrl'} K</Kbd>
          </span>
        </button>
        {ai !== null && (
          <span
            className="hidden h-[34px] items-center gap-[7px] rounded-full border border-border-control bg-bg-2 px-3 text-[12px] font-semibold tracking-[0.02em] md:inline-flex"
            title={
              ai === 'ready'
                ? 'A language model is reachable: written answers and explanations are available.'
                : 'No language model is reachable. Everything structural still works: overview, architecture, call flow, summaries and search.'
            }
          >
            {ai === 'ready' ? (
              <span className="live-dot" aria-hidden />
            ) : (
              <Sparkles size={12} className="text-text-3" aria-hidden />
            )}
            <span className={ai === 'ready' ? 'text-moss' : 'text-text-2'}>{ai === 'ready' ? 'AI on' : 'AI off'}</span>
          </span>
        )}
        {repo && (
          <button
            type="button"
            onClick={onExport}
            title="Export a token-budgeted summary to use as LLM context"
            className={`${BTN} max-lg:hidden`}
          >
            <Download size={14} aria-hidden />
            Export
          </button>
        )}
        <button type="button" onClick={onIndex} className={`${BTN} prim-btn`} aria-label="Index project">
          <FolderPlus size={14} aria-hidden />
          <span className="hidden lg:inline">Index project</span>
        </button>
      </div>
    </header>
  )
}
