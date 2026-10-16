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
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border-subtle bg-bg-1 px-5">
      <div className="flex items-center gap-2.5">
        <Mark />
        <span className="wordmark serif text-[24px] leading-none">RepoMind</span>
      </div>

      {repos.length > 0 && (
        <label className="flex items-center gap-2">
          <span className="sr-only">Repository</span>
          <select
            value={repo?.id ?? ''}
            onChange={(e) => onRepo(Number(e.target.value))}
            className="h-[34px] max-w-[14rem] rounded-[7px] border border-border-control bg-raised px-2.5 font-mono text-[12.5px] text-text-1"
          >
            {repos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · #{r.id}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="mx-auto flex min-w-0 max-w-xl flex-1">{ask}</div>

      <div className="flex items-center gap-2">
        <button type="button" onClick={onPalette} className={BTN} aria-label="Open command palette" title="Command palette">
          <Search size={14} aria-hidden />
          <span className="hidden xl:inline">Search</span>
          <Kbd>{isMac ? '⌘' : 'Ctrl'} K</Kbd>
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
            className={`${BTN} hidden md:inline-flex`}
          >
            <Download size={14} aria-hidden />
            Export
          </button>
        )}
        <button type="button" onClick={onIndex} className={`${BTN} prim-btn hidden md:inline-flex`}>
          <FolderPlus size={14} aria-hidden />
          Index project
        </button>
      </div>
    </header>
  )
}
