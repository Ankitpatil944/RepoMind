import { useCallback, useSyncExternalStore } from 'react'

import type { Direction } from '../api/types'

export type InspectorTab = 'summary' | 'source' | 'explain' | 'evidence'
export type View = 'overview' | 'architecture' | 'flow'
export type ExplorerTab = 'files' | 'symbols' | 'endpoints'

/** Everything that defines "what the user is looking at", kept in the URL hash
 *  so any view is a shareable deep link and the back button works. */
export interface AppState {
  repo: number | null
  ep: number | null // graph focus: endpoint id
  ch: number | null // graph focus: chunk id
  sel: string | null // selected graph node id ("c:12", "e:3", "x:jwt.decode")
  file: string | null
  start: number | null
  end: number | null
  tab: InspectorTab
  ex: ExplorerTab
  depth: number
  dir: Direction
  outline: boolean
  view: View
  arch: string // architecture view: directory being drilled into ('' = top)
}

export const DEFAULT_STATE: AppState = {
  repo: null,
  ep: null,
  ch: null,
  sel: null,
  file: null,
  start: null,
  end: null,
  tab: 'summary',
  ex: 'endpoints',
  depth: 3,
  dir: 'down',
  outline: false,
  view: 'overview',
  arch: '',
}

const int = (v: string | null): number | null => {
  if (v === null) return null
  const n = Number.parseInt(v, 10)
  return Number.isFinite(n) ? n : null
}
const oneOf = <T extends string>(v: string | null, allowed: readonly T[], fallback: T): T =>
  allowed.includes(v as T) ? (v as T) : fallback

export function parseHash(hash: string): AppState {
  const p = new URLSearchParams(hash.replace(/^#/, ''))
  const depth = int(p.get('depth'))
  return {
    repo: int(p.get('repo')),
    ep: int(p.get('ep')),
    ch: int(p.get('ch')),
    sel: p.get('sel'),
    file: p.get('file'),
    start: int(p.get('start')),
    end: int(p.get('end')),
    tab: oneOf(p.get('tab'), ['summary', 'source', 'explain', 'evidence'] as const, DEFAULT_STATE.tab),
    ex: oneOf(p.get('ex'), ['files', 'symbols', 'endpoints'] as const, DEFAULT_STATE.ex),
    depth: depth === null ? DEFAULT_STATE.depth : Math.min(4, Math.max(1, depth)),
    dir: oneOf(p.get('dir'), ['down', 'up', 'both'] as const, DEFAULT_STATE.dir),
    outline: p.get('outline') === '1',
    view: oneOf(p.get('view'), ['overview', 'architecture', 'flow'] as const, DEFAULT_STATE.view),
    arch: (p.get('arch') ?? '').replace(/^\/+|\/+$/g, ''),
  }
}

export function buildHash(state: AppState): string {
  const p = new URLSearchParams()
  const put = (k: string, v: string | number | null) => {
    if (v !== null && v !== '') p.set(k, String(v))
  }
  put('repo', state.repo)
  put('ep', state.ep)
  put('ch', state.ch)
  put('sel', state.sel)
  put('file', state.file)
  put('start', state.start)
  put('end', state.end)
  if (state.tab !== DEFAULT_STATE.tab) put('tab', state.tab)
  if (state.ex !== DEFAULT_STATE.ex) put('ex', state.ex)
  if (state.depth !== DEFAULT_STATE.depth) put('depth', state.depth)
  if (state.dir !== DEFAULT_STATE.dir) put('dir', state.dir)
  if (state.outline) put('outline', 1)
  if (state.view !== DEFAULT_STATE.view) put('view', state.view)
  put('arch', state.arch)
  const s = p.toString()
  return s ? `#${s}` : ''
}

function subscribe(cb: () => void): () => void {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}
const getSnapshot = () => window.location.hash

export function useAppState(): [AppState, (patch: Partial<AppState>) => void] {
  const hash = useSyncExternalStore(subscribe, getSnapshot, () => '')
  const state = parseHash(hash)
  const set = useCallback((patch: Partial<AppState>) => {
    const next = { ...parseHash(window.location.hash), ...patch }
    const h = buildHash(next)
    if (h !== window.location.hash) window.location.hash = h
  }, [])
  return [state, set]
}
