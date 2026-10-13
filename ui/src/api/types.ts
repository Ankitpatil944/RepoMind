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
  method?: string
  path?: string
  handles_authentication?: boolean
  requires_auth?: boolean
  evidence?: string[]
  auth_related?: boolean
  hidden_calls?: number
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
