import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import db
from app.ingest.service import ingest_repo


@asynccontextmanager
async def lifespan(_: FastAPI):
    if db.database_url():
        with db.connect() as conn:
            db.init_schema(conn)
    yield


app = FastAPI(title="RepoMind", lifespan=lifespan)


class IngestRequest(BaseModel):
    path: str


def _resolve_repo_path(raw: str) -> Path:
    path = Path(raw).resolve()
    allowed_root = os.environ.get("REPOS_ROOT")
    if allowed_root and not path.is_relative_to(Path(allowed_root).resolve()):
        raise HTTPException(400, f"path must be inside {allowed_root}")
    if not path.is_dir():
        raise HTTPException(404, f"directory not found: {raw}")
    return path


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    path = _resolve_repo_path(req.path)
    with db.connect() as conn:
        return ingest_repo(conn, path)


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
