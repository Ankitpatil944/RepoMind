# Changelog

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
