"""Indexes made by an older analyzer must be re-analyzed after an upgrade."""

import shutil
from pathlib import Path

from app import db
from app.embed import HashingEmbedder
from app.ingest.service import ingest_repo

API = Path(__file__).parent / "fixtures" / "api_repo"


def test_bumped_analysis_version_forces_reanalysis(conn, tmp_path):
    repo = tmp_path / "api"
    shutil.copytree(API, repo)
    stats = ingest_repo(conn, repo, HashingEmbedder())
    repo_id = stats["repo_id"]
    try:
        # Simulate an index produced by an older analyzer version.
        conn.execute(
            "UPDATE schema_meta SET value = 'older' WHERE key = 'analysis_version'"
        )
        conn.commit()

        db.init_schema(conn)  # what happens on API start-up after an upgrade

        stale = conn.execute(
            "SELECT count(*) FROM files WHERE repo_id = %s AND NOT analyzed", (repo_id,)
        ).fetchone()[0]
        assert stale == 2

        again = ingest_repo(conn, repo, HashingEmbedder())
        assert again["files_indexed"] == 0  # nothing re-parsed
        assert again["files_analyzed"] == 2  # but analysis re-ran
        assert conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'analysis_version'"
        ).fetchone()[0] == db.ANALYSIS_VERSION
    finally:
        conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
        conn.commit()
