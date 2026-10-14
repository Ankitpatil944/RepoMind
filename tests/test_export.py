"""Token-budgeted LLM-context export (needs Postgres)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.embed import HashingEmbedder
from app.export import CHARS_PER_TOKEN, estimate_tokens
from app.ingest.service import ingest_repo
from app.main import app

SHOP = Path(__file__).parent.parent / "evals" / "repos" / "shop_api"
client = TestClient(app)


@pytest.fixture
def shop(conn):
    stats = ingest_repo(conn, SHOP, HashingEmbedder())
    yield stats["repo_id"]
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()


def _export(repo, **params):
    r = client.get(f"/repos/{repo}/export", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_export_text_is_plain_ascii(shop):
    """Pasted into arbitrary tools and terminals, so no fancy symbols (also cheaper tokens)."""
    for fmt in ("markdown", "json"):
        text = _export(shop, detail="source", max_tokens=60_000, format=fmt)["content"]
        assert text.isascii(), sorted({c for c in text if ord(c) > 127})


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 0
    assert CHARS_PER_TOKEN == 4


def test_map_export_contains_architecture_routes_and_signatures(shop):
    out = _export(shop, detail="map", max_tokens=60_000)
    md = out["content"]

    assert md.startswith("# shop_api: codebase map")
    assert "static analysis (no LLM)" in md
    assert "17 HTTP endpoints" in md
    assert "## Architecture" in md and "`routes/`" in md  # opened inside app/
    assert "- POST /auth/login -> login [auth]" in md
    assert "- GET /orders -> list_orders [protected]" in md
    assert "- GET /health -> health [public]" in md
    assert "`def verify_password(raw: str, salt: bytes, expected: str) -> bool`" in md
    assert "- Exchange an email and password for an access token." in md
    assert "callers " in md  # fan-in annotations
    assert out["truncated"] is False and out["over_budget"] is False


def test_export_does_not_contain_source_bodies_unless_asked(shop):
    body_marker = "hashlib.pbkdf2_hmac"  # appears only inside hash_password's body

    assert body_marker not in _export(shop, detail="map", max_tokens=60_000)["content"]
    src = _export(shop, detail="source", max_tokens=60_000)["content"]
    assert "## Key source" in src and body_marker in src


def test_budget_is_respected_and_trimming_is_declared(shop):
    full = _export(shop, detail="map", max_tokens=60_000)
    tight = _export(shop, detail="map", max_tokens=1_100)

    assert tight["estimated_tokens"] < full["estimated_tokens"]
    assert tight["truncated"] is True
    assert "Trimmed to fit the token budget" in tight["content"]
    # essentials alone may exceed a tiny budget, but optional content never does
    assert tight["estimated_tokens"] <= max(tight["budget"], 1_000 * 1.6)
    assert sum(tight["omitted"].values()) > 0


def test_more_important_files_survive_trimming(shop):
    tight = _export(shop, detail="map", max_tokens=2_000)["content"]

    # routes dominate the importance score, so the auth routes file is kept
    assert "app/routes/auth.py" in tight


def test_overview_is_much_smaller_than_map_and_raw_source(shop):
    est = client.get(f"/repos/{shop}/export/estimate").json()

    assert est["overview_tokens"] < est["map_tokens"] < est["full_source_tokens"] * 2
    assert est["overview_tokens"] < est["full_source_tokens"] / 3
    assert est["full_source_tokens"] > 1_000


def test_json_export_is_valid_compact_and_budgeted(shop):
    out = _export(shop, detail="map", max_tokens=60_000, format="json")
    data = json.loads(out["content"])

    assert data["repo"] == "shop_api"
    assert data["totals"]["endpoints"] == 17
    assert any(e["path"] == "/auth/login" and e["auth"] == "auth" for e in data["endpoints"])
    assert any(f["path"] == "app/security.py" for f in data["files"])
    assert "\n" not in out["content"]  # compact: no pretty-printing whitespace

    tight = _export(shop, detail="map", max_tokens=1_500, format="json")
    assert json.loads(tight["content"])  # still valid JSON after trimming
    assert tight["estimated_tokens"] < out["estimated_tokens"]


def test_tests_are_left_out(conn, shop, tmp_path):
    out = _export(shop, detail="map", max_tokens=60_000)

    assert out["test_files_left_out"] == 0
    assert "test_" not in out["content"]


def test_validation_errors_are_400(shop):
    for params in ({"detail": "everything"}, {"format": "xml"}, {"max_tokens": 10}, {"max_tokens": 9_999_999}):
        r = client.get(f"/repos/{shop}/export", params=params)
        assert r.status_code == 400, params
    assert client.get("/repos/999999/export").status_code == 404
