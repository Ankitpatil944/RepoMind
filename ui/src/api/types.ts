// Mirrors the FastAPI responses (see app/main.py, app/api_ui.py, app/graph.py).

export interface Repo {
  id: number
  name: string
  path: string
  indexed_at: string | null
  files: number
  chunks: number
}

export interface FileEntry {
  path: string
  language: string
  symbols: number
  endpoints: number
  loc: number
  complexity: number
}

export interface SymbolInfo {
  chunk_id: number
  name: string
  qualified_name: string
  kind: 'function' | 'method' | 'class'
  start_line: number
  end_line: number
}

export interface SymbolHit extends SymbolInfo {
  file: string
}

export interface FileContent {
  path: string
  language: string
  content: string
  changed_since_indexed: boolean
  symbols: SymbolInfo[]
}

export interface Endpoint {
  id: number
  method: string
  path: string
  framework: string
  file: string
  line: number
  handler: string | null
  handler_chunk_id: number | null
  handles_authentication: boolean
  requires_auth: boolean
  evidence: string[]
}

export type FlowNodeType = 'endpoint' | 'function' | 'method' | 'class' | 'external'

export interface FlowNode {
  id: string
  type: FlowNodeType
  label: string
  name?: string
  file?: string
  start_line?: number
  end_line?: number
  chunk_id?: number
  endpoint_id?: number
  handler_chunk_id?: number | null
  method?: string
  path?: string
  handles_authentication?: boolean
  requires_auth?: boolean
  evidence?: string[]
  auth_related?: boolean
  hidden_calls?: number
  signature?: string
  doc?: string
  complexity?: number
  loc?: number
  fan_in?: number
  fan_out?: number
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  line: number | null
  kind: 'calls' | 'handles'
}

export interface FlowGraph {
  root: string
  nodes: FlowNode[]
  edges: FlowEdge[]
  truncated: boolean
  depth: number
  direction: Direction
}

export type Direction = 'down' | 'up' | 'both'

export interface Source {
  ref: number
  chunk_id?: number
  file: string
  start_line: number
  end_line: number
  kind: string
  name: string
  score?: number
  matched_by?: string[]
}

export interface AskResponse {
  answer: string | null
  error: string | null
  sources: Source[]
  endpoints?: Endpoint[]
}

export interface ExplainResponse extends AskResponse {
  callers: string[]
}

export interface IngestResult {
  repo_id: number
  files_indexed: number
  files_unchanged: number
  files_removed: number
  chunks: number
}

export interface HotFunction {
  chunk_id: number
  name: string
  file: string
  line: number
  complexity: number
  loc: number
  doc: string
  fan_in?: number
  label?: string
}

export interface Overview {
  totals: {
    files: number
    loc: number
    functions: number
    classes: number
    endpoints: number
    internal_links: number
  }
  languages: Array<{ language: string; files: number; loc: number }>
  auth: { authentication: number; protected: number; public: number }
  hotspots: {
    most_called: HotFunction[]
    most_complex: HotFunction[]
    largest_files: Array<{ path: string; loc: number; language: string }>
  }
  guards: HotFunction[]
  dependencies: {
    third_party: Array<{ name: string; files: number }>
    stdlib: Array<{ name: string; files: number }>
  }
  frameworks: string[]
}

export interface ModuleNode {
  id: string
  kind: 'dir' | 'file'
  label: string
  path: string
  files: number
  loc: number
  endpoints: number
  complexity: number
  symbols: number
  languages: string[]
  degree: number
}

export interface ModuleEdge {
  id: string
  source: string
  target: string
  weight: number
}

export interface ModuleGraph {
  root: string
  level: 'dir' | 'file'
  nodes: ModuleNode[]
  edges: ModuleEdge[]
  truncated: boolean
  breadcrumb: string[]
}

export interface ChunkRef {
  chunk_id: number
  name: string
  file: string
  line: number
}

export interface ChunkFacts {
  chunk_id: number
  name: string
  qualified_name: string
  kind: string
  file: string
  language: string
  start_line: number
  end_line: number
  signature: string
  doc: string
  complexity: number
  complexity_label: 'low' | 'moderate' | 'high' | null
  loc: number
  callees_internal: ChunkRef[]
  callees_external: string[]
  callers: ChunkRef[]
  endpoints: Array<{
    id: number
    method: string
    path: string
    handles_authentication: boolean
    requires_auth: boolean
    evidence: string[]
  }>
  summary: string[]
}

export interface FileInfo {
  path: string
  language: string
  loc: number
  doc: string
  symbols: Array<{
    chunk_id: number
    kind: string
    name: string
    start_line: number
    end_line: number
    signature: string
    doc: string
    complexity: number
    loc: number
    fan_in: number
  }>
  imports: { internal: string[]; third_party: string[]; stdlib: string[] }
  imported_by: string[]
  endpoints: Array<{ method: string; path: string; line: number }>
}

export interface Capabilities {
  llm: { status: 'ready' | 'unreachable' | 'error'; base_url: string; model: string }
  embedder: string
  reranker: string
}
