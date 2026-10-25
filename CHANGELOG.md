# Changelog

## Unreleased

- Call graph: when several files define the same name (every service in a monorepo has its own
  `get_db`), a call now resolves to the definition nearest the caller in the folder tree instead of
  whichever was indexed first. On a 9-service repo this moved 227 cross-service links back to the
  right service. Re-run ingest to relink an existing index.
- Function summaries report the true number of callers ("called from 193 places") instead of the
  first 24 shown in the list.
- Overview on large repos: the risk map groups by the folder level that actually splits the code
  (each service in a monorepo instead of one `services/` tile), the exposure finding skips health and
  docs routes and prefers an unguarded write, and the page no longer overflows on phones.

- Retrieval: keyword search now prefix-matches stemmed terms ("created" finds `issueToken`). With
  `bge-small` and no reranker this lifts MRR from 0.81 to 0.83; with the default reranker the
  benchmarks are unchanged. The hashing smoke floor for blog_django was lowered (hit@1 0.57 to
  0.45) because broader matching hurts the word-hash embedder. Tried and dropped: a function-name
  matcher (hurt real embeddings, MRR 0.83 to 0.77) and indexing endpoint auth facts (no effect).
- Retrieval: keyword matches are ranked by term rarity (BM25-style IDF), and the keyword list gets
  half weight in rank fusion. On a real 4,110-chunk repo the old Postgres ranking made hybrid search
  worse than vector alone (hit@1 0.40 vs 0.61); with IDF hybrid reaches 0.59 hit@1 and 0.93 hit@10.
  The hashing smoke floor for orders_fastify was lowered (hit@3 0.62 to 0.45).
- Rerankers re-measured on that repo: none beat plain hybrid search at hit@1; MiniLM lifts hit@10
  from 0.93 to 0.97. `bge-reranker-base` scored worse (hit@1 0.53) at ~4 s per query, so it is not
  recommended.

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
