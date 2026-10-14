import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChunkFacts, Endpoint, FlowGraph, ModuleGraph, Overview } from '../api/types'
import App from './App'

const REPOS = [{ id: 1, name: 'shop_api', path: '/samples/shop_api', indexed_at: null, files: 3, chunks: 20 }]

const ep = (over: Partial<Endpoint>): Endpoint => ({
  id: 0,
  method: 'GET',
  path: '/',
  framework: 'fastapi',
  file: 'app/routes/auth.py',
  line: 1,
  handler: null,
  handler_chunk_id: null,
  handles_authentication: false,
  requires_auth: false,
  evidence: [],
  ...over,
})

const ENDPOINTS: Endpoint[] = [
  ep({
    id: 11, method: 'GET', path: '/orders', file: 'app/routes/orders.py', line: 14,
    handler: 'list_orders', handler_chunk_id: 200, requires_auth: true,
    evidence: ["guarded by 'Depends(get_current_user)'"],
  }),
  ep({
    id: 10, method: 'POST', path: '/auth/login', line: 15, handler: 'login', handler_chunk_id: 100,
    handles_authentication: true,
    evidence: ["path '/auth/login' looks like an authentication endpoint", "calls 'verify_password'"],
  }),
  ep({ id: 12, method: 'GET', path: '/health', file: 'app/main.py', line: 18, handler: 'health' }),
]

const FLOW: FlowGraph = {
  root: 'e:10',
  depth: 3,
  direction: 'down',
  truncated: false,
  nodes: [
    {
      id: 'e:10', type: 'endpoint', label: 'POST /auth/login', method: 'POST', path: '/auth/login',
      file: 'app/routes/auth.py', start_line: 15, end_line: 15, endpoint_id: 10, handler_chunk_id: 100,
      handles_authentication: true, requires_auth: false,
      evidence: ["path '/auth/login' looks like an authentication endpoint", "calls 'verify_password'"],
    },
    {
      id: 'c:100', type: 'function', label: 'login', name: 'login', file: 'app/routes/auth.py',
      start_line: 15, end_line: 21, chunk_id: 100,
      signature: 'def login(email: str, password: str)',
      doc: 'Exchange an email and password for an access token.',
      complexity: 4, loc: 7, fan_in: 0, fan_out: 3,
    },
    {
      id: 'c:101', type: 'function', label: 'verify_password', name: 'verify_password',
      file: 'app/security.py', start_line: 19, end_line: 20, chunk_id: 101, auth_related: true,
      signature: 'def verify_password(raw, salt, expected)', complexity: 1, loc: 2, fan_in: 1, fan_out: 1,
    },
    { id: 'x:jwt.encode', type: 'external', label: 'jwt.encode', auth_related: true },
  ],
  edges: [
    { id: 'e:10->c:100', source: 'e:10', target: 'c:100', line: null, kind: 'handles' },
    { id: 'c:100->c:101', source: 'c:100', target: 'c:101', line: 17, kind: 'calls' },
    { id: 'c:100->x:jwt.encode', source: 'c:100', target: 'x:jwt.encode', line: 19, kind: 'calls' },
  ],
}

const OVERVIEW: Overview = {
  totals: { files: 13, loc: 412, functions: 31, classes: 3, endpoints: 17, internal_links: 22 },
  languages: [
    { language: 'python', files: 12, loc: 380 },
    { language: 'javascript', files: 1, loc: 32 },
  ],
  auth: { authentication: 5, protected: 7, public: 5 },
  hotspots: {
    most_called: [
      { chunk_id: 300, name: 'run_query', file: 'app/db.py', line: 18, complexity: 1, loc: 4, doc: '', fan_in: 6 },
    ],
    most_complex: [
      { chunk_id: 100, name: 'login', file: 'app/routes/auth.py', line: 15, complexity: 4, loc: 7, doc: '', label: 'low' },
    ],
    largest_files: [{ path: 'app/security.py', loc: 53, language: 'python' }],
  },
  guards: [
    { chunk_id: 400, name: 'get_current_user', file: 'app/security.py', line: 33, complexity: 3, loc: 8, doc: '', fan_in: 7 },
  ],
  dependencies: {
    third_party: [{ name: 'fastapi', files: 5 }, { name: 'jwt', files: 1 }],
    stdlib: [{ name: 'hashlib', files: 2 }],
  },
  frameworks: ['fastapi', 'express'],
}

