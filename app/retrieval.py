"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with
reciprocal rank fusion, then (optionally) cross-encoder reranked."""

from dataclasses import dataclass, field

import psycopg

from app.embed import Embedder, to_pgvector
from app.rerank import Reranker
from app.text import query_terms

RRF_K = 60
CANDIDATES_PER_RETRIEVER = 30
RERANK_POOL = 20
RERANK_DOC_CHARS = 2000


@dataclass
class Hit:
    chunk_id: int
    file: str
    kind: str
    qualified_name: str
    start_line: int
    end_line: int
    content: str
    score: float = 0.0
    matched_by: list[str] = field(default_factory=list)


def rrf(rankings: dict[str, list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion over named ranked id lists."""
    scores: dict[int, float] = {}
    for ids in rankings.values():
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def _vector_ids(conn: psycopg.Connection, repo_id: int, query_vec: list[float], limit: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT id FROM chunks
        WHERE repo_id = %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (repo_id, to_pgvector(query_vec), limit),
    ).fetchall()
    return [r[0] for r in rows]


def _keyword_ids(conn: psycopg.Connection, repo_id: int, terms: list[str], limit: int) -> list[int]:
    if not terms:
        return []
    # OR-semantics: natural-language questions rarely have every word in one chunk.
    # Terms are [a-z0-9]+ only (see split_identifiers), so the tsquery is safe.
    tsquery = " | ".join(terms)
    rows = conn.execute(
        """
        SELECT id FROM chunks
        WHERE repo_id = %s AND search_tsv @@ to_tsquery('simple', %s)
        ORDER BY ts_rank_cd(search_tsv, to_tsquery('simple', %s)) DESC
        LIMIT %s
        """,
        (repo_id, tsquery, tsquery, limit),
    ).fetchall()
    return [r[0] for r in rows]


def hybrid_search(
    conn: psycopg.Connection,
    repo_id: int,
    query: str,
    embedder: Embedder,
    reranker: Reranker | None = None,
    top_k: int = 6,
) -> list[Hit]:
    vector = _vector_ids(conn, repo_id, embedder.embed_query(query), CANDIDATES_PER_RETRIEVER)
    keyword = _keyword_ids(conn, repo_id, query_terms(query), CANDIDATES_PER_RETRIEVER)

    fused = rrf({"vector": vector, "keyword": keyword})
    if not fused:
        return []
    pool_ids = sorted(fused, key=fused.get, reverse=True)[: max(RERANK_POOL, top_k)]

    rows = conn.execute(
        """
        SELECT c.id, f.path, c.kind, c.qualified_name, c.start_line, c.end_line, c.content
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.id = ANY(%s)
        """,
        (pool_ids,),
    ).fetchall()
    by_id = {
        r[0]: Hit(r[0], r[1], r[2], r[3], r[4], r[5], r[6], score=fused[r[0]],
                  matched_by=[n for n, ids in (("vector", vector), ("keyword", keyword)) if r[0] in ids])
        for r in rows
    }
    hits = [by_id[i] for i in pool_ids if i in by_id]

    if reranker is not None and len(hits) > 1:
        docs = [f"{h.file}\n{h.qualified_name}\n{h.content}"[:RERANK_DOC_CHARS] for h in hits]
        for hit, score in zip(hits, reranker.score(query, docs)):
            hit.score = score
        hits.sort(key=lambda h: h.score, reverse=True)

    return hits[:top_k]
