import { describe, expect, it } from 'vitest'

import type { FileEntry, FlowGraph } from '../api/types'
import { citationRef, linkCitations } from './citations'
import { buildOutline, layoutFlow, pathEdgeIds } from './graph'
import { buildHash, DEFAULT_STATE, parseHash } from './hash'
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
    }

    expect(parseHash(buildHash(state))).toEqual(state)
  })

  it('omits defaults so urls stay short', () => {
    expect(buildHash({ ...DEFAULT_STATE, repo: 3 })).toBe('#repo=3')
    expect(buildHash(DEFAULT_STATE)).toBe('')
  })

  it('sanitises hostile or garbage input', () => {
    const s = parseHash('#repo=abc&depth=99&tab=hax&dir=sideways&start=-')

    expect(s.repo).toBeNull()
    expect(s.depth).toBe(4)
    expect(s.tab).toBe('source')
    expect(s.dir).toBe('down')
    expect(s.start).toBeNull()
  })
})

describe('file tree', () => {
  const files: FileEntry[] = [
    { path: 'app/routes/auth.py', language: 'python', symbols: 5, endpoints: 5 },
    { path: 'app/security.py', language: 'python', symbols: 6, endpoints: 0 },
    { path: 'webhooks/server.js', language: 'javascript', symbols: 3, endpoints: 2 },
    { path: 'main.py', language: 'python', symbols: 1, endpoints: 1 },
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
