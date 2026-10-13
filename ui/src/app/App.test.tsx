import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Endpoint, FlowGraph } from '../api/types'
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
    id: 11,
    method: 'GET',
    path: '/orders',
    file: 'app/routes/orders.py',
    line: 14,
    handler: 'list_orders',
    handler_chunk_id: 200,
    requires_auth: true,
    evidence: ["guarded by 'Depends(get_current_user)'"],
  }),
  ep({
    id: 10,
    method: 'POST',
    path: '/auth/login',
    line: 15,
    handler: 'login',
    handler_chunk_id: 100,
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
      id: 'e:10',
      type: 'endpoint',
      label: 'POST /auth/login',
      method: 'POST',
      path: '/auth/login',
      file: 'app/routes/auth.py',
      start_line: 15,
      end_line: 15,
      endpoint_id: 10,
      handles_authentication: true,
      requires_auth: false,
      evidence: ["path '/auth/login' looks like an authentication endpoint", "calls 'verify_password'"],
    },
    { id: 'c:100', type: 'function', label: 'login', name: 'login', file: 'app/routes/auth.py', start_line: 15, end_line: 21, chunk_id: 100 },
    { id: 'c:101', type: 'function', label: 'verify_password', name: 'verify_password', file: 'app/security.py', start_line: 19, end_line: 20, chunk_id: 101, auth_related: true },
    { id: 'x:jwt.encode', type: 'external', label: 'jwt.encode', auth_related: true },
  ],
  edges: [
    { id: 'e:10->c:100', source: 'e:10', target: 'c:100', line: null, kind: 'handles' },
    { id: 'c:100->c:101', source: 'c:100', target: 'c:101', line: 17, kind: 'calls' },
    { id: 'c:100->x:jwt.encode', source: 'c:100', target: 'x:jwt.encode', line: 19, kind: 'calls' },
  ],
}

const FILE = {
  path: 'app/routes/auth.py',
  language: 'python',
  content: 'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/auth")\n\n\n@router.post("/login")\ndef login(email, password):\n    return {"ok": True}\n',
  changed_since_indexed: false,
  symbols: [{ chunk_id: 100, name: 'login', qualified_name: 'login', kind: 'function', start_line: 6, end_line: 8 }],
}

let calls: Array<{ url: string; method: string; body?: string }>

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
  if (p === '/repos') return REPOS
  if (p === '/repos/1/endpoints') return ENDPOINTS
  if (p === '/repos/1/files') {
    return [
      { path: 'app/routes/auth.py', language: 'python', symbols: 5, endpoints: 1 },
      { path: 'app/security.py', language: 'python', symbols: 6, endpoints: 0 },
    ]
  }
  if (p === '/repos/1/graph/flow') return FLOW
  if (p === '/repos/1/files/content') return FILE
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

beforeEach(() => {
  calls = []
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

describe('RepoMind UI', () => {
  it('lists endpoints with auth roles and auto-opens the auth endpoint in the graph', async () => {
    renderApp()

    const explorer = await screen.findByRole('complementary', { name: 'Explorer' })
    expect(await within(explorer).findByText('/auth/login')).toBeTruthy()
    expect(within(explorer).getByText('/orders')).toBeTruthy()

    // The auth endpoint is chosen automatically and drawn as a graph.
    const graph = await screen.findByLabelText('Call graph', { selector: '[class*="react-flow"], .react-flow' })
    expect(graph).toBeTruthy()
    expect(await screen.findByText('verify_password')).toBeTruthy()
    expect(screen.getByText('jwt.encode')).toBeTruthy()

    const flowCall = calls.find((c) => c.url.includes('/graph/flow'))
    expect(flowCall?.url).toContain('endpoint_id=10')
    expect(window.location.hash).toContain('ep=10')
  })

  it('shows the same graph as an accessible text outline', async () => {
    renderApp()
    await screen.findByText('verify_password')

    fireEvent.click(screen.getByRole('button', { name: 'Show as outline (text)' }))

    const outline = await screen.findByRole('navigation', { name: 'Call graph outline' })
    expect(within(outline).getByText('verify_password')).toBeTruthy()
    expect(within(outline).getByText('jwt.encode')).toBeTruthy()
    expect(within(outline).getAllByText('calls').length).toBe(2)
    expect(window.location.hash).toContain('outline=1')
  })

  it('explains why an endpoint was classified, in the Evidence tab', async () => {
    renderApp()
    await screen.findByText('verify_password')

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Evidence' }))

    expect(await screen.findByText("path '/auth/login' looks like an authentication endpoint")).toBeTruthy()
    expect(screen.getByText("calls 'verify_password'")).toBeTruthy()
  })

  it('loads the source of the selected endpoint', async () => {
    renderApp()
    await screen.findByText('verify_password')

    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/files/content') && c.url.includes('app%2Froutes%2Fauth.py'))).toBe(true)
    })
    expect(await screen.findByText('app/routes/auth.py', { selector: 'span' })).toBeTruthy()
  })

  it('asks a question and renders the answer with a clickable citation', async () => {
    renderApp()
    await screen.findByText('verify_password')

    fireEvent.change(screen.getByLabelText('Ask'), { target: { value: 'How do users log in?' } })
    fireEvent.submit(screen.getByRole('search', { name: 'Ask about this repository' }))

    expect(await screen.findByText(/Login is handled by/)).toBeTruthy()
    const chip = await screen.findByRole('button', { name: 'Source 1: login' })
    const ask = calls.find((c) => c.method === 'POST' && c.url === '/ask')
    expect(JSON.parse(ask!.body!)).toMatchObject({ repo_id: 1, question: 'How do users log in?' })

    fireEvent.click(chip)
    await waitFor(() => expect(window.location.hash).toContain('ch=100'))
    // 'source' is the default tab, so it is omitted from the URL; 'explain' must be gone.
    expect(window.location.hash).not.toContain('tab=explain')
    expect(window.location.hash).toContain('start=15')
  })

  it('opens the command palette with Ctrl+K and finds an endpoint', async () => {
    renderApp()
    await screen.findByText('verify_password')

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByPlaceholderText(/Search endpoints, functions, files/)
    fireEvent.change(input, { target: { value: 'orders' } })

    const palette = await screen.findByRole('dialog')
    expect(await within(palette).findByText('/orders')).toBeTruthy()
  })

  it('degrades gracefully when /explain has no LLM', async () => {
    renderApp()
    await screen.findByText('verify_password')

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Explain' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Evidence' }).catch(() => document.body))
    // Select a function node via the outline so it has a chunk to explain.
    fireEvent.click(screen.getByRole('button', { name: 'Show as outline (text)' }))
    const outline = await screen.findByRole('navigation', { name: 'Call graph outline' })
    fireEvent.click(within(outline).getByText('login'))

    fireEvent.click(await screen.findByRole('button', { name: /Explain this/ }))

    expect(await screen.findByText(/connection refused/)).toBeTruthy()
    expect(screen.getByText(/Enable \/ask/)).toBeTruthy()
  })
})
