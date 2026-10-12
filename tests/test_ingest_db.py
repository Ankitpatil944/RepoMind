"""Integration tests; need Postgres (docker compose up -d db) and DATABASE_URL."""

import shutil
from pathlib import Path

from app.embed import HashingEmbedder
from app.ingest.service import ingest_repo

SAMPLE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_ingest_is_incremental(conn, tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)
    embedder = HashingEmbedder()

    first = ingest_repo(conn, repo, embedder)
    assert first["files_indexed"] == 2
    assert first["chunks"] > 5
    assert first["chunks_embedded"] == first["chunks"]

    second = ingest_repo(conn, repo, embedder)
    assert second["files_indexed"] == 0
    assert second["files_unchanged"] == 2
    assert second["chunks_embedded"] == 0

    (repo / "server.js").unlink()
    third = ingest_repo(conn, repo, embedder)
    assert third["files_removed"] == 1

    conn.execute("DELETE FROM repos WHERE id = %s", (first["repo_id"],))
    conn.commit()


def test_reingest_backfills_missing_embeddings(conn, indexed_repo, tmp_path):
    """Chunks stored before embeddings existed (NULL) get filled on re-ingest."""
    conn.execute(
        "UPDATE chunks SET embedding = NULL, search_text = '' WHERE repo_id = %s", (indexed_repo,)
    )
    conn.commit()
    path = conn.execute("SELECT path FROM repos WHERE id = %s", (indexed_repo,)).fetchone()[0]

    stats = ingest_repo(conn, Path(path), HashingEmbedder())

    assert stats["files_indexed"] == 0
    assert stats["chunks_embedded"] > 0
    missing = conn.execute(
        "SELECT count(*) FROM chunks WHERE repo_id = %s AND embedding IS NULL", (indexed_repo,)
    ).fetchone()[0]
    assert missing == 0
