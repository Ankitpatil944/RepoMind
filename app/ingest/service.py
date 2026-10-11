import hashlib
from pathlib import Path

import psycopg

from app.ingest.parser import parse_source
from app.ingest.walker import iter_source_files


def ingest_repo(conn: psycopg.Connection, root: Path) -> dict:
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
    stats = {"repo_id": repo_id, "files_indexed": 0, "files_unchanged": 0, "files_removed": 0, "chunks": 0}

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

    conn.execute("UPDATE repos SET indexed_at = now() WHERE id = %s", (repo_id,))
    conn.commit()
    return stats
