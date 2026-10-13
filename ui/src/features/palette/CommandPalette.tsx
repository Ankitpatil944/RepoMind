import { Command } from 'cmdk'
import { FileCode2, FunctionSquare, MessageSquare, Route } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { useEndpoints, useFiles, useSymbols } from '../../api/hooks'
import type { Endpoint, SymbolHit } from '../../api/types'
import { MethodPill, RoleBadge, roleOf } from '../../design/primitives'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  repo: number | null
  onEndpoint: (e: Endpoint) => void
  onSymbol: (s: SymbolHit) => void
  onFile: (path: string) => void
  onAsk: (question: string) => void
}

const ITEM =
  'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-[13px] text-text-1 aria-selected:bg-bg-3 aria-selected:shadow-[inset_2px_0_0_var(--accent-500)]'

export function CommandPalette({ open, onOpenChange, repo, onEndpoint, onSymbol, onFile, onAsk }: Props) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 150)
    return () => clearTimeout(t)
  }, [q])
  useEffect(() => {
    if (!open) setQ('')
  }, [open])

  const endpoints = useEndpoints(open ? repo : null)
  const files = useFiles(open ? repo : null)
  const symbols = useSymbols(repo, debounced, open && debounced.length >= 2)

  const needle = q.trim().toLowerCase()
  const matchEndpoints = useMemo(
    () =>
      needle
        ? (endpoints.data ?? [])
            .filter((e) => `${e.method} ${e.path} ${e.handler ?? ''}`.toLowerCase().includes(needle))
            .slice(0, 6)
        : [],
    [endpoints.data, needle],
  )
  const matchFiles = useMemo(
    () => (needle ? (files.data ?? []).filter((f) => f.path.toLowerCase().includes(needle)).slice(0, 6) : []),
    [files.data, needle],
  )
  const matchSymbols = debounced.length >= 2 ? (symbols.data ?? []).slice(0, 8) : []

  const close = () => onOpenChange(false)

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      shouldFilter={false}
      overlayClassName="fixed inset-0 z-40 bg-bg-0/70 backdrop-blur-[2px]"
      contentClassName="fixed left-1/2 top-[14vh] z-50 w-[min(640px,92vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-border-control bg-bg-1 shadow-2xl"
    >
      <Command.Input
        value={q}
        onValueChange={setQ}
        placeholder="Search endpoints, functions, files, or ask a question…"
        className="h-12 w-full border-b border-border-subtle bg-transparent px-4 text-[15px] text-text-1 placeholder:text-text-3 focus:outline-none"
      />
      <Command.List className="max-h-[50vh] overflow-auto p-2">
        <Command.Empty className="px-3 py-6 text-center text-text-2">
          {needle ? 'No matches. Press Enter on the question below to ask it instead.' : 'Start typing to search.'}
        </Command.Empty>

        {matchEndpoints.length > 0 && (
          <Command.Group heading="Endpoints" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-text-3">
            {matchEndpoints.map((e) => (
              <Command.Item key={`e${e.id}`} value={`endpoint-${e.id}`} className={ITEM} onSelect={() => (onEndpoint(e), close())}>
                <Route size={14} className="text-text-2" aria-hidden />
                <MethodPill method={e.method} />
                <span className="truncate font-mono">{e.path}</span>
                <RoleBadge role={roleOf(e)} compact className="ml-auto" />
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {matchSymbols.length > 0 && (
          <Command.Group heading="Functions & classes" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-text-3">
            {matchSymbols.map((s) => (
              <Command.Item key={`s${s.chunk_id}`} value={`symbol-${s.chunk_id}`} className={ITEM} onSelect={() => (onSymbol(s), close())}>
                <FunctionSquare size={14} className="text-text-2" aria-hidden />
                <span className="truncate font-mono">{s.qualified_name}</span>
                <span className="ml-auto truncate font-mono text-[11.5px] text-text-2">
                  {s.file}:{s.start_line}
                </span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {matchFiles.length > 0 && (
          <Command.Group heading="Files" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-text-3">
            {matchFiles.map((f) => (
              <Command.Item key={`f${f.path}`} value={`file-${f.path}`} className={ITEM} onSelect={() => (onFile(f.path), close())}>
                <FileCode2 size={14} className="text-text-2" aria-hidden />
                <span className="truncate font-mono">{f.path}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {needle.length > 2 && (
          <Command.Group heading="Ask" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-text-3">
            <Command.Item value="ask" className={ITEM} onSelect={() => (onAsk(q.trim()), close())}>
              <MessageSquare size={14} className="text-accent-400" aria-hidden />
              <span className="truncate">
                Ask: <span className="text-text-2">{q.trim()}</span>
              </span>
            </Command.Item>
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  )
}
