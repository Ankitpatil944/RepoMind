import { useMemo, useState } from 'react'

import type { FileEntry } from '../../api/types'
import { layoutTreemap } from '../../lib/treemap'
import { heat, langName } from './colors'

const W = 100
const H = 52

interface Props {
  files: FileEntry[]
  onOpen: (path: string) => void
}

interface Cell {
  file: FileEntry
  x: number
  y: number
  w: number
  h: number
}

interface Group {
  name: string
  x: number
  y: number
  w: number
  h: number
  cells: Cell[]
}

const MAX_DEPTH = 4

/** Group files by folder at the shallowest depth that actually splits the repo. A monorepo
 *  with everything under `services/` would otherwise be one giant tile, so we go deeper
 *  while a single folder holds most of the code (and the depth still adds groups). */
export function groupByFolder(files: FileEntry[]): Map<string, FileEntry[]> {
  const at = (depth: number) => {
    const byDir = new Map<string, FileEntry[]>()
    for (const f of files) {
      const parts = f.path.split('/')
      const key = parts.length > 1 ? parts.slice(0, Math.min(depth, parts.length - 1)).join('/') : '(root)'
      byDir.set(key, [...(byDir.get(key) ?? []), f])
    }
    return byDir
  }
  const total = files.reduce((a, f) => a + f.loc, 0) || 1
  let best = at(1)
  for (let depth = 2; depth <= MAX_DEPTH; depth++) {
    const largest = Math.max(...[...best.values()].map((fs) => fs.reduce((a, f) => a + f.loc, 0)))
    if (largest / total < 0.6) break
    const next = at(depth)
    if (next.size <= best.size) break
    best = next
  }
  return best
}

/** Risk map: a two-level treemap. Size = lines of code, heat = complexity of the file
 *  relative to the most complex one. Hovering a tile dims the rest and fills the
 *  readout line; hot tiles pulse. Every cell is a real button. */
export function Treemap({ files, onOpen }: Props) {
  const [hover, setHover] = useState<FileEntry | null>(null)
  const maxCx = useMemo(() => Math.max(1, ...files.map((f) => f.complexity)), [files])

  const groups = useMemo<Group[]>(() => {
    const byDir = groupByFolder(files.filter((f) => f.loc > 0))
    const dirRects = layoutTreemap(
      [...byDir.entries()].map(([id, fs]) => ({ id, value: fs.reduce((a, f) => a + f.loc, 0) })),
      W,
      H,
    )
    return dirRects.map((r) => {
      const inner = layoutTreemap(
        (byDir.get(r.id) ?? []).map((f) => ({ id: f.path, value: f.loc })),
        r.w,
        r.h,
      )
      const byPath = new Map((byDir.get(r.id) ?? []).map((f) => [f.path, f]))
      return {
        name: r.id,
        x: r.x,
        y: r.y,
        w: r.w,
        h: r.h,
        cells: inner.map((c) => ({ file: byPath.get(c.id) as FileEntry, x: c.x, y: c.y, w: c.w, h: c.h })),
      }
    })
  }, [files])

  if (groups.length === 0) return <p className="text-text-2">No files to draw.</p>

  let index = 0
  return (
    <div>
      <div
        role="group"
        aria-label="Repository structure treemap"
        className="relative w-full overflow-hidden rounded-[10px] border border-border-subtle bg-bg-1"
        style={{ aspectRatio: `${W} / ${H}` }}
        onMouseLeave={() => setHover(null)}
      >
        {groups.map((g) => (
          <div
            key={g.name}
            className="absolute rounded-[6px] shadow-[inset_0_0_0_1px_var(--border-control)]"
            style={{
              left: `${g.x}%`,
              top: `${(g.y / H) * 100}%`,
              width: `${g.w}%`,
              height: `${(g.h / H) * 100}%`,
            }}
          >
            {g.cells.map((c) => {
              const i = index++
              // Cell sizes are in container-percent units, so these thresholds are
              // "wide/tall enough to fit a label" regardless of screen size.
              const heightPct = (c.h / H) * 100
              const big = c.w > 7 && heightPct > 14
              const huge = c.w > 14 && heightPct > 26
              const t = c.file.complexity / maxCx
              const { bg, border } = heat(t)
              const dimmed = hover !== null && hover.path !== c.file.path
              return (
                <button
                  key={c.file.path}
                  type="button"
                  onClick={() => onOpen(c.file.path)}
                  onMouseEnter={() => setHover(c.file)}
                  onFocus={() => setHover(c.file)}
                  onBlur={() => setHover(null)}
                  title={`${c.file.path}\n${c.file.loc} lines · ${c.file.symbols} symbols${c.file.endpoints ? ` · ${c.file.endpoints} routes` : ''}`}
                  aria-label={`${c.file.path}, ${c.file.loc} lines${c.file.endpoints ? `, ${c.file.endpoints} routes` : ''}`}
                  className="treemap-cell pop absolute p-[1.5px] text-left"
                  style={{
                    left: `${(c.x / g.w) * 100}%`,
                    top: `${(c.y / g.h) * 100}%`,
                    width: `${(c.w / g.w) * 100}%`,
                    height: `${(c.h / g.h) * 100}%`,
                    animationDelay: `${Math.min(i, 40) * 18}ms`,
                    opacity: dimmed ? 0.4 : 1,
                    transition: 'opacity 150ms linear, filter 150ms linear',
                  }}
                >
                  <span
                    className={`flex h-full w-full flex-col gap-0.5 overflow-hidden rounded-[5px] border p-[7px_8px] ${t > 0.7 ? 'breathe' : ''}`}
                    style={{
                      background: bg,
                      borderColor: border,
                      boxShadow: c.file.endpoints ? 'inset 0 -3px 0 var(--accent-400)' : undefined,
                    }}
                  >
                    {big && (
                      <span className="block truncate font-mono text-[11px] leading-tight text-text-1">
                        {c.file.path.split('/').pop()}
                      </span>
                    )}
                    {huge && (
                      <span className="block truncate font-mono text-[10.5px] text-text-2">
                        {c.file.loc} loc{c.file.endpoints ? ` · ${c.file.endpoints} routes` : ''}
                      </span>
                    )}
                  </span>
                </button>
              )
            })}
            {g.w > 9 && (g.h / H) * 100 > 12 && (
              <span
                className="pointer-events-none absolute bottom-1.5 right-2 z-[1] max-w-[calc(100%-1rem)] truncate rounded bg-bg-0/80 px-1 font-mono text-[10.5px] text-text-2"
                title={g.name}
              >
                {g.name.split('/').pop()}
              </span>
            )}
          </div>
        ))}
      </div>

      <p className="mt-2 min-h-5 font-mono text-[12px] text-text-2" aria-live="polite">
        {hover ? (
          <>
            <span className="text-cream">{hover.path}</span> · {hover.loc} lines · {hover.symbols} symbols
            {hover.endpoints ? ` · ${hover.endpoints} routes` : ''} · {langName(hover.language)} · complexity{' '}
            {hover.complexity}
          </>
        ) : (
          'Hover a tile for details. Click to open it.'
        )}
      </p>
      <ul className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-text-2" aria-label="Treemap legend">
        <li className="flex items-center gap-1.5">
          Cool
          <span
            className="h-2 w-16 rounded-full"
            style={{ background: `linear-gradient(90deg, ${heat(0).bg}, ${heat(1).border})` }}
            aria-hidden
          />
          Hot (complexity)
        </li>
        <li className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-sage" aria-hidden />
          Defines HTTP routes
        </li>
      </ul>
    </div>
  )
}