const FACTS: ChunkFacts = {
  chunk_id: 100,
  name: 'login',
  qualified_name: 'login',
  kind: 'function',
  file: 'app/routes/auth.py',
  language: 'python',
  start_line: 15,
  end_line: 21,
  signature: 'def login(email: str, password: str)',
  doc: 'Exchange an email and password for an access token.',
  complexity: 4,
  complexity_label: 'low',
  loc: 7,
  callees_internal: [{ chunk_id: 101, name: 'verify_password', file: 'app/security.py', line: 19 }],
  callees_external: ['jwt.encode'],
  callers: [],
  endpoints: [
    {
      id: 10, method: 'POST', path: '/auth/login', handles_authentication: true,
      requires_auth: false, evidence: ["path '/auth/login' looks like an authentication endpoint"],
    },
  ],
  summary: [
    '`login` is a function in `app/routes/auth.py` (lines 15-21, 7 lines).',
    'It handles the route `POST /auth/login`; it performs authentication.',
  ],
}

const MODULES: ModuleGraph = {
  root: '',
  level: 'dir',
  truncated: false,
  breadcrumb: [],
  nodes: [
    { id: 'app', kind: 'dir', label: 'app', path: 'app', files: 10, loc: 220, endpoints: 15, complexity: 40, symbols: 30, languages: ['python'], degree: 3 },
    { id: 'webhooks', kind: 'dir', label: 'webhooks', path: 'webhooks', files: 4, loc: 180, endpoints: 2, complexity: 5, symbols: 3, languages: ['javascript'], degree: 0 },
  ],
  edges: [],
}
// one folder holds nearly everything, like services/ in a microservice repo
const MODULES_DOMINANT: ModuleGraph = {
  ...MODULES,
  nodes: [
    { ...MODULES.nodes[0], loc: 3800 },
    { ...MODULES.nodes[1], loc: 32 },
  ],
}
const MODULES_APP: ModuleGraph = {
  ...MODULES,
  root: 'app',
  breadcrumb: ['app'],
  nodes: [
    { id: 'app/routes', kind: 'dir', label: 'routes', path: 'app/routes', files: 4, loc: 150, endpoints: 15, complexity: 20, symbols: 12, languages: ['python'], degree: 2 },
    { id: 'app/security.py', kind: 'file', label: 'security.py', path: 'app/security.py', files: 1, loc: 53, endpoints: 0, complexity: 9, symbols: 7, languages: ['python'], degree: 2 },
  ],
  edges: [{ id: 'app/routes->app/security.py', source: 'app/routes', target: 'app/security.py', weight: 4 }],
}

const FILE_INFO = {
  path: 'app/routes/auth.py',
  language: 'python',
  loc: 50,
  doc: 'Authentication routes.',
  symbols: [
    { chunk_id: 100, kind: 'function', name: 'login', start_line: 15, end_line: 21, signature: 'def login(email, password)', doc: 'Exchange credentials.', complexity: 4, loc: 7, fan_in: 0 },
  ],
  imports: { internal: ['app/security.py'], third_party: ['fastapi'], stdlib: [] },
  imported_by: ['app/main.py'],
  endpoints: [{ method: 'POST', path: '/auth/login', line: 15 }],
}

const FILE = {
  path: 'app/routes/auth.py',
  language: 'python',
  content: 'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/auth")\n\n\n@router.post("/login")\ndef login(email, password):\n    return {"ok": True}\n',
  changed_since_indexed: false,
  symbols: [{ chunk_id: 100, name: 'login', qualified_name: 'login', kind: 'function', start_line: 6, end_line: 8 }],
}

let calls: Array<{ url: string; method: string; body?: string }>
let llmStatus: 'ready' | 'unreachable' = 'unreachable'
let dominantFolder = false

