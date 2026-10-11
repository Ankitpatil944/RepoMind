"""Integration test; needs a running Postgres (docker compose up -d db)."""

import os
import shutil
from pathlib import Path

import pytest

from app import db
from app.ingest.service import ingest_repo

SAMPLE = Path(__file__).parent / "fixtures" / "sample_repo"

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture
def conn():
    with db.connect() as c:
        db.init_schema(c)
        yield c


def test_ingest_is_incremental(conn, tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)

    first = ingest_repo(conn, repo)
    assert first["files_indexed"] == 2
    assert first["chunks"] > 5

    second = ingest_repo(conn, repo)
    assert second["files_indexed"] == 0
    assert second["files_unchanged"] == 2

    (repo / "server.js").unlink()
    third = ingest_repo(conn, repo)
    assert third["files_removed"] == 1

    conn.execute("DELETE FROM repos WHERE id = %s", (first["repo_id"],))
    conn.commit()
