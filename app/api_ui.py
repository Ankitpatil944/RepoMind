"""Additive endpoints that power the web UI (explorer, source preview,
symbol search, call-flow graph, per-node explanation)."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, llm
from app.ask import build_explain_messages, citation
from app.graph import FlowTargetNotFound, call_flow, list_endpoints
from app.ingest.walker import MAX_FILE_BYTES
from app.retrieval import Hit

router = APIRouter()


def _require_repo(conn, repo_id: int) -> str:
    row = conn.execute("SELECT path FROM repos WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"repo {repo_id} not found")
    return row[0]


@router.get("/repos/{repo_id}/files")
def list_files(repo_id: int) -> list[dict]:
    with db.connect() as conn:
        _require_repo(conn, repo_id)
        rows = conn.execute(
            """
            SELECT f.path, f.language,
                   (SELECT count(*) FROM chunks c WHERE c.file_id = f.id AND c.kind <> 'module'),
                   (SELECT count(*) FROM endpoints e WHERE e.file_id = f.id)
            FROM files f WHERE f.repo_id = %s ORDER BY f.path
            """,
            (repo_id,),
        ).fetchall()
    return [
        {"path": p, "language": lang, "symbols": symbols, "endpoints": eps}
        for p, lang, symbols, eps in rows
    ]


@router.get("/repos/{repo_id}/files/content")
def file_content(repo_id: int, path: str) -> dict:
    """Source of an *indexed* file, with its symbol ranges.

    Only paths present in the index are served, and the resolved location must
    stay inside the repo folder, so this cannot read arbitrary files."""
    with db.connect() as conn:
        repo_path = _require_repo(conn, repo_id)
        row = conn.execute(
            "SELECT id, language, sha256 FROM files WHERE repo_id = %s AND path = %s",
            (repo_id, path),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"file not indexed: {path}")
        file_id, language, indexed_sha = row
        symbols = conn.execute(
            """
            SELECT id, name, qualified_name, kind, start_line, end_line
            FROM chunks WHERE file_id = %s AND kind <> 'module' ORDER BY start_line
            """,
            (file_id,),
        ).fetchall()

    root = Path(repo_path).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(400, "path escapes the repository")
    if not target.is_file():
        raise HTTPException(
            404, "source not available on disk (repo folder moved or not mounted)"
        )
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(413, "file too large to preview")

    data = target.read_bytes()
    return {
        "path": path,
        "language": language,
        "content": data.decode("utf-8", errors="replace"),
        "changed_since_indexed": hashlib.sha256(data).hexdigest() != indexed_sha,
        "symbols": [
            {
                "chunk_id": cid,
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "start_line": start,
                "end_line": end,
            }
            for cid, name, qualified, kind, start, end in symbols
        ],
    }


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/repos/{repo_id}/symbols")
def search_symbols(repo_id: int, q: str = "", kind: str | None = None, limit: int = 30) -> list[dict]:
    """Functions / methods / classes by name; exact > prefix > substring."""
    limit = max(1, min(limit, 100))
    like = _like(q.strip())
    with db.connect() as conn:
        _require_repo(conn, repo_id)
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.qualified_name, c.kind, f.path, c.start_line, c.end_line,
                   CASE WHEN lower(c.name) = lower(%(q)s) THEN 0
                        WHEN c.name ILIKE %(prefix)s THEN 1 ELSE 2 END AS rank
            FROM chunks c JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %(repo)s
              AND c.kind IN ('function', 'method', 'class')
              AND (%(kind)s::text IS NULL OR c.kind = %(kind)s)
              AND (%(q)s = '' OR c.name ILIKE %(sub)s OR c.qualified_name ILIKE %(sub)s)
            ORDER BY rank, length(c.qualified_name), f.path, c.start_line
            LIMIT %(limit)s
            """,
            {
                "q": q.strip(),
                "prefix": f"{like}%",
                "sub": f"%{like}%",
                "repo": repo_id,
                "kind": kind,
                "limit": limit,
            },
        ).fetchall()
    return [
        {
            "chunk_id": cid,
            "name": name,
            "qualified_name": qualified,
            "kind": k,
            "file": path,
            "start_line": start,
            "end_line": end,
        }
        for cid, name, qualified, k, path, start, end, _ in rows
    ]


