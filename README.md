# RepoMind

**Ask questions about any codebase and get answers that point to the exact file and line.**

RepoMind indexes a Python or JavaScript project, then lets you ask things like
*"how do users log in?"* or *"which endpoints require authentication?"*. Answers cite
real source locations, and the whole thing runs locally and free.

[![CI](https://github.com/Ankitpatil944/RepoMind/actions/workflows/ci.yml/badge.svg)](https://github.com/Ankitpatil944/RepoMind/actions)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![PostgreSQL + pgvector](https://img.shields.io/badge/postgres-pgvector-4169E1)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Real output from the bundled sample project:

```text
$ python -m app.cli endpoints shop_api
POST    /auth/login                   app/routes/auth.py:15      login           AUTH
POST    /auth/refresh                 app/routes/auth.py:35      refresh         AUTH protected
GET     /orders                       app/routes/orders.py:14    list_orders     protected
GET     /products                     app/routes/products.py:10  list_products
POST    /admin/users/{user_id}/ban    app/routes/admin.py:14     ban_user        protected

$ python -m app.cli search shop_api "where are passwords hashed"
[1] app/security.py:15-17  hash_password (function)
[2] app/security.py:1-53  <module> (module)
[3] app/routes/auth.py:24-32  register (function)
```

`ask` returns the same kind of cited sources plus a written answer once an LLM is configured.

## What makes it different from "chat with your repo"

- **Understands code structure.** Files are split into functions, classes and methods with
  [tree-sitter](https://tree-sitter.github.io/), not arbitrary text windows.
- **Hybrid search.** Vector similarity + keyword search (with `snake_case`/`camelCase`
  splitting), fused with rank fusion and re-ranked by a cross-encoder.
- **Finds your API.** Detects HTTP routes (FastAPI, Flask, Express), their handlers, and
  whether each one *performs* or *requires* authentication, with the evidence.
- **Call graph you can explore.** "Who calls this?" and "what does this call?" as an
  interactive graph, from any endpoint or function, with auth evidence highlighted.
- **Measured, not vibes.** A built-in evaluation harness scores retrieval and endpoint
  detection and can fail CI on regressions.

## Quickstart (5 minutes, Docker only)

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Compose).
No Python install needed.

```bash
git clone https://github.com/Ankitpatil944/RepoMind.git
cd RepoMind
docker compose up -d --build     # first build downloads ~200 MB of models
```

Index the bundled sample project and explore it:

```bash
docker compose exec api python -m app.cli ingest /samples/shop_api
docker compose exec api python -m app.cli endpoints shop_api
docker compose exec api python -m app.cli search shop_api "where are passwords hashed"
```

Everything above works **without any API key or LLM**. Interactive API docs live at
<http://localhost:8000/docs>.

### Open the web UI

Go to **<http://localhost:8000>**. Click **Index project → Index sample project**, or run the
`ingest` command above, then explore:

- **Graph** (centre): pick an endpoint and see what it calls, where authentication happens,
  and which calls leave the repo (dashed nodes). Click a node to select it, double-click to
  re-centre the graph on it, and use *Calls / Callers / Both* and the depth control to widen
  or narrow the view. The list icon switches to a text outline of the same graph.
- **Explorer** (left): endpoints with their auth role, a file tree, and symbol search.
- **Inspector** (right): **Source** with the selected code highlighted, **Explain** for a
  written explanation of the selected function or an answer to your question (with clickable
  `[n]` citations), and **Evidence** for *why* something was classified as auth or protected.
- **Ctrl/⌘ K** opens a command palette; **/** focuses the ask box. Every view has a shareable
  URL (the state lives in the address bar).

The graph, explorer, source and evidence work with no LLM. Written explanations need one
(see below).

### Index your own project

Put (or copy) your project into the `repos/` folder, then ingest it by folder name:

```bash
cp -r ~/code/my-project repos/my-project          # Windows: Copy-Item -Recurse C:\code\my-project repos\my-project
docker compose exec api python -m app.cli ingest my-project
docker compose exec api python -m app.cli ask my-project "How is authentication implemented?"
```

Or point RepoMind at a whole folder of projects by setting `REPOS_DIR=C:/code` in `.env`
(see [Configuration](#configuration)), then ingest `my-project` the same way. Re-running
`ingest` is cheap: only changed files are re-processed.

### Enable `/ask` (LLM answers)

`ask` needs a chat model. Without one it still returns the retrieved sources and tells you
what is missing. Pick one, copy `.env.example` to `.env`, and restart (`docker compose up -d`):

| Option | Cost | Setup |
|---|---|---|
| **Ollama** (default) | free, fully local | Install [Ollama](https://ollama.com), run `ollama pull qwen2.5-coder:7b`. On Linux start it with `OLLAMA_HOST=0.0.0.0`. |
| **Groq** | free tier | Set `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (examples in `.env.example`) |
| **Gemini** | free tier | Same three variables (OpenAI-compatible endpoint) |

Any OpenAI-compatible endpoint works. **Privacy:** with Groq/Gemini the retrieved code
snippets are sent to that provider; with Ollama nothing leaves your machine.

## Commands

All commands run as `docker compose exec api python -m app.cli <command>`. A repo can be
given by name or by id.

| Command | What it does |
|---|---|
| `ingest <folder>` | Index a project (`my-project` → `/repos/my-project`, or a full container path such as `/samples/shop_api`) |
| `repos` | List indexed projects |
| `search <repo> "<query>"` | Ranked code locations, no LLM needed |
| `ask <repo> "<question>"` | Answer with `[n]` citations (needs an LLM) |
| `endpoints <repo> [--auth authentication\|protected\|public]` | HTTP routes with auth classification |

The same features are available over HTTP (`/ingest`, `/search`, `/ask`,
`/repos/{id}/endpoints`, `/repos/{id}/graph?name=fn`, `/repos/{id}/chunks`); see
<http://localhost:8000/docs>.

## How it works

```mermaid
flowchart LR
    A[Source folder] --> B[tree-sitter parse]
    B --> C[Functions / classes / methods]
    B --> D[Routes, imports, call graph]
    C --> E[(Postgres + pgvector)]
    D --> E
    Q[Question] --> F[Vector search]
    Q --> G[Keyword search]
    E --> F
    E --> G
    F --> H[Rank fusion + reranker]
    G --> H
    H --> I[LLM with cited snippets]
    D -. endpoint list .-> I
```

| Part | Technology |
|---|---|
| API | FastAPI |
| Storage + vector + keyword search | PostgreSQL with pgvector and full-text search |
| Parsing | tree-sitter (Python, JavaScript) |
| Embeddings / reranker | [fastembed](https://github.com/qdrant/fastembed) (`bge-small-en-v1.5`, MiniLM cross-encoder), local ONNX, no GPU |
| LLM | any OpenAI-compatible endpoint (optional) |

## What's supported (and what isn't)

| | Supported |
|---|---|
| Languages | Python, JavaScript (`.py .js .jsx .mjs .cjs`) |
| Route detection | FastAPI / Flask decorators, `APIRouter(prefix=...)`, `Depends(...)`, Express `app.get/post/...` and `router.use(...)` |
| Not supported yet | TypeScript, Go, Java, etc.; Django URL confs; routers mounted across files with a prefix; docs/Markdown/config files are not indexed |

**Heuristics, not magic.** Auth classification is based on names and patterns (`login`,
`Depends(get_current_user)`, `jwt.decode`, ...). "No auth detected" means no signal was
found, not proof an endpoint is public. Call-graph links are matched by function name.

## Configuration

Everything is optional. Copy `.env.example` to `.env` to change defaults.

| Variable | Default | Meaning |
|---|---|---|
| `REPOS_DIR` | `./repos` | Host folder mounted read-only at `/repos` |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | OpenAI-compatible chat endpoint (Ollama by default) |
| `LLM_MODEL` | `qwen2.5-coder:7b` | Model name for that endpoint |
| `LLM_API_KEY` | empty | Needed for hosted providers |
| `EMBEDDER` | `fastembed` | `hashing` = no model, for tests only |
| `RERANKER` | `fastembed` | `none` to skip reranking (less RAM, faster) |

## Evaluation

```bash
docker compose exec api python -m evals.run --embedder fastembed --reranker fastembed
```

The harness indexes a benchmark app (`evals/repos/shop_api`), asks 16 labelled questions,
and checks retrieval (hit@k, recall, MRR), endpoint detection and auth classification.
Floors live in `evals/thresholds.json`; CI fails if a metric drops below them.

| shop_api benchmark | hit@1 | recall@10 | MRR | endpoint detection | auth classification |
|---|---|---|---|---|---|
| hashing (no model) | 0.69 | 0.88 | 0.79 | 1.00 / 1.00 | 0.94 |
| bge-small + reranker | 1.00 | 1.00 | 1.00 | 1.00 / 1.00 | 0.94 |

> **Read this honestly:** the benchmark is small (16 questions, 55 chunks), so the real-model
> numbers are saturated. They show the pipeline works, not that retrieval is perfect on
> large repos. Larger, harder datasets are welcome contributions. One endpoint
> (`POST /webhooks/stripe`, protected by an HMAC signature rather than a user token) is
> deliberately a known miss.

## Security notes

- **There is no authentication on the API.** Ports are bound to `127.0.0.1` by default.
  Do not expose it to a network without adding auth and a reverse proxy.
- Indexing only reads files and parses them. **Repository code is never executed.**
- `/ingest` only accepts folders under the mounted roots (`/repos`, `/samples`).
- Indexed code lives in the local Postgres volume. `docker compose down -v` deletes it.
- Source files are treated as untrusted data; only `.py`/`.js` files are read, so `.env`
  and key files are not indexed. Still, check for hardcoded secrets before using a hosted LLM.

## Development

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d db                                 # Postgres on 127.0.0.1:5433
export DATABASE_URL=postgresql://repomind:repomind@127.0.0.1:5433/repomind   # PowerShell: $env:DATABASE_URL="..."
pytest -q          # DB tests are skipped when DATABASE_URL is unset
ruff check .
python -m evals.run --embedder hashing                  # the CI regression gate
```

Web UI (Vite + React + TypeScript + React Flow), in `ui/`:

```bash
cd ui
npm install
npm run dev        # http://localhost:5173, proxies API calls to 127.0.0.1:8000
npm test           # unit + component tests (no browser needed)
npm run typecheck && npm run build
```

`docker compose up --build` builds the UI in a Node stage and serves it from the API at `/`,
so users never need Node. Design tokens live in `ui/src/design/tokens.css`; a test enforces
WCAG contrast for every text/background pair.

Tests never download models: they use a deterministic fake embedder. Project layout:

```text
app/        API, ingestion (parser, analysis), retrieval, graph, CLI
ui/         web UI (React Flow graph, explorer, source, explain)
evals/      benchmark app, golden dataset, metrics, runner, thresholds
tests/      unit and integration tests
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| `ask` says "No answer: LLM request failed" | No LLM configured; see [Enable `/ask`](#enable-ask-llm-answers). `search` and `endpoints` work without one. |
| `path must be inside one of: /repos, /samples` | Copy the project into `repos/` (or set `REPOS_DIR`) and use the folder name. |
| `Cannot reach RepoMind` | Run `docker compose up -d` and check `docker compose ps`. |
| Port 8000 or 5433 already in use | Change the left side of the port mapping in `docker-compose.yml`. |
| First request is slow after a build with no network | Models download on first use (~200 MB), then are cached in a volume. |
| UI shows "Source unavailable" | The preview reads files from the mounted project folder. Check it is still under `repos/` (or `REPOS_DIR`), and re-run ingest if the path moved. |
| UI shows "changed since indexed" | The file was edited after indexing, so highlighted lines may be off. Re-run ingest. |
| Graph looks sparse or has odd links | Call edges are matched by function name, so some are missing or ambiguous. Dashed nodes are calls resolved outside the repo. |
| Upgraded and endpoints look stale | Re-run ingest (or **Index project** in the UI); analysis results are refreshed automatically after an upgrade. |

## Roadmap

Done: ingestion, hybrid retrieval + reranking, cited answers, endpoint/auth detection,
call graph, incremental re-indexing, evaluation harness with CI gate, CLI, web UI with an
interactive call graph.

Planned: module-level (import) graph view, TypeScript and more frameworks, cross-file router
prefixes, indexing Git URLs directly, larger benchmark, background indexing jobs,
LLM-judged faithfulness, streaming answers.

## Contributing

Issues and PRs are welcome. Please keep changes focused, add tests, run `pytest` and
`ruff check .`, and avoid adding paid-service dependencies.

## License

[MIT](LICENSE)
