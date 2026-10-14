import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  AskResponse,
  Capabilities,
  ChunkFacts,
  Direction,
  Endpoint,
  ExplainResponse,
  ExportDetail,
  ExportEstimate,
  ExportFormat,
  ExportResult,
  FileContent,
  FileEntry,
  FileInfo,
  FlowGraph,
  IngestResult,
  ModuleGraph,
  Overview,
  Repo,
  SymbolHit,
} from './types'

const STALE = 30_000

export function useRepos() {
  return useQuery({ queryKey: ['repos'], queryFn: ({ signal }) => api.get<Repo[]>('/repos', undefined, signal), staleTime: STALE })
}

export function useFiles(repo: number | null) {
  return useQuery({
    queryKey: ['files', repo],
    queryFn: ({ signal }) => api.get<FileEntry[]>(`/repos/${repo}/files`, undefined, signal),
    enabled: repo !== null,
    staleTime: STALE,
  })
}

export function useEndpoints(repo: number | null) {
  return useQuery({
    queryKey: ['endpoints', repo],
    queryFn: ({ signal }) => api.get<Endpoint[]>(`/repos/${repo}/endpoints`, undefined, signal),
    enabled: repo !== null,
    staleTime: STALE,
  })
}

export function useSymbols(repo: number | null, q: string, enabled = true) {
  return useQuery({
    queryKey: ['symbols', repo, q],
    queryFn: ({ signal }) =>
      api.get<SymbolHit[]>(`/repos/${repo}/symbols`, { q, limit: 40 }, signal),
    enabled: repo !== null && enabled,
    staleTime: STALE,
    placeholderData: (prev) => prev,
  })
}

export function useFileContent(repo: number | null, path: string | null) {
  return useQuery({
    queryKey: ['file', repo, path],
    queryFn: ({ signal }) =>
      api.get<FileContent>(`/repos/${repo}/files/content`, { path }, signal),
    enabled: repo !== null && path !== null,
    staleTime: STALE,
    retry: false,
  })
}

export interface FlowFocus {
  endpointId: number | null
  chunkId: number | null
}

export function useFlow(repo: number | null, focus: FlowFocus, depth: number, direction: Direction) {
  const has = focus.endpointId !== null || focus.chunkId !== null
  return useQuery({
    queryKey: ['flow', repo, focus.endpointId, focus.chunkId, depth, direction],
    queryFn: ({ signal }) =>
      api.get<FlowGraph>(
        `/repos/${repo}/graph/flow`,
        {
          endpoint_id: focus.endpointId,
          chunk_id: focus.endpointId === null ? focus.chunkId : null,
          depth,
          direction,
        },
        signal,
      ),
    enabled: repo !== null && has,
    staleTime: STALE,
    retry: false,
    placeholderData: (prev) => prev,
  })
}

export function useAsk() {
  return useMutation({
    mutationFn: (v: { repo: number; question: string }) =>
      api.post<AskResponse>('/ask', { repo_id: v.repo, question: v.question, top_k: 6 }),
  })
}

export function useExplain() {
  return useMutation({
    mutationFn: (v: { repo: number; chunkId: number }) =>
      api.post<ExplainResponse>('/explain', { repo_id: v.repo, chunk_id: v.chunkId }),
  })
}

export function useIngest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.post<IngestResult>('/ingest', { path }),
    onSuccess: () => {
      void qc.invalidateQueries()
    },
  })
}

export function useOverview(repo: number | null) {
  return useQuery({
    queryKey: ['overview', repo],
    queryFn: ({ signal }) => api.get<Overview>(`/repos/${repo}/overview`, undefined, signal),
    enabled: repo !== null,
    staleTime: STALE,
  })
}

export function useModules(repo: number | null, root: string, level: 'dir' | 'file') {
  return useQuery({
    queryKey: ['modules', repo, root, level],
    queryFn: ({ signal }) =>
      api.get<ModuleGraph>(`/repos/${repo}/graph/modules`, { root, level }, signal),
    enabled: repo !== null,
    staleTime: STALE,
    placeholderData: (prev) => prev,
  })
}

export function useFacts(repo: number | null, chunkId: number | null) {
  return useQuery({
    queryKey: ['facts', repo, chunkId],
    queryFn: ({ signal }) =>
      api.get<ChunkFacts>(`/repos/${repo}/chunks/${chunkId}/facts`, undefined, signal),
    enabled: repo !== null && chunkId !== null,
    staleTime: STALE,
    retry: false,
  })
}

export function useFileInfo(repo: number | null, path: string | null) {
  return useQuery({
    queryKey: ['fileinfo', repo, path],
    queryFn: ({ signal }) => api.get<FileInfo>(`/repos/${repo}/files/info`, { path }, signal),
    enabled: repo !== null && path !== null,
    staleTime: STALE,
    retry: false,
  })
}

export function useCapabilities() {
  return useQuery({
    queryKey: ['capabilities'],
    queryFn: ({ signal }) => api.get<Capabilities>('/capabilities', undefined, signal),
    staleTime: 60_000,
    retry: false,
  })
}

export function useExportEstimate(repo: number | null, focus = '') {
  return useQuery({
    queryKey: ['export-estimate', repo, focus],
    queryFn: ({ signal }) =>
      api.get<ExportEstimate>(`/repos/${repo}/export/estimate`, { focus }, signal),
    placeholderData: (prev) => prev,
    enabled: repo !== null,
    staleTime: 60_000,
    retry: false,
  })
}

export function useExport(
  repo: number | null,
  opts: { detail: ExportDetail; maxTokens: number; format: ExportFormat; focus: string },
) {
  return useQuery({
    queryKey: ['export', repo, opts.detail, opts.maxTokens, opts.format, opts.focus],
    queryFn: ({ signal }) =>
      api.get<ExportResult>(
        `/repos/${repo}/export`,
        { detail: opts.detail, max_tokens: opts.maxTokens, format: opts.format, focus: opts.focus },
        signal,
      ),
    enabled: repo !== null,
    staleTime: 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  })
}
