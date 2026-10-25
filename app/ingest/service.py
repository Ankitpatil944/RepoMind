import hashlib
from collections.abc import Callable
from pathlib import Path

import psycopg

from app.embed import Embedder, get_embedder, to_pgvector
from app.ingest.analysis import analyze_source
from app.ingest.parser import Chunk, count_loc, parse_source
from app.ingest.walker import iter_source_files
from app.text import embedding_text, search_text

EMBED_BATCH = 64

# Method names so common that `anything.<name>()` almost never means *our* method.
COMMON_METHOD_NAMES = frozenset(
    """get set add update pop append extend remove clear copy keys values items close open read write
    send put delete commit rollback flush execute fetchone fetchall join split strip format encode
    decode lower upper run start stop load dump dumps loads post patch head refresh count index find
    sort reverse insert exit enter next map filter reduce push shift then catch emit on off call
    apply connect disconnect save create init reset parse validate render""".split()
)


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


def _refresh_metrics(
    conn: psycopg.Connection, file_id: int, data: bytes, chunks: list[Chunk]
) -> None:
    """Fill signature / doc / complexity / loc for chunks stored by an older
    version, matching them to freshly parsed ones by kind + name + start line."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            UPDATE chunks SET signature = %s, doc = %s, complexity = %s, loc = %s
            WHERE file_id = %s AND kind = %s AND qualified_name = %s AND start_line = %s
            """,
            [
                (c.signature, c.doc, c.complexity, c.loc, file_id, c.kind, c.qualified_name, c.start_line)
                for c in chunks
            ],
        )
    conn.execute("UPDATE files SET loc = %s WHERE id = %s", (count_loc(data), file_id))


def _store_analysis(
    conn: psycopg.Connection,
    repo_id: int,
    file_id: int,
    data: bytes,
    language: str,
    chunks: list[Chunk] | None = None,
) -> None:
    """Imports, call edges and endpoints for one file (replaces earlier rows).

    `chunks` is passed for a freshly inserted file (metrics already stored);
    when omitted the file is being re-analyzed, so metrics are refreshed too."""
    if chunks is None:
        _refresh_metrics(conn, file_id, data, parse_source(data, language))

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


# How many leading path segments two files share ('a/b/x.py' vs 'a/b/c/y.py' -> 2). Used to
# break ties between same-named definitions: in a monorepo every service has its own
# `get_db`, and a call should resolve to the one in the caller's own service/package.
_SHARED_PREFIX_SQL = """
    COALESCE((SELECT max(i) FROM generate_series(1, least(
                  array_length(string_to_array({a}, '/'), 1),
                  array_length(string_to_array({b}, '/'), 1)) - 1) AS i
              WHERE (string_to_array({a}, '/'))[1:i] = (string_to_array({b}, '/'))[1:i]), 0)
"""


def _resolve_graph(conn: psycopg.Connection, repo_id: int) -> None:
    """Link call edges / endpoint handlers to chunk ids by name, preferring the same
    file, then the definition nearest the caller in the folder tree (so each service in
    a monorepo resolves to its own helpers). Re-run on every ingest since another file
    may now define a name."""
    # Name matching is a guess, so it is deliberately conservative:
    #   foo()        -> a plain function (a bare call can never be a method)
    #   self.foo()   -> a method in the same file
    #   obj.foo()    -> a function/method, unless `foo` is a ubiquitous name
    #                   (get, add, close, ...) that would match unrelated objects
    conn.execute(
        """
        UPDATE call_edges e SET callee_chunk_id = (
            SELECT c.id FROM chunks c JOIN files cf ON cf.id = c.file_id
            WHERE c.repo_id = e.repo_id AND c.name = e.callee_name
              AND CASE
                    WHEN position('.' in e.callee_full) = 0 THEN c.kind = 'function'
                    -- exactly one dot: `self.foo`, not `self.cache.foo`
                    WHEN (left(e.callee_full, 5) = 'self.'
                          OR left(e.callee_full, 4) = 'cls.'
                          OR left(e.callee_full, 5) = 'this.')
                         AND length(e.callee_full) - length(replace(e.callee_full, '.', '')) = 1
                      THEN c.kind = 'method' AND c.file_id = e.file_id
                    ELSE c.kind IN ('function', 'method')
                         AND e.callee_name <> ALL(%s)
                  END
            ORDER BY (c.file_id = e.file_id) DESC, {shared} DESC, c.id
            LIMIT 1)
        WHERE e.repo_id = %s
        """.replace("{shared}", _SHARED_PREFIX_SQL.format(
            a="cf.path", b="(SELECT path FROM files WHERE id = e.file_id)")),
        (list(COMMON_METHOD_NAMES), repo_id),
    )
    conn.execute(
        """
        UPDATE endpoints e SET handler_chunk_id = (
            SELECT c.id FROM chunks c JOIN files cf ON cf.id = c.file_id
            WHERE c.repo_id = e.repo_id
              AND (c.kind IN ('function', 'method')
                   OR (e.framework = 'django' AND c.kind = 'class'))  -- class-based views
              AND ((e.handler_line IS NOT NULL AND c.file_id = e.file_id
                    AND c.start_line = e.handler_line)
                OR (e.handler_line IS NULL AND c.name = e.handler_name))
            ORDER BY (c.file_id = e.file_id) DESC, {shared} DESC, c.id
            LIMIT 1)
        WHERE e.repo_id = %s
        """.replace("{shared}", _SHARED_PREFIX_SQL.format(
            a="cf.path", b="(SELECT path FROM files WHERE id = e.file_id)")),
        (repo_id,),
    )


