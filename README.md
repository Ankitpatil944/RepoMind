# RepoMind

**Understand any codebase in minutes, and give your AI assistant a 1,000-token map of it instead of 1,000,000 tokens of source.**

RepoMind indexes a Python, JavaScript or TypeScript project and shows you its architecture,
HTTP endpoints, auth surface and call graph, with every answer pointing at the exact file and
line. It runs locally, needs no API key, and is free.

**Use it to:**

- 🧠 **Give Claude, ChatGPT or Cursor project memory.** Export a token-budgeted, secret-redacted
  summary and save it as `CLAUDE.md`, or paste it into any chat. [Jump to how](#use-it-as-context-for-your-own-llm-and-keep-the-bill-small)
- 🗺️ **Onboard onto an unfamiliar repo.** Treemap, architecture map, "start here" flows.
- 🔐 **Audit the auth surface.** Which routes require authentication, and what is the evidence?
- 🔎 **Search by meaning.** *"where are passwords hashed"* finds `hash_password`, not a grep pile.

```bash
git clone https://github.com/Ankitpatil944/RepoMind.git && cd RepoMind
docker compose up -d --build
docker compose exec api python -m app.cli ingest /samples/shop_api
# then open http://localhost:8000
```

> If RepoMind saves you time, a ⭐ helps other developers find it.

[![CI](https://github.com/Ankitpatil944/RepoMind/actions/workflows/ci.yml/badge.svg)](https://github.com/Ankitpatil944/RepoMind/actions)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![PostgreSQL + pgvector](https://img.shields.io/badge/postgres-pgvector-4169E1)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

![RepoMind overview of the sample project: stats, auth surface and where to start](docs/img/1-overview.png)

<table>
<tr>
<td width="50%"><img src="docs/img/flow-nestjs.png" alt="Call flow for POST /auth/login in a NestJS app"><br><sub>Call flow of a NestJS route, with the code-derived summary (no LLM involved).</sub></td>
<td width="50%"><img src="docs/img/2-architecture.png" alt="Architecture map of folders and their dependencies"><br><sub>Architecture map: folders sized by code, linked by imports.</sub></td>
</tr>
</table>

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
- **Understand a repo without any AI.** Overview, treemap, architecture map, call flow and
  per-function summaries are computed from the code itself, so they work offline with no API
  key. A language model is optional and only adds written explanations.
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
`ingest` command above. **None of this needs an API key or a language model.**

The UI has three views over the same index:

- **Overview**: the repository at a glance. File, line, function, class and endpoint counts,
  language mix, an auth-surface breakdown, a **treemap of every file sized by lines of code**,
  hotspots (most-called, most-complex, largest), auth guard functions, and the third-party
  libraries it depends on. A "Start here" row jumps into the most interesting flows.
- **Architecture**: a dependency map of folders (double-click to drill down to files) built from
  resolved imports. Node size and bars show code volume; arrows show who imports whom.
- **Call flow**: pick an endpoint or function and see what it calls, with each node showing its
  signature, docstring, size, complexity and fan-in/out. Unresolved external calls (for example
  `jwt.decode`) are dashed nodes so authentication evidence is visible. Hover a node to spotlight
  its neighbours, double-click to re-centre, and use *Calls / Callers / Both* and depth to widen
  or narrow it. The list icon shows the same graph as a text outline.

The right-hand **Inspector** has four tabs:

| Tab | What it gives you | Needs a model? |
|---|---|---|
| **Summary** | Plain-language facts about a function, file or folder: signature, docs, complexity, callers, callees, routes handled, imports | No |
| **Source** | The code, with the selected range highlighted | No |
| **Evidence** | Why an endpoint was classified as auth/protected | No |
| **Explain** | A written explanation and answers to questions, with `[n]` citations | Yes |

Press **Ctrl/⌘ K** for the command palette and **/** to focus the ask box. Every view has a
shareable URL (state lives in the address bar). The header shows **AI on / AI off**, so it is
always clear which features are available; with AI off, everything structural still works.

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
| `export <repo> [--detail overview\|map\|source] [--max-tokens N] [--format markdown\|json] [--focus folder] [-o file]` | Token-budgeted context for an LLM |

The same features are available over HTTP (`/ingest`, `/search`, `/ask`,
`/repos/{id}/endpoints`, `/repos/{id}/graph?name=fn`, `/repos/{id}/chunks`); see
<http://localhost:8000/docs>.

## Use it as context for your own LLM (and keep the bill small)

**Quick recipe for Claude Code / Cursor:** generate a map once, commit it as the memory file your
tool already reads.

```bash
docker compose exec api python -m app.cli export my-project --detail map --max-tokens 8000 -o CLAUDE.md
```

Copy `CLAUDE.md` into your project root (Cursor: `.cursorrules`, others: paste into the chat) and
the assistant starts every session knowing the structure, routes and auth rules. Re-run after big
changes.

The embeddings in the database are a **search index**, not something a model can read: an LLM
consumes text tokens, so you cannot hand it vectors. Most of what RepoMind stores is not vectors
at all but structured facts (signatures, docs, routes, call edges, imports). **Export** turns
those facts into compact text with a token budget:

```bash
# CLI (Markdown to a file; add --format json for compact JSON)
docker compose exec api python -m app.cli export my-project --detail map --max-tokens 16000 -o map.md

# one service in full detail instead of a thin slice of everything
docker compose exec api python -m app.cli export my-project --focus services/auth-service -o auth.md
```

or use **Export** in the web UI header, which shows what each level costs before you copy it.

| Level | What's in it | Typical size |
|---|---|---|
| `overview` | Size, stack, architecture, auth surface, guards, hotspots | about 1k tokens |
| `map` (default) | Overview + every route with its auth role + signatures and docs of the most important files | up to your budget |
| `source` | The map, plus code for handlers, hubs and guards | up to your budget |

On a real 88,000-line, 549-file FastAPI monorepo, pasting the source is roughly **1,000,000
tokens**; the overview is **under 1,000**, and a budgeted map fits in 8,000 to 30,000. Files are
ranked (routes first, then how depended-upon they are, then size) and the least important are left
out *with a note saying what was dropped*. Test files are excluded.

### Getting more out of a budget, and staying safe

- **Scope it.** On a big monorepo a whole-repo map is a thin slice of everything. Pick a folder
  (Scope in the dialog, or `--focus services/auth-service`) and that folder gets the full budget:
  its routes, signatures and docs in detail, with caller counts that still look at the whole repo.
- **Secrets are redacted, and counted.** AWS/GitHub/Stripe/Google/Slack keys, JWTs, private keys,
  `password = "..."`-style assignments and passwords inside URLs are replaced with
  `[REDACTED:kind]` before anything is written, and the export tells you how many it removed.
  This is a safety net, not a guarantee: it cannot recognise an arbitrary string that happens to
  be a secret, so skim an export before sending it to a third party.
- **Staleness is reported.** Indexed files are compared with what is on disk now; if any changed
  or disappeared, the export and the dialog say so and tell you to re-run ingest. If the project
  folder isn't mounted, it says it can't check.
- **Routes adapt to the budget.** The detailed route list (with handler names) is used when it
  fits; under pressure it switches to a compact list so more routes survive.

Other notes: token counts are estimates (about 4 characters per token; real tokenizers vary by
model). The export is generated from static analysis, so it contains no model output and is
deterministic. Typographic punctuation and emoji are normalised to plain text so it pastes cleanly
anywhere; text in other languages is kept as UTF-8. For *targeted* questions, pairing the overview
with retrieval (`search`) is cheaper than any large dump.

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
| Parsing | tree-sitter (Python, JavaScript, TypeScript) |
| Embeddings / reranker | [fastembed](https://github.com/qdrant/fastembed) (`bge-small-en-v1.5`, MiniLM cross-encoder), local ONNX, no GPU |
| LLM | any OpenAI-compatible endpoint (optional) |

## What's supported (and what isn't)

| | Supported |
|---|---|
| Languages | Python, JavaScript, TypeScript (`.py .js .jsx .mjs .cjs .ts .tsx .mts .cts`) |
| Route detection | FastAPI / Flask decorators, `APIRouter(prefix=...)`, `Depends(...)`; Express / Koa / Hono `app.get/post/...`, `router.use(...)`, `route('/x').get().post()`; Fastify (`{ preHandler }` options, `route({...})`, `addHook`); NestJS controllers and guards; Django `path()` / `re_path()` and DRF `router.register` |
| Auth signals | decorators and middleware (`login_required`, `@UseGuards`, `preHandler`), DRF `permission_classes`, mixins such as `LoginRequiredMixin`, HMAC/signature middleware |
| Not supported yet | Go, Java/Spring, Ruby, PHP; Django `include('app.urls')` across files and DRF `@action`; routers mounted across files with a prefix; docs/Markdown/config files are not indexed. Django routes that accept any method are reported as `ANY` |

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

The harness indexes five small benchmark apps (FastAPI `shop_api`, NestJS + Express
`notes_nest`, Flask `inventory_flask`, Django + DRF `blog_django`, Fastify + Express
`orders_fastify`), asks 50 labelled questions, and checks retrieval
(hit@k, recall, MRR), endpoint detection and auth classification. Floors live in
`evals/thresholds.json` (per dataset); CI fails if a metric drops below them.

| Benchmark | Config | hit@1 | recall@10 | MRR | endpoint detection (P / R) | auth classification |
|---|---|---|---|---|---|---|
| shop_api | hashing (no model) | 0.69 | 0.88 | 0.79 | 1.00 / 1.00 | 1.00 |
| shop_api | bge-small + reranker | 1.00 | 1.00 | 1.00 | 1.00 / 1.00 | 1.00 |
| notes_nest | hashing (no model) | 0.20 | 0.75 | 0.40 | 1.00 / 1.00 | 1.00 |
| notes_nest | bge-small + reranker | 0.60 | 0.85 | 0.73 | 1.00 / 1.00 | 1.00 |
| inventory_flask | hashing (no model) | 0.70 | 0.70 | 0.70 | 1.00 / 1.00 | 1.00 |
| inventory_flask | bge-small + reranker | 0.70 | 1.00 | 0.81 | 1.00 / 1.00 | 1.00 |
| blog_django | hashing (no model) | 0.62 | 1.00 | 0.73 | 1.00 / 1.00 | 1.00 |
| blog_django | bge-small + reranker | 0.88 | 1.00 | 0.94 | 1.00 / 1.00 | 1.00 |
| orders_fastify | hashing (no model) | 0.33 | 0.83 | 0.51 | 1.00 / 1.00 | 1.00 |
| orders_fastify | bge-small + reranker | 0.50 | 1.00 | 0.64 | 1.00 / 1.00 | 1.00 |

> **Read this honestly:** the benchmarks are small (50 questions, ~190 chunks) and I wrote
> them myself, then fixed the analyzer where they exposed gaps, so the endpoint scores are
> optimistic. The two newer apps are harder for retrieval (hit@1 0.60 to 0.70 with real
> models), which is the more realistic picture. Larger, third-party benchmarks are
> welcome contributions.

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
call graph, incremental re-indexing, evaluation harness with CI gate, CLI, web UI (overview,
architecture map, interactive call graph, static summaries).

Also done: background indexing with live progress in the UI (`POST /ingest/jobs`, `GET /jobs/{id}`), and indexing a public GitHub/GitLab/Bitbucket repo by URL
(`docker compose exec api python -m app.cli ingest https://github.com/owner/repo`, or `POST /ingest {"url": ...}`;
https only, shallow clone, hosts limited by `GIT_HOSTS`).

Also done: three benchmark apps in the eval gate (FastAPI, NestJS + Express, Flask) with
per-dataset floors in `evals/thresholds.json`; TypeScript / TSX parsing, Express routes in TypeScript, and NestJS controllers
(`@Controller`, `@Get`/`@Post`..., class- and method-level `@UseGuards`).

Also done: Fastify, Koa/Hono, Django and Django REST framework route detection.

Planned: Java/Spring and Go, cross-file router prefixes, a benchmark of real third-party repos,
LLM-judged faithfulness, streaming answers.

## Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the checks CI
runs, how to add framework support and benchmarks, and PR conventions. In short: keep changes
focused, add tests, run `pytest` and `ruff check .`, and avoid paid-service dependencies.

## License

[MIT](LICENSE)
