import hashlib
from pathlib import Path

import psycopg

from app.embed import Embedder, get_embedder, to_pgvector
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
        path: (file_id, sha)
        for file_id, path, sha in conn.execute(
            "SELECT id, path, sha256 FROM files WHERE repo_id = %s", (repo_id,)
        )
    }

    seen: set[str] = set()
    stats = {
        "repo_id": repo_id,
        "files_indexed": 0,
        "files_unchanged": 0,
        "files_removed": 0,
        "chunks": 0,
        "chunks_embedded": 0,
    }

    for rel_path, language, abs_path in iter_source_files(root):
        seen.add(rel_path)
        data = abs_path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()

        if rel_path in existing:
            file_id, old_sha = existing[rel_path]
            if old_sha == sha:
                stats["files_unchanged"] += 1
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
        stats["files_indexed"] += 1
        stats["chunks"] += len(chunks)

    for rel_path, (file_id, _) in existing.items():
        if rel_path not in seen:
            conn.execute("DELETE FROM files WHERE id = %s", (file_id,))
            stats["files_removed"] += 1

    conn.commit()  # chunks are durable even if embedding fails; re-ingest resumes
    stats["chunks_embedded"] = embed_pending(conn, repo_id, embedder or get_embedder())

    conn.execute("UPDATE repos SET indexed_at = now() WHERE id = %s", (repo_id,))
    conn.commit()
    return stats
