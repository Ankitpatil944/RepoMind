"""Integration tests for the call graph and endpoint inventory (need Postgres)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.embed import HashingEmbedder
from app.ingest.service import ingest_repo
from app.main import app

API = Path(__file__).parent / "fixtures" / "api_repo"


@pytest.fixture
def api_repo(conn, tmp_path):
    repo = tmp_path / "api"
    shutil.copytree(API, repo)
    stats = ingest_repo(conn, repo, HashingEmbedder())
    yield stats["repo_id"], repo, stats
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()


def _by_route(rows):
    return {(r["method"], r["path"]): r for r in rows}


def test_endpoint_inventory_and_auth_classification(api_repo):
    repo_id, _, _ = api_repo

    rows = _by_route(TestClient(app).get(f"/repos/{repo_id}/endpoints").json())

    login = rows[("POST", "/auth/login")]
    assert login["handles_authentication"] and not login["requires_auth"]
    assert login["file"] == "fastapi_app.py" and login["handler"] == "login"

    assert rows[("GET", "/users/me")]["requires_auth"]  # Depends(get_current_user)
    assert rows[("DELETE", "/users/{user_id}")]["requires_auth"]  # dependencies=[...]
    assert rows[("GET", "/reports")]["requires_auth"]  # transitive: build_report -> get_current_user
    health = rows[("GET", "/health")]
    assert not health["requires_auth"] and not health["handles_authentication"]

    assert rows[("POST", "/api/login")]["handles_authentication"]
    assert rows[("GET", "/orders")]["requires_auth"]  # router.use(requireAuth)
    assert rows[("GET", "/me")]["requires_auth"]
    assert not rows[("GET", "/ping")]["requires_auth"]


def test_endpoint_filter(api_repo):
    repo_id, _, _ = api_repo
    client = TestClient(app)

    auth = client.get(f"/repos/{repo_id}/endpoints", params={"auth": "authentication"}).json()
    public = client.get(f"/repos/{repo_id}/endpoints", params={"auth": "public"}).json()

    assert {e["path"] for e in auth} == {"/auth/login", "/api/login"}
    assert {e["path"] for e in public} == {"/health", "/ping"}
    assert client.get(f"/repos/{repo_id}/endpoints", params={"auth": "nope"}).status_code == 400


def test_function_graph_resolves_calls_both_ways(api_repo):
    repo_id, _, _ = api_repo

    g = TestClient(app).get(f"/repos/{repo_id}/graph", params={"name": "get_current_user"}).json()

    assert [d["name"] for d in g["definitions"]] == ["get_current_user"]
    assert {c["callee"]: c["resolved_name"] for c in g["calls"]}["decode_token"] == "decode_token"
    assert {c["function"] for c in g["called_by"]} == {"build_report"}  # `me` uses Depends(), not a call


def test_reingest_backfills_analysis_for_old_files(conn, api_repo):
    repo_id, repo, _ = api_repo
    conn.execute("UPDATE files SET analyzed = FALSE WHERE repo_id = %s", (repo_id,))
    conn.execute("DELETE FROM endpoints WHERE repo_id = %s", (repo_id,))
    conn.execute("DELETE FROM call_edges WHERE repo_id = %s", (repo_id,))
    conn.commit()

    stats = ingest_repo(conn, repo, HashingEmbedder())

    assert stats["files_indexed"] == 0
    assert stats["files_analyzed"] == 2
    count = conn.execute("SELECT count(*) FROM endpoints WHERE repo_id = %s", (repo_id,)).fetchone()[0]
    assert count == 9


def test_changed_file_replaces_its_endpoints(conn, api_repo):
    repo_id, repo, _ = api_repo
    path = repo / "express_app.js"
    path.write_text(path.read_text().replace('"/ping"', '"/pong"'))

    ingest_repo(conn, repo, HashingEmbedder())

    paths = {e["path"] for e in TestClient(app).get(f"/repos/{repo_id}/endpoints").json()}
    assert "/pong" in paths and "/ping" not in paths


def test_ask_includes_endpoint_inventory_for_api_questions(api_repo, monkeypatch):
    repo_id, _, _ = api_repo
    seen = {}

    def fake_chat(messages):
        seen["user"] = messages[1]["content"]
        return "POST /auth/login handles authentication."

    monkeypatch.setattr(llm, "chat", fake_chat)

    body = TestClient(app).post(
        "/ask", json={"repo_id": repo_id, "question": "which APIs are for authentication?"}
    ).json()

    assert "Detected HTTP endpoints" in seen["user"]
    assert "POST /auth/login -> login [fastapi_app.py:" in seen["user"]
    assert any(e["path"] == "/auth/login" for e in body["endpoints"])


def test_ask_skips_inventory_for_unrelated_questions(api_repo, monkeypatch):
    repo_id, _, _ = api_repo
    seen = {}
    monkeypatch.setattr(llm, "chat", lambda m: seen.setdefault("user", m[1]["content"]) and "ok")

    TestClient(app).post("/ask", json={"repo_id": repo_id, "question": "how is the report built"})

    assert "Detected HTTP endpoints" not in seen["user"]
