import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, gitclone, jobs, llm
from app.api_ui import router as ui_router
from app.ask import build_messages, citation, is_endpoint_question
from app.embed import get_embedder
from app.graph import function_graph, list_endpoints
from app.ingest.service import ingest_repo
from app.rerank import get_reranker
from app.retrieval import hybrid_search


@asynccontextmanager
async def lifespan(_: FastAPI):
    if db.database_url():
        with db.connect() as conn:
            db.init_schema(conn)
    yield


app = FastAPI(title="RepoMind", lifespan=lifespan)
app.include_router(ui_router)


class IngestRequest(BaseModel):
    path: str | None = None
    url: str | None = None  # public https Git URL; cloned shallowly, then indexed


class SearchRequest(BaseModel):
    repo_id: int
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=20)


class AskRequest(BaseModel):
    repo_id: int
    question: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=20)


def _resolve_repo_path(raw: str) -> Path:
    path = Path(raw).resolve()
    # REPOS_ROOT may hold several allowed roots separated by os.pathsep.
    allowed = [r for r in os.environ.get("REPOS_ROOT", "").split(os.pathsep) if r]
    if allowed and not any(path.is_relative_to(Path(r).resolve()) for r in allowed):
        raise HTTPException(400, f"path must be inside one of: {', '.join(allowed)}")
    if not path.is_dir():
        raise HTTPException(404, f"directory not found: {raw}")
    return path


def _search(repo_id: int, query: str, top_k: int):
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM repos WHERE id = %s", (repo_id,)).fetchone() is None:
            raise HTTPException(404, f"repo {repo_id} not found")
        return hybrid_search(conn, repo_id, query, get_embedder(), get_reranker(), top_k)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _check_ingest_request(req: IngestRequest) -> None:
    """Cheap, synchronous validation shared by /ingest and /ingest/jobs."""
    if bool(req.path) == bool(req.url):
        raise HTTPException(422, "send exactly one of 'path' or 'url'")
    try:
        if req.url:
            gitclone.parse_git_url(req.url)
        else:
            _resolve_repo_path(req.path or "")
    except gitclone.GitError as e:
        raise HTTPException(400, str(e)) from e


def _run_ingest(req: IngestRequest, progress=None) -> dict:
    if req.url:
        if progress:
            progress("cloning", 0, 0)
        try:
            path = gitclone.fetch(req.url)
        except gitclone.GitError as e:
            raise HTTPException(400, str(e)) from e
    else:
        path = _resolve_repo_path(req.path or "")
    with db.connect() as conn:
        return ingest_repo(conn, path, progress=progress)


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    """Index and wait for the result. Use /ingest/jobs for large projects."""
    _check_ingest_request(req)
    return _run_ingest(req)


@app.post("/ingest/jobs", status_code=202)
def start_ingest_job(req: IngestRequest) -> dict:
    """Start indexing in the background; poll GET /jobs/{id} for progress."""
    _check_ingest_request(req)
    job = jobs.submit(req.url or req.path or "", lambda progress: _run_ingest(req, progress))
    return job.view()


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found (jobs are forgotten on restart)")
    return job.view()


@app.post("/search")
def search(req: SearchRequest) -> list[dict]:
    """Retrieval only (no LLM): ranked chunks with file:line locations."""
    hits = _search(req.repo_id, req.query, req.top_k)
    return [{**citation(i, h), "content": h.content} for i, h in enumerate(hits, start=1)]


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    """Answer a question about a repo with citations.

    Always returns the retrieved `sources`; if the LLM is unreachable,
    `answer` is null and `error` explains why (retrieval still worked)."""
    hits = _search(req.repo_id, req.question, req.top_k)
    sources = [citation(i, h) for i, h in enumerate(hits, start=1)]
    if not hits:
        return {"answer": "No indexed code matched this question.", "sources": [], "error": None}

    endpoints = None
    if is_endpoint_question(req.question):
        with db.connect() as conn:
            endpoints = list_endpoints(conn, req.repo_id) or None

    try:
        answer = llm.chat(build_messages(req.question, hits, endpoints))
    except llm.LLMError as e:
        return {"answer": None, "sources": sources, "endpoints": endpoints or [], "error": str(e)}
    return {"answer": answer, "sources": sources, "endpoints": endpoints or [], "error": None}


@app.get("/repos/{repo_id}/endpoints")
def repo_endpoints(repo_id: int, auth: str | None = None) -> list[dict]:
    """HTTP endpoints found by static analysis, with auth classification.

    auth=authentication  -> endpoints that perform login/token/etc.
    auth=protected       -> endpoints guarded by auth middleware/decorators
    auth=public          -> endpoints with no auth signal"""
    if auth not in (None, "authentication", "protected", "public"):
        raise HTTPException(400, "auth must be authentication, protected or public")
    with db.connect() as conn:
        found = list_endpoints(conn, repo_id)
    if auth == "authentication":
        return [e for e in found if e["handles_authentication"]]
    if auth == "protected":
        return [e for e in found if e["requires_auth"]]
    if auth == "public":
        return [e for e in found if not e["handles_authentication"] and not e["requires_auth"]]
    return found


@app.get("/repos/{repo_id}/graph")
def graph(repo_id: int, name: str) -> dict:
    """Where a function is defined, what it calls, and who calls it (by name)."""
    with db.connect() as conn:
        return function_graph(conn, repo_id, name)


@app.get("/repos")
def list_repos() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.name, r.path, r.indexed_at,
                   (SELECT count(*) FROM files f WHERE f.repo_id = r.id),
                   (SELECT count(*) FROM chunks c WHERE c.repo_id = r.id)
            FROM repos r ORDER BY r.id
            """
        ).fetchall()
    return [
        {"id": i, "name": n, "path": p, "indexed_at": t, "files": f, "chunks": c}
        for i, n, p, t, f, c in rows
    ]


@app.get("/repos/{repo_id}/chunks")
def list_chunks(repo_id: int, kind: str | None = None, limit: int = 50) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT f.path, c.kind, c.qualified_name, c.start_line, c.end_line, c.content
            FROM chunks c JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s AND (%s::text IS NULL OR c.kind = %s)
            ORDER BY f.path, c.start_line
            LIMIT %s
            """,
            (repo_id, kind, kind, min(limit, 500)),
        ).fetchall()
    return [
        {
            "file": p,
            "kind": k,
            "name": q,
            "start_line": s,
            "end_line": e,
            "content": content,
        }
        for p, k, q, s, e, content in rows
    ]


# Web UI (built into the Docker image, or by `npm run build` in ui/). Mounted
# last so every API route above takes precedence.
_UI_DIST = Path(os.environ.get("UI_DIST", Path(__file__).resolve().parent.parent / "ui" / "dist"))
if (_UI_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")