function route(url: string, init?: RequestInit): unknown {
  const u = new URL(url, 'http://test')
  const p = u.pathname
  if (init?.method === 'POST' && p === '/ask') {
    return {
      answer: 'Login is handled by `login` [1].',
      error: null,
      sources: [{ ref: 1, chunk_id: 100, file: 'app/routes/auth.py', start_line: 15, end_line: 21, kind: 'function', name: 'login' }],
    }
  }
  if (init?.method === 'POST' && p === '/explain') {
    return { answer: null, error: 'LLM request failed: connection refused', sources: [], callers: [], endpoints: [] }
  }
  if (p === '/capabilities') {
    return { llm: { status: llmStatus, base_url: 'http://x/v1', model: 'm' }, embedder: 'hashing', reranker: 'none' }
  }
  if (p === '/repos') return REPOS
  if (p === '/repos/1/endpoints') return ENDPOINTS
  if (p === '/repos/1/overview') return OVERVIEW
  if (p === '/repos/1/files') {
    return [
      { path: 'app/routes/auth.py', language: 'python', symbols: 5, endpoints: 1, loc: 50, complexity: 9 },
      { path: 'app/security.py', language: 'python', symbols: 6, endpoints: 0, loc: 53, complexity: 9 },
      { path: 'webhooks/server.js', language: 'javascript', symbols: 3, endpoints: 2, loc: 32, complexity: 5 },
    ]
  }
  if (p === '/repos/1/graph/flow') return FLOW
  if (p === '/repos/1/graph/modules') {
    if (u.searchParams.get('root') === 'app') return MODULES_APP
    return dominantFolder ? MODULES_DOMINANT : MODULES
  }
  if (p === '/repos/1/files/content') return FILE
  if (p === '/repos/1/files/info') return FILE_INFO
  if (p === '/repos/1/chunks/100/facts') return FACTS
  if (p === '/repos/1/symbols') return []
  throw new Error(`unmocked request: ${url}`)
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

/** Open the login endpoint's call flow via the explorer, like a user would. */
async function openLoginFlow() {
  const explorer = await screen.findByRole('complementary', { name: 'Explorer' })
  fireEvent.click(await within(explorer).findByText('/auth/login'))
  await screen.findByText('verify_password')
}

beforeEach(() => {
  calls = []
  llmStatus = 'unreachable'
  dominantFolder = false
  window.location.hash = ''
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? 'GET', body: init?.body as string | undefined })
      const body = route(String(input), init)
      return { ok: true, status: 200, statusText: 'OK', json: async () => body }
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Overview (works with no AI)', () => {
  it('lands on a repo overview with real statistics', async () => {
    renderApp()

    expect(await screen.findByRole('heading', { name: 'shop_api' })).toBeTruthy()
    expect(screen.getByLabelText('13 Files')).toBeTruthy()
    expect(screen.getByLabelText('412 Lines of code')).toBeTruthy()
    expect(screen.getByLabelText('17 Endpoints')).toBeTruthy()
    expect(screen.getByRole('list', { name: 'Detected stack' }).textContent).toContain('FastAPI')
    expect(window.location.hash).not.toContain('view=')
    // none of this needed the LLM endpoints
    expect(calls.some((c) => c.url === '/ask' || c.url === '/explain')).toBe(false)
  })

  it('shows hotspots, auth guards and dependencies', async () => {
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })

    const most = screen.getByRole('region', { name: 'Most called' })
    expect(within(most).getByText('run_query')).toBeTruthy()
    expect(within(most).getByText('6 callers')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Auth guards' })).getByText('get_current_user')).toBeTruthy()
    const deps = screen.getByRole('region', { name: 'Dependencies' })
    expect(within(deps).getByText(/fastapi/)).toBeTruthy()
    expect(within(deps).getByText(/hashlib/)).toBeTruthy()
    expect(screen.getByRole('img', { name: /5 authentication, 7 protected, 5 with no auth signal/ })).toBeTruthy()
  })

  it('draws a treemap whose cells open files with a static summary', async () => {
    renderApp()
    const cell = await screen.findByRole('button', { name: 'app/routes/auth.py, 50 lines, 1 routes' })

    fireEvent.click(cell)

    const inspector = await screen.findByRole('complementary', { name: 'Inspector' })
    expect(await within(inspector).findByText('Authentication routes.')).toBeTruthy()
    expect(window.location.hash).toContain('file=app%2Froutes%2Fauth.py')
    expect(within(inspector).getByText('def login(email, password)')).toBeTruthy()
    expect(within(inspector).getByText('app/main.py')).toBeTruthy() // imported by
  })

  it('"Start here" jumps straight into the auth flow', async () => {
    renderApp()

    fireEvent.click(await screen.findByRole('button', { name: /Trace POST \/auth\/login/ }))

    expect(await screen.findByText('verify_password')).toBeTruthy()
    expect(window.location.hash).toContain('view=flow')
    expect(window.location.hash).toContain('ep=10')
  })
})

