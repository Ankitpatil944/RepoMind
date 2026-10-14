import { describe, expect, it } from 'vitest'

import type { FileEntry, FlowGraph } from '../api/types'
import { citationRef, linkCitations } from './citations'
import { buildOutline, layoutFlow, neighbourhood, pathEdgeIds } from './graph'
import { buildHash, DEFAULT_STATE, parseHash } from './hash'
import { layoutTreemap } from './treemap'
import { ancestors, buildFileTree, flattenVisible } from './tree'

describe('url state', () => {
  it('round-trips a full state', () => {
    const state = {
      ...DEFAULT_STATE,
      repo: 7,
      ep: 12,
      sel: 'c:55',
      file: 'app/routes/auth.py',
      start: 15,
      end: 21,
      tab: 'explain' as const,
      ex: 'files' as const,
      depth: 4,
      dir: 'both' as const,
      outline: true,
      view: 'architecture' as const,
      arch: 'app/routes',
    }

    expect(parseHash(buildHash(state))).toEqual(state)
  })

  it('defaults to the overview view and summary tab', () => {
    expect(DEFAULT_STATE.view).toBe('overview')
    expect(DEFAULT_STATE.tab).toBe('summary')
    expect(parseHash('').view).toBe('overview')
    expect(parseHash('#view=nope').view).toBe('overview')
    expect(parseHash('#arch=%2F%2Fapp%2F%2F').arch).toBe('app')
  })

  it('omits defaults so urls stay short', () => {
    expect(buildHash({ ...DEFAULT_STATE, repo: 3 })).toBe('#repo=3')
    expect(buildHash(DEFAULT_STATE)).toBe('')
  })

  it('sanitises hostile or garbage input', () => {
    const s = parseHash('#repo=abc&depth=99&tab=hax&dir=sideways&start=-')

    expect(s.repo).toBeNull()
    expect(s.depth).toBe(4)
    expect(s.tab).toBe('summary') // falls back to the default tab
    expect(s.dir).toBe('down')
    expect(s.start).toBeNull()
  })
})

describe('file tree', () => {
  const files: FileEntry[] = [
    { path: 'app/routes/auth.py', language: 'python', symbols: 5, endpoints: 5, loc: 50, complexity: 9 },
    { path: 'app/security.py', language: 'python', symbols: 6, endpoints: 0, loc: 60, complexity: 8 },
    { path: 'webhooks/server.js', language: 'javascript', symbols: 3, endpoints: 2, loc: 30, complexity: 4 },
    { path: 'main.py', language: 'python', symbols: 1, endpoints: 1, loc: 12, complexity: 1 },
  ]

  it('nests directories first and rolls up counts', () => {
    const root = buildFileTree(files)

    expect(root.children.map((c) => c.name)).toEqual(['app', 'webhooks', 'main.py'])
    const app = root.children[0]
    expect(app.fileCount).toBe(2)
    expect(app.endpoints).toBe(5)
    expect(app.children.map((c) => c.name)).toEqual(['routes', 'security.py'])
  })

  it('only shows children of expanded directories', () => {
    const root = buildFileTree(files)

    const collapsed = flattenVisible(root, new Set())
    const open = flattenVisible(root, new Set(['app', 'app/routes']))

    expect(collapsed.map((r) => r.node.path)).toEqual(['app', 'webhooks', 'main.py'])
    expect(open.map((r) => r.node.path)).toContain('app/routes/auth.py')
    expect(open.find((r) => r.node.path === 'app/routes/auth.py')?.depth).toBe(2)
  })

  it('lists ancestor directories', () => {
    expect(ancestors('a/b/c.py')).toEqual(['a', 'a/b'])
    expect(ancestors('c.py')).toEqual([])
  })
})

const FLOW: FlowGraph = {
  root: 'e:1',
  depth: 3,
  direction: 'down',
  truncated: false,
  nodes: [
    { id: 'e:1', type: 'endpoint', label: 'POST /auth/login' },
    { id: 'c:10', type: 'function', label: 'login' },
    { id: 'c:11', type: 'function', label: 'verify_password' },
    { id: 'c:12', type: 'function', label: 'create_access_token' },
    { id: 'x:jwt.encode', type: 'external', label: 'jwt.encode' },
  ],
  edges: [
    { id: 'e:1->c:10', source: 'e:1', target: 'c:10', line: null, kind: 'handles' },
    { id: 'c:10->c:11', source: 'c:10', target: 'c:11', line: 17, kind: 'calls' },
    { id: 'c:10->c:12', source: 'c:10', target: 'c:12', line: 19, kind: 'calls' },
    { id: 'c:12->x:jwt.encode', source: 'c:12', target: 'x:jwt.encode', line: 24, kind: 'calls' },
  ],
}

