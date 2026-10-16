# Contributing to RepoMind

Thanks for helping out. Issues and pull requests are welcome, from typo fixes to new
framework support.

## Ground rules

- **Keep changes focused.** One PR, one idea. Unrelated refactors belong in their own PR.
- **Add tests.** Bug fixes need a test that fails without the fix; features need tests for the new behaviour.
- **No paid-service dependencies.** RepoMind runs locally and free. Anything that needs a paid API must be optional.
- **Repository code is never executed.** Indexing only reads and parses files. Do not add code paths that run, import or `eval` indexed code.
- **Be kind.** Assume good intent and keep review comments about the code.

## Ways to contribute

| Idea | Where to look |
|---|---|
| Report a bug | Open an issue with the repo layout (or a minimal snippet), the command you ran, and the output |
| Support a new web framework | `app/ingest/analysis.py`, `evals/repos/`, `evals/datasets/` (see below) |
| Support a new language | `app/ingest/parser.py`, `app/ingest/walker.py` |
| Improve retrieval | `app/retrieval.py`, `app/rerank.py`, `app/embed.py` |
| Improve the UI | `ui/src/` |
| Add a benchmark from a real third-party repo | `evals/` (very welcome, see [Evaluation](#evaluation)) |

Not sure where to start? Check the Roadmap in the README ("Planned" and "Not supported yet").
For anything larger than a small fix, open an issue first so we can agree on the approach.

## Project layout

```text
app/          API, ingestion (parser, analysis), retrieval, graph, export, CLI
app/ingest/   walker (find files) -> parser (chunks) -> analysis (routes, auth, calls) -> service
ui/           web UI (Vite + React + TypeScript + React Flow)
evals/        benchmark apps (repos/), labelled questions (datasets/), metrics, runner, thresholds.json
tests/        unit and integration tests
docs/         screenshots and docs
```

## Development setup

You need Python 3.12, Docker (for Postgres with pgvector), and Node 22 if you touch the UI.

```bash
git clone https://github.com/Ankitpatil944/RepoMind.git
cd RepoMind

python -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

docker compose up -d db                                 # Postgres on 127.0.0.1:5433
export DATABASE_URL=postgresql://repomind:repomind@127.0.0.1:5433/repomind
# PowerShell: $env:DATABASE_URL="postgresql://repomind:repomind@127.0.0.1:5433/repomind"
```

Tests never download models; they use a deterministic fake embedder. If `DATABASE_URL`
is unset, tests that need the database are skipped (CI runs them, so please run them locally too).

### Web UI

```bash
cd ui
npm install
npm run dev        # http://localhost:5173, proxies API calls to 127.0.0.1:8000
```

Run the API alongside it (`docker compose up -d`, or `uvicorn app.main:app --port 8000`).
Design tokens live in `ui/src/design/tokens.css`; a test enforces WCAG contrast for every
text/background pair, so check it still passes if you change colours.

## Before you open a PR

These are the same checks CI runs. All must pass.

```bash
# Backend (from the repo root)
ruff check .
pytest -q
python -m evals.run --embedder hashing        # regression gate, no model download

# Frontend (from ui/)
npm run typecheck
npm test
npm run build
```

Checklist:

- [ ] `ruff check .` is clean (config in `ruff.toml`)
- [ ] New or changed behaviour has tests
- [ ] The eval gate passes; if you touched analysis or retrieval, you ran it
- [ ] README / `CHANGELOG.md` updated under "Unreleased" for user-visible changes
- [ ] No secrets, personal paths or large binaries committed

## Evaluation

The eval harness indexes small benchmark apps in `evals/repos/`, asks the labelled
questions in `evals/datasets/<name>.json`, and checks retrieval (hit@k, recall, MRR),
endpoint detection and auth classification. Floors live in `evals/thresholds.json`, per
dataset, and CI fails if a metric drops below them.

```bash
python -m evals.run --embedder hashing                                  # what CI runs
python -m evals.run --embedder fastembed --reranker fastembed           # real models (downloads ~200 MB)
```

Rules for thresholds:

- **Never lower a floor to make CI pass.** If a metric dropped, find out why. If the drop is
  a real, justified trade-off, explain it in the PR.
- **Raise floors** when you improve a metric, so the gain is locked in.
- Benchmarks here are small and were written by the maintainer, so scores are optimistic.
  Benchmarks from real third-party repos are the most valuable contribution you can make.

### Adding support for a framework

1. Add a small benchmark app under `evals/repos/<name>/` that uses the framework's routing and auth idioms (realistic, but small).
2. Label it in `evals/datasets/<name>.json`: expected endpoints (method, path, handler, auth/protected) and retrieval questions with the files/functions that answer them.
3. Teach `app/ingest/analysis.py` to detect the routes and auth signals.
4. Add focused unit tests (see `tests/test_frameworks.py` for examples) and a fixture in `tests/fixtures/` if needed.
5. Add per-dataset floors to `evals/thresholds.json`.
6. Update the "What's supported" table in the README and the changelog.

Auth detection is heuristic. Prefer precise patterns that record their evidence, and
document known limits rather than guessing.

### Changing analysis output

If your change alters what the analyzer stores, bump `ANALYSIS_VERSION` in `app/db.py`
so existing indexes are refreshed automatically after upgrade.

## Code style

- Python: formatted and linted with Ruff; type hints on public functions; short docstrings that say *why*, not *what*.
- TypeScript: strict mode (`npm run typecheck`); keep components small and tested.
- Match the surrounding code's naming and comment density.
- Static features (overview, call flow, summaries, export) must keep working **without an LLM**. LLM features stay optional.

## Commit and PR conventions

- Commit messages follow the existing history: `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`, `chore: ...`.
- In the PR description, say **what** changed, **why**, and **how you tested it**. Include screenshots for UI changes.
- Keep PRs small enough to review in one sitting. Link the issue it closes.

## Security

RepoMind has no API authentication and is bound to `127.0.0.1` by default. Please don't
open public issues for vulnerabilities (for example path traversal in `/ingest` or secret
leakage in `export`); contact the maintainer privately through the email on their GitHub
profile instead.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
