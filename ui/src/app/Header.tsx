import { FolderPlus, Search, Sparkles } from 'lucide-react'

import type { Repo } from '../api/types'
import { Kbd } from '../design/primitives'

interface Props {
  repos: Repo[]
  repo: Repo | null
  /** null while unknown */
  ai: 'ready' | 'unreachable' | 'error' | null
  onRepo: (id: number) => void
  onPalette: () => void
  onIndex: () => void
}

function Mark() {
  return (
    <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--bg-2)" stroke="var(--border-control)" />
      <path d="M12 15.5l8-5M12 16.5l8 5" stroke="var(--text-2)" strokeWidth="1.5" />
      <circle cx="9" cy="16" r="3" fill="var(--accent-500)">
        <animate attributeName="r" values="3;4;3" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <circle cx="23" cy="9.5" r="3" fill="var(--text-2)" />
      <circle cx="23" cy="22.5" r="3" fill="var(--text-2)" />
    </svg>
  )
}

export function Header({ repos, repo, ai, onRepo, onPalette, onIndex }: Props) {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border-subtle bg-bg-1 px-3">
      <div className="flex items-center gap-2">
        <Mark />
        <span className="wordmark text-[15px] font-semibold tracking-tight">RepoMind</span>
      </div>

      {repos.length > 0 && (
        <label className="flex items-center gap-2">
          <span className="sr-only">Repository</span>
          <select
            value={repo?.id ?? ''}
            onChange={(e) => onRepo(Number(e.target.value))}
            className="h-8 max-w-[14rem] rounded-md border border-border-control bg-bg-2 px-2 text-[13px] text-text-1"
          >
            {repos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · #{r.id}
              </option>
            ))}
          </select>
        </label>
      )}

      <button
        type="button"
        onClick={onPalette}
        className="mx-auto flex h-8 w-full max-w-md items-center gap-2 rounded-md border border-border-control bg-bg-2 px-2.5 text-left text-[13px] text-text-2 transition-colors duration-150 hover:bg-bg-3"
      >
        <Search size={14} aria-hidden />
        <span className="flex-1 truncate">Search endpoints, functions, files — or ask</span>
        <Kbd>{isMac ? '⌘' : 'Ctrl'} K</Kbd>
      </button>

      <div className="hidden items-center gap-3 text-[12.5px] text-text-2 md:flex">
        {repo && (
          <span title={repo.path}>
            {repo.files} files · {repo.chunks} chunks
          </span>
        )}
        {ai !== null && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-border-control px-2 py-0.5 text-[12px]"
            title={
              ai === 'ready'
                ? 'A language model is reachable: written answers and explanations are available.'
                : 'No language model is reachable. Everything structural still works: overview, architecture, call flow, summaries and search.'
            }
          >
            <Sparkles size={12} className={ai === 'ready' ? 'text-ok' : 'text-text-3'} aria-hidden />
            <span className={ai === 'ready' ? 'text-text-1' : 'text-text-2'}>
              {ai === 'ready' ? 'AI on' : 'AI off'}
            </span>
          </span>
        )}
        <button
          type="button"
          onClick={onIndex}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-control px-2.5 text-[13px] text-text-1 transition-colors duration-150 hover:bg-bg-3"
        >
          <FolderPlus size={14} aria-hidden />
          Index project
        </button>
      </div>
    </header>
  )
}