describe('graph helpers', () => {
  it('lays nodes out left to right without overlap', () => {
    const pos = layoutFlow(FLOW)

    expect(pos.size).toBe(FLOW.nodes.length)
    expect(pos.get('e:1')!.x).toBeLessThan(pos.get('c:10')!.x)
    expect(pos.get('c:10')!.x).toBeLessThan(pos.get('c:12')!.x)
    expect(pos.get('c:12')!.x).toBeLessThan(pos.get('x:jwt.encode')!.x)
    const siblings = [pos.get('c:11')!, pos.get('c:12')!]
    expect(siblings[0].y).not.toBe(siblings[1].y)
  })

  it('finds the edges on the path from the root to a node', () => {
    const edges = pathEdgeIds(FLOW, 'x:jwt.encode')

    expect([...edges].sort()).toEqual(['c:10->c:12', 'c:12->x:jwt.encode', 'e:1->c:10'])
    expect(pathEdgeIds(FLOW, null).size).toBe(0)
    expect(pathEdgeIds(FLOW, 'e:1').size).toBe(0)
  })

  it('builds a text outline with relations and survives cycles', () => {
    const cyclic: FlowGraph = {
      ...FLOW,
      edges: [...FLOW.edges, { id: 'c:11->c:10', source: 'c:11', target: 'c:10', line: 3, kind: 'calls' }],
    }

    const outline = buildOutline(cyclic)!

    expect(outline.node.id).toBe('e:1')
    expect(outline.children[0].relation).toBe('handles')
    const login = outline.children[0]
    expect(login.children.map((c) => [c.node.label, c.relation])).toEqual([
      ['verify_password', 'calls'],
      ['create_access_token', 'calls'],
    ])
    const count = (o: typeof outline): number => 1 + o.children.reduce((n, c) => n + count(c), 0)
    expect(count(outline)).toBe(FLOW.nodes.length)
  })
})

describe('treemap', () => {
  it('fills the area exactly with rectangles proportional to value', () => {
    const items = [
      { id: 'a', value: 60 },
      { id: 'b', value: 25 },
      { id: 'c', value: 10 },
      { id: 'd', value: 5 },
    ]

    const rects = layoutTreemap(items, 100, 50)

    expect(rects).toHaveLength(4)
    const area = (r: { w: number; h: number }) => r.w * r.h
    expect(rects.reduce((a, r) => a + area(r), 0)).toBeCloseTo(5000, 3)
    const a = rects.find((r) => r.id === 'a')!
    expect(area(a) / 5000).toBeCloseTo(0.6, 3)
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(-1e-9)
      expect(r.y).toBeGreaterThanOrEqual(-1e-9)
      expect(r.x + r.w).toBeLessThanOrEqual(100 + 1e-9)
      expect(r.y + r.h).toBeLessThanOrEqual(50 + 1e-9)
    }
  })

  it('does not overlap and ignores empty items', () => {
    const rects = layoutTreemap(
      [
        { id: 'x', value: 10 },
        { id: 'y', value: 10 },
        { id: 'z', value: 0 },
      ],
      40,
      20,
    )

    expect(rects.map((r) => r.id).sort()).toEqual(['x', 'y'])
    const [p, q] = rects
    const overlap = p.x < q.x + q.w - 1e-9 && q.x < p.x + p.w - 1e-9 && p.y < q.y + q.h - 1e-9 && q.y < p.y + p.h - 1e-9
    expect(overlap).toBe(false)
  })

  it('returns nothing for degenerate input', () => {
    expect(layoutTreemap([], 10, 10)).toEqual([])
    expect(layoutTreemap([{ id: 'a', value: 1 }], 0, 10)).toEqual([])
  })
})

describe('graph focus', () => {
  it('neighbourhood is the node plus direct neighbours only', () => {
    const n = neighbourhood(FLOW, 'c:10')

    expect([...n].sort()).toEqual(['c:10', 'c:11', 'c:12', 'e:1'])
    expect(neighbourhood(FLOW, null).size).toBe(0)
  })
})

describe('citations', () => {
  it('links [n] markers but not existing markdown links', () => {
    expect(linkCitations('Uses login [1] and hash [2][3]. See [docs](http://x).')).toBe(
      'Uses login [1](#cite-1) and hash [2](#cite-2)[3](#cite-3). See [docs](http://x).',
    )
  })

  it('parses citation hrefs', () => {
    expect(citationRef('#cite-4')).toBe(4)
    expect(citationRef('https://example.com')).toBeNull()
    expect(citationRef(undefined)).toBeNull()
  })
})