describe('Call flow', () => {
  it('renders rich nodes: signature, docs and metrics', async () => {
    renderApp()
    await openLoginFlow()

    // Scope to the canvas: the Summary pane repeats the same signature and docs.
    const canvas = await screen.findByLabelText('Call graph', { selector: '.react-flow' })
    expect(await within(canvas).findByText('def login(email: str, password: str)')).toBeTruthy()
    expect(within(canvas).getByText('Exchange an email and password for an access token.')).toBeTruthy()
    expect(within(canvas).getByText('cx 4 · low')).toBeTruthy()
    expect(within(canvas).getByText('jwt.encode')).toBeTruthy()
    expect(calls.find((c) => c.url.includes('/graph/flow'))?.url).toContain('endpoint_id=10')
  })

  it('shows the same graph as an accessible text outline', async () => {
    renderApp()
    await openLoginFlow()

    fireEvent.click(screen.getByRole('button', { name: 'Show as outline (text)' }))

    const outline = await screen.findByRole('navigation', { name: 'Call graph outline' })
    expect(within(outline).getByText('verify_password')).toBeTruthy()
    expect(within(outline).getByText('jwt.encode')).toBeTruthy()
    expect(window.location.hash).toContain('outline=1')
  })

  it('Summary tab describes the selected function without any LLM', async () => {
    renderApp()
    await openLoginFlow()

    fireEvent.click(screen.getByRole('button', { name: 'Show as outline (text)' }))
    const outline = await screen.findByRole('navigation', { name: 'Call graph outline' })
    fireEvent.click(within(outline).getByText('login'))

    expect(await screen.findByText('What the code tells us')).toBeTruthy()
    expect(screen.getByText('It handles the route', { exact: false })).toBeTruthy()
    expect(screen.getByText(/Derived from static analysis/)).toBeTruthy()
    const facts = calls.filter((c) => c.url.includes('/chunks/100/facts'))
    expect(facts.length).toBeGreaterThan(0)
    expect(calls.some((c) => c.url === '/explain')).toBe(false)
  })

  it('explains why an endpoint was classified, in the Evidence tab', async () => {
    renderApp()
    await openLoginFlow()

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Evidence' }))

    expect(await screen.findByText("path '/auth/login' looks like an authentication endpoint")).toBeTruthy()
    expect(screen.getByText("calls 'verify_password'")).toBeTruthy()
  })

  it('loads the source of the selected endpoint', async () => {
    renderApp()
    await openLoginFlow()

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Source' }))

    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/files/content') && c.url.includes('app%2Froutes%2Fauth.py'))).toBe(true)
    })
  })
})

