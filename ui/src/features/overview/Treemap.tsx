import { useMemo } from 'react'

import type { FileEntry } from '../../api/types'
import { layoutTreemap } from '../../lib/treemap'
import { langColor, langName } from './colors'

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

/** Two-level treemap: directories laid out by total size, files inside each.
 *  Cells cascade in; hovering lifts one. Every cell is a real button. */
export function Treemap({ files, onOpen }: Props) {
  const groups = useMemo<Group[]>(() => {
    const byDir = new Map<string, FileEntry[]>()
    for (const f of files) {
      if (f.loc <= 0) continue
      const top = f.path.includes('/') ? f.path.split('/')[0] : '(root)'
      byDir.set(top, [...(byDir.get(top) ?? []), f])
    }
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
        className="relative w-full overflow-hidden rounded-lg bg-bg-0"
        style={{ aspectRatio: `${W} / ${H}` }}
      >
        {groups.map((g) => (
          <div
            key={g.name}
            className="absolute"
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
              return (
                <button
                  key={c.file.path}
                  type="button"
                  onClick={() => onOpen(c.file.path)}
                  title={`${c.file.path}\n${c.file.loc} lines · ${c.file.symbols} symbols${c.file.endpoints ? ` · ${c.file.endpoints} routes` : ''}`}
                  aria-label={`${c.file.path}, ${c.file.loc} lines${c.file.endpoints ? `, ${c.file.endpoints} routes` : ''}`}
                  className="treemap-cell cell-in absolute overflow-hidden rounded-[5px] border p-1 text-left"
                  style={{
                    left: `${(c.x / g.w) * 100}%`,
                    top: `${(c.y / g.h) * 100}%`,
                    width: `calc(${(c.w / g.w) * 100}% - 2px)`,
                    height: `calc(${(c.h / g.h) * 100}% - 2px)`,
                    margin: 1,
                    animationDelay: `${Math.min(i, 40) * 18}ms`,
                    background: `color-mix(in srgb, ${langColor(c.file.language)} 18%, var(--bg-2))`,
                    borderColor: `color-mix(in srgb, ${langColor(c.file.language)} 42%, var(--bg-2))`,
                    boxShadow: c.file.endpoints
                      ? 'inset 0 -3px 0 var(--accent-500)'
                      : undefined,
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
                </button>
              )
            })}
            <span className="pointer-events-none absolute left-1.5 top-1 z-[1] rounded bg-bg-0/80 px-1 font-mono text-[10.5px] text-text-2">
              {g.name}
            </span>
          </div>
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-text-2" aria-label="Treemap legend">
        {[...new Set(files.map((f) => f.language))].map((l) => (
          <li key={l} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: langColor(l) }} aria-hidden />
            <span>{langName(l)}</span>
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-accent-500" aria-hidden />
          Defines HTTP routes
        </li>
      </ul>
    </div>
  )
}
