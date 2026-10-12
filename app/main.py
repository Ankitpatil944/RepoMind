import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import db, llm
from app.ask import build_messages, citation
from app.embed import get_embedder
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


class IngestRequest(BaseModel):
    path: str


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
    allowed_root = os.environ.get("REPOS_ROOT")
    if allowed_root and not path.is_relative_to(Path(allowed_root).resolve()):
        raise HTTPException(400, f"path must be inside {allowed_root}")
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


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    path = _resolve_repo_path(req.path)
    with db.connect() as conn:
        return ingest_repo(conn, path)


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
    try:
        answer = llm.chat(build_messages(req.question, hits))
    except llm.LLMError as e:
        return {"answer": None, "sources": sources, "error": str(e)}
    return {"answer": answer, "sources": sources, "error": None}


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
