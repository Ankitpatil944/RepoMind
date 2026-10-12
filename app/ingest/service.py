import hashlib
from pathlib import Path

import psycopg

from app.embed import Embedder, get_embedder, to_pgvector
from app.ingest.analysis import analyze_source
from app.ingest.parser import parse_source
from app.ingest.walker import iter_source_files
from app.text import embedding_text, search_text

EMBED_BATCH = 64


def embed_pending(conn: psycopg.Connection, repo_id: int, embedder: Embedder) -> int:
    """Embed every chunk of the repo that has no embedding yet (new files, and
    chunks stored before embeddings existed). Returns how many were embedded."""
    rows = conn.execute(
        """
        SELECT c.id, f.path, c.kind, c.qualified_name, c.content
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.embedding IS NULL
        ORDER BY c.id
        """,
        (repo_id,),
    ).fetchall()

    for start in range(0, len(rows), EMBED_BATCH):
        batch = rows[start : start + EMBED_BATCH]
        vectors = embedder.embed_documents(
            [embedding_text(path, kind, qname, content) for _, path, kind, qname, content in batch]
        )
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE chunks SET embedding = %s::vector, search_text = %s WHERE id = %s",
                [
                    (to_pgvector(vec), search_text(path, qname, content), chunk_id)
                    for vec, (chunk_id, path, _kind, qname, content) in zip(vectors, batch)
                ],
            )
    return len(rows)


def _store_analysis(
    conn: psycopg.Connection, repo_id: int, file_id: int, data: bytes, language: str
) -> None:
    """Imports, call edges and endpoints for one file (replaces earlier rows)."""
    chunk_rows = conn.execute(
        "SELECT id, start_line, end_line FROM chunks WHERE file_id = %s", (file_id,)
    ).fetchall()

    def owner(line: int) -> int | None:
        """Innermost chunk containing the line (smallest line span wins)."""
        best = None
        for chunk_id, start, end in chunk_rows:
            if start <= line <= end and (best is None or end - start < best[0]):
                best = (end - start, chunk_id)
        return best[1] if best else None

    result = analyze_source(data, language)

    for table in ("call_edges", "endpoints", "file_imports"):
        conn.execute(f"DELETE FROM {table} WHERE file_id = %s", (file_id,))  # noqa: S608

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO file_imports (file_id, repo_id, module) VALUES (%s, %s, %s)",
            [(file_id, repo_id, m) for m in result.imports],
        )
        edges = {
            (owner(c.line), c.callee_name, c.callee_full, c.line) for c in result.calls
        }
        cur.executemany(
            """
            INSERT INTO call_edges
                (repo_id, file_id, caller_chunk_id, callee_name, callee_full, line)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (repo_id, file_id, caller, name, full, line)
                for caller, name, full, line in sorted(edges, key=lambda e: e[3])
                if caller is not None
            ],
        )
        cur.executemany(
            """
            INSERT INTO endpoints
                (repo_id, file_id, method, path, framework, line,
                 handler_name, handler_line, signals, inline_calls)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    repo_id, file_id, e.method, e.path, e.framework, e.line,
                    e.handler_name, e.handler_line, list(e.signals), list(e.inline_calls),
                )
                for e in result.endpoints
            ],
        )
    conn.execute("UPDATE files SET analyzed = TRUE WHERE id = %s", (file_id,))


def _resolve_graph(conn: psycopg.Connection, repo_id: int) -> None:
    """Link call edges / endpoint handlers to chunk ids by name, preferring the
    same file. Re-run on every ingest since another file may now define a name."""
    conn.execute(
        """
        UPDATE call_edges e SET callee_chunk_id = (
            SELECT c.id FROM chunks c
            WHERE c.repo_id = e.repo_id AND c.kind IN ('function', 'method')
              AND c.name = e.callee_name
            ORDER BY (c.file_id = e.file_id) DESC, c.id
            LIMIT 1)
        WHERE e.repo_id = %s
        """,
        (repo_id,),
    )
    conn.execute(
        """
        UPDATE endpoints e SET handler_chunk_id = (
            SELECT c.id FROM chunks c
            WHERE c.repo_id = e.repo_id AND c.kind IN ('function', 'method')
              AND ((e.handler_line IS NOT NULL AND c.file_id = e.file_id
                    AND c.start_line = e.handler_line)
                OR (e.handler_line IS NULL AND c.name = e.handler_name))
            ORDER BY (c.file_id = e.file_id) DESC, c.id
            LIMIT 1)
        WHERE e.repo_id = %s
        """,
        (repo_id,),
    )


def ingest_repo(
    conn: psycopg.Connection, root: Path, embedder: Embedder | None = None
) -> dict:
    """Index a local directory. Unchanged files (same sha256) are skipped."""
    root = root.resolve()
    repo_id = conn.execute(
        """
        INSERT INTO repos (name, path) VALUES (%s, %s)
        ON CONFLICT (path) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (root.name, str(root)),
    ).fetchone()[0]

    existing = {
        path: (file_id, sha, analyzed)
        for file_id, path, sha, analyzed in conn.execute(
            "SELECT id, path, sha256, analyzed FROM files WHERE repo_id = %s", (repo_id,)
        )
    }

    seen: set[str] = set()
    stats = {
        "repo_id": repo_id,
        "files_indexed": 0,
        "files_unchanged": 0,
        "files_removed": 0,
        "files_analyzed": 0,
        "chunks": 0,
        "chunks_embedded": 0,
    }

    for rel_path, language, abs_path in iter_source_files(root):
        seen.add(rel_path)
        data = abs_path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()

        if rel_path in existing:
            file_id, old_sha, analyzed = existing[rel_path]
            if old_sha == sha:
                stats["files_unchanged"] += 1
                if not analyzed:  # indexed before static analysis existed
                    _store_analysis(conn, repo_id, file_id, data, language)
                    stats["files_analyzed"] += 1
                continue
            conn.execute("DELETE FROM files WHERE id = %s", (file_id,))

        file_id = conn.execute(
            "INSERT INTO files (repo_id, path, language, sha256) VALUES (%s, %s, %s, %s) RETURNING id",
            (repo_id, rel_path, language, sha),
        ).fetchone()[0]

        chunks = parse_source(data, language)
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks
                    (file_id, repo_id, kind, name, qualified_name, start_line, end_line, content)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (file_id, repo_id, c.kind, c.name, c.qualified_name, c.start_line, c.end_line, c.content)
                    for c in chunks
                ],
            )
        _store_analysis(conn, repo_id, file_id, data, language)
        stats["files_indexed"] += 1
        stats["files_analyzed"] += 1
        stats["chunks"] += len(chunks)

    for rel_path, (file_id, _, _) in existing.items():
        if rel_path not in seen:
            conn.execute("DELETE FROM files WHERE id = %s", (file_id,))
            stats["files_removed"] += 1

    _resolve_graph(conn, repo_id)
    conn.commit()  # chunks are durable even if embedding fails; re-ingest resumes
    stats["chunks_embedded"] = embed_pending(conn, repo_id, embedder or get_embedder())

    conn.execute("UPDATE repos SET indexed_at = now() WHERE id = %s", (repo_id,))
    conn.commit()
    return stats
