import os
import shutil
from pathlib import Path

import pytest

# Tests never download or run real models: fake embedder, no reranker.
os.environ["EMBEDDER"] = "hashing"
os.environ["RERANKER"] = "none"

from app import db  # noqa: E402
from app.embed import HashingEmbedder  # noqa: E402
from app.ingest.service import ingest_repo  # noqa: E402

SAMPLE = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def conn():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set (docker compose up -d db)")
    with db.connect() as c:
        db.init_schema(c)
        yield c


@pytest.fixture
def indexed_repo(conn, tmp_path):
    """Sample repo copied to a temp dir and ingested; removed afterwards."""
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)
    stats = ingest_repo(conn, repo, HashingEmbedder())
    yield stats["repo_id"]
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()
