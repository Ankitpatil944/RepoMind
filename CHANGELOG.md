# Changelog

## Unreleased

- Retrieval: keyword search now prefix-matches stemmed terms ("created" finds `issueToken`). With
  `bge-small` and no reranker this lifts MRR from 0.81 to 0.83; with the default reranker the
  benchmarks are unchanged. The hashing smoke floor for blog_django was lowered (hit@1 0.57 to
  0.45) because broader matching hurts the word-hash embedder. Tried and dropped: a function-name
  matcher (hurt real embeddings, MRR 0.83 to 0.77) and indexing endpoint auth facts (no effect).
- `RERANK_MODEL=BAAI/bge-reranker-base` is about 4 points better hit@1 than the default MiniLM
  reranker but ~5x slower per query (1.6 s vs 0.3 s).

- UI redesign to the DESIGN.md spec: sage/terracotta/teal palette, Instrument Serif + Geist type,
  a briefing-style Overview (headline, findings, heat-coloured risk map), call-flow nodes with
  complexity meters and line-number edge chips, an inspector header with Back history, an ask box
  in the header, and a skippable envelope intro (reduced-motion aware).

- More frameworks: Fastify (options, `route({...})`, hooks), Koa/Hono, Express route chains,
  Django `path()`/`re_path()` and Django REST framework (routers, `permission_classes`, mixins).
- Two more benchmark apps (Django + DRF, Fastify + Express) in the eval gate.

## 0.1.0

First public release.

- Ingestion: tree-sitter chunking for Python, JavaScript and TypeScript; incremental re-indexing.
- Retrieval: hybrid vector + full-text search with reciprocal rank fusion and an optional reranker;
  cited answers through any OpenAI-compatible LLM (optional).
- Static analysis: HTTP endpoints (FastAPI, Flask, Express, NestJS), auth classification,
  call graph and module graph.
- Web UI: overview, architecture map, interactive call graph, source preview, code-derived
  summaries that work without an LLM.
- Index a project from a folder or a public Git URL, in the background with live progress.
- LLM-context export: token-budgeted, scoped to a folder, secret redaction, freshness check.
- Evaluation harness with three benchmark apps and a CI regression gate.
- Docker Compose one-command setup, CLI, MIT licence.