def _refine_methods(conn: psycopg.Connection, repo_id: int) -> None:
    """Django routes start as ANY; narrow them using the view's own decorators
    (@require_POST, @api_view(['GET', 'POST']), ...) once the handler is linked."""
    rows = conn.execute(
        """
        SELECT e.id, array_agg(DISTINCT ce.callee_full)
        FROM endpoints e
        JOIN call_edges ce ON ce.caller_chunk_id = e.handler_chunk_id
        WHERE e.repo_id = %s AND e.method = 'ANY' AND ce.callee_full LIKE '@%%'
        GROUP BY e.id
        """,
        (repo_id,),
    ).fetchall()
    # DRF read-only viewsets only answer GET: drop the write routes generated for them.
    conn.execute(
        """
        DELETE FROM endpoints e
        WHERE e.repo_id = %s AND e.framework = 'django'
          AND e.method IN ('POST', 'PUT', 'PATCH', 'DELETE')
          AND EXISTS (SELECT 1 FROM call_edges ce
                      WHERE ce.caller_chunk_id = e.handler_chunk_id
                        AND ce.callee_full LIKE '@base:ReadOnly%%')
        """,
        (repo_id,),
    )
    fixed = {"@require_POST": "POST", "@require_GET": "GET", "@require_safe": "GET"}
    for endpoint_id, markers in rows:
        methods: list[str] = []
        for marker in markers:
            if marker in fixed:
                methods.append(fixed[marker])
            elif marker.startswith(("@api_view:", "@require_http_methods:")):
                methods.extend(m for m in marker.split(":", 1)[1].split(",") if m)
        methods = sorted(set(methods))
        if not methods:
            continue
        conn.execute("UPDATE endpoints SET method = %s WHERE id = %s", (methods[0], endpoint_id))
        for extra in methods[1:]:
            conn.execute(
                """
                INSERT INTO endpoints (repo_id, file_id, method, path, framework, line,
                    handler_name, handler_line, handler_chunk_id, signals, inline_calls)
                SELECT repo_id, file_id, %s, path, framework, line,
                    handler_name, handler_line, handler_chunk_id, signals, inline_calls
                FROM endpoints WHERE id = %s
                """,
                (extra, endpoint_id),
            )


def ingest_repo(
    conn: psycopg.Connection,
    root: Path,
    embedder: Embedder | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Index a local directory. Unchanged files (same sha256) are skipped.

    `progress(phase, done, total)` is called as work advances (used by background jobs)."""
    report = progress or (lambda *_: None)
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

    files = list(iter_source_files(root))
    for n, (rel_path, language, abs_path) in enumerate(files):
        report("parsing", n, len(files))
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
            """
            INSERT INTO files (repo_id, path, language, sha256, loc)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (repo_id, rel_path, language, sha, count_loc(data)),
        ).fetchone()[0]

        chunks = parse_source(data, language)
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks
                    (file_id, repo_id, kind, name, qualified_name, start_line, end_line,
                     content, signature, doc, complexity, loc)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        file_id, repo_id, c.kind, c.name, c.qualified_name, c.start_line,
                        c.end_line, c.content, c.signature, c.doc, c.complexity, c.loc,
                    )
                    for c in chunks
                ],
            )
        _store_analysis(conn, repo_id, file_id, data, language, chunks)
        stats["files_indexed"] += 1
        stats["files_analyzed"] += 1
        stats["chunks"] += len(chunks)

    for rel_path, (file_id, _, _) in existing.items():
        if rel_path not in seen:
            conn.execute("DELETE FROM files WHERE id = %s", (file_id,))
            stats["files_removed"] += 1

    report("linking", len(files), len(files))
    _resolve_graph(conn, repo_id)
    _refine_methods(conn, repo_id)
    conn.commit()  # chunks are durable even if embedding fails; re-ingest resumes
    report("embedding", len(files), len(files))
    stats["chunks_embedded"] = embed_pending(conn, repo_id, embedder or get_embedder())

    conn.execute("UPDATE repos SET indexed_at = now() WHERE id = %s", (repo_id,))
    conn.commit()
    return stats