describe('Architecture map', () => {
  it('shows folders, and double-click drills into one', async () => {
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })

    fireEvent.click(screen.getByRole('tab', { name: /Architecture/ }))
    const map = await screen.findByLabelText('Module dependency map', { selector: '.react-flow' })
    expect(await within(map).findByText('webhooks')).toBeTruthy()
    expect(window.location.hash).toContain('view=architecture')

    fireEvent.doubleClick(within(map).getByText('app'))

    expect(await screen.findByText('security.py')).toBeTruthy()
    expect(window.location.hash).toContain('arch=app')
    expect(screen.getByRole('navigation', { name: 'Folder path' }).textContent).toContain('app')
  })

  it('opens inside the folder that holds nearly all the code', async () => {
    dominantFolder = true
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })

    fireEvent.click(screen.getByRole('tab', { name: /Architecture/ }))

    // the top-level map would be "app + a tiny folder": it opens inside app instead
    // the canvas remounts when the folder changes, so wait on the hash, then re-query
    await waitFor(() => expect(window.location.hash).toContain('arch=app'))
    expect(await screen.findByText('security.py')).toBeTruthy()
    const crumbs = screen.getByRole('navigation', { name: 'Folder path' })
    await waitFor(() => {
      expect(crumbs.textContent).toContain('root')
      expect(crumbs.textContent).toContain('app')
    })
  })

  it('does not re-open the folder after you go back to the root', async () => {
    dominantFolder = true
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })
    fireEvent.click(screen.getByRole('tab', { name: /Architecture/ }))
    await waitFor(() => expect(window.location.hash).toContain('arch=app'))
    await screen.findByText('security.py')

    fireEvent.click(screen.getByRole('button', { name: 'Repository root' }))

    // back at the top level, and it stays there (no second automatic descent)
    expect(await screen.findByText('webhooks')).toBeTruthy()
    await new Promise((r) => setTimeout(r, 300))
    expect(window.location.hash).not.toContain('arch=app')
  })

  it('selecting a folder summarises it', async () => {
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })
    fireEvent.click(screen.getByRole('tab', { name: /Architecture/ }))
    // wait for the (lazy) map itself, not just any text that says "webhooks"
    const map = await screen.findByLabelText('Module dependency map', { selector: '.react-flow' })

    fireEvent.click(await within(map).findByText('webhooks'))

    const inspector = screen.getByRole('complementary', { name: 'Inspector' })
    expect(await within(inspector).findByText('webhooks/')).toBeTruthy()
    expect(within(inspector).getByText(/holds 4 files/)).toBeTruthy()
  })
})

describe('AI-optional behaviour', () => {
  it('says AI is off and points to the Summary tab', async () => {
    llmStatus = 'unreachable'
    renderApp()

    expect(await screen.findByText('AI off')).toBeTruthy()
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Explain' }))
    expect(await screen.findByText(/AI is off, and that is fine/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open Summary' })).toBeTruthy()
  })

  it('shows AI on when a model is reachable', async () => {
    llmStatus = 'ready'
    renderApp()

    expect(await screen.findByText('AI on')).toBeTruthy()
  })

  it('asks a question and renders the answer with a clickable citation', async () => {
    llmStatus = 'ready'
    renderApp()
    await openLoginFlow()

    fireEvent.change(screen.getByLabelText('Ask'), { target: { value: 'How do users log in?' } })
    fireEvent.submit(screen.getByRole('search', { name: 'Ask about this repository' }))

    expect(await screen.findByText(/Login is handled by/)).toBeTruthy()
    const chip = await screen.findByRole('button', { name: 'Source 1: login' })
    const ask = calls.find((c) => c.method === 'POST' && c.url === '/ask')
    expect(JSON.parse(ask!.body!)).toMatchObject({ repo_id: 1, question: 'How do users log in?' })

    fireEvent.click(chip)
    await waitFor(() => expect(window.location.hash).toContain('ch=100'))
    expect(window.location.hash).not.toContain('tab=explain')
    expect(window.location.hash).toContain('start=15')
  })

  it('degrades gracefully when /explain has no LLM', async () => {
    renderApp()
    await openLoginFlow()

    fireEvent.click(screen.getByRole('button', { name: 'Show as outline (text)' }))
    const outline = await screen.findByRole('navigation', { name: 'Call graph outline' })
    fireEvent.click(within(outline).getByText('login'))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Explain' }))

    fireEvent.click(await screen.findByRole('button', { name: /Explain this/ }))

    expect(await screen.findByText(/connection refused/)).toBeTruthy()
    expect(screen.getAllByText(/Enable \/ask/).length).toBeGreaterThan(0)
  })
})

describe('Navigation', () => {
  it('opens the command palette with Ctrl+K and finds an endpoint', async () => {
    renderApp()
    await screen.findByRole('heading', { name: 'shop_api' })

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByPlaceholderText(/Search endpoints, functions, files/)
    fireEvent.change(input, { target: { value: 'orders' } })

    const palette = await screen.findByRole('dialog')
    expect(await within(palette).findByText('/orders')).toBeTruthy()
  })
})