@router.get("/repos/{repo_id}/graph/flow")
def graph_flow(
    repo_id: int,
    endpoint_id: int | None = None,
    chunk_id: int | None = None,
    depth: int = 3,
    direction: str = "down",
) -> dict:
    """Focused call graph (nodes + edges) around an endpoint or a function."""
    if direction not in ("down", "up", "both"):
        raise HTTPException(400, "direction must be down, up or both")
    if (endpoint_id is None) == (chunk_id is None):
        raise HTTPException(400, "pass exactly one of endpoint_id or chunk_id")
    with db.connect() as conn:
        _require_repo(conn, repo_id)
        try:
            return call_flow(
                conn, repo_id, endpoint_id=endpoint_id, chunk_id=chunk_id,
                depth=depth, direction=direction,
            )
        except FlowTargetNotFound as e:
            raise HTTPException(404, str(e)) from e


class ExplainRequest(BaseModel):
    repo_id: int
    chunk_id: int


@router.post("/explain")
def explain(req: ExplainRequest) -> dict:
    """Explain one function/class using its callees, callers and endpoint role.

    Same contract as /ask: when the LLM is unreachable, `answer` is null,
    `error` says why, and the grounding `sources` are still returned."""
    with db.connect() as conn:
        _require_repo(conn, req.repo_id)
        row = conn.execute(
            """
            SELECT c.id, f.path, c.kind, c.qualified_name, c.start_line, c.end_line, c.content
            FROM chunks c JOIN files f ON f.id = c.file_id
            WHERE c.id = %s AND c.repo_id = %s
            """,
            (req.chunk_id, req.repo_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"chunk {req.chunk_id} not found")
        target = Hit(row[0], row[1], row[2], row[3], row[4], row[5], row[6])

        callee_rows = conn.execute(
            """
            SELECT DISTINCT ON (cc.id) cc.id, f.path, cc.kind, cc.qualified_name,
                   cc.start_line, cc.end_line, cc.content
            FROM call_edges ce
            JOIN chunks cc ON cc.id = ce.callee_chunk_id
            JOIN files f ON f.id = cc.file_id
            WHERE ce.caller_chunk_id = %s AND cc.id <> %s
            ORDER BY cc.id
            LIMIT 4
            """,
            (req.chunk_id, req.chunk_id),
        ).fetchall()
        callees = [Hit(r[0], r[1], r[2], r[3], r[4], r[5], r[6][:1200]) for r in callee_rows]

        caller_rows = conn.execute(
            """
            SELECT DISTINCT f.path, c.qualified_name
            FROM call_edges ce
            JOIN chunks c ON c.id = ce.caller_chunk_id
            JOIN files f ON f.id = c.file_id
            WHERE ce.callee_chunk_id = %s AND c.id <> %s
            ORDER BY f.path, c.qualified_name
            LIMIT 6
            """,
            (req.chunk_id, req.chunk_id),
        ).fetchall()
        callers = [f"{name} ({path})" for path, name in caller_rows]
        endpoints = [
            e for e in list_endpoints(conn, req.repo_id) if e["handler_chunk_id"] == req.chunk_id
        ]

    sources = [citation(i, h) for i, h in enumerate([target, *callees], start=1)]
    try:
        answer = llm.chat(build_explain_messages(target, callees, callers, endpoints))
    except llm.LLMError as e:
        return {"answer": None, "error": str(e), "sources": sources,
                "callers": callers, "endpoints": endpoints}
    return {"answer": answer, "error": None, "sources": sources,
            "callers": callers, "endpoints": endpoints}
