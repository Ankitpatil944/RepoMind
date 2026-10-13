"""Integration tests for the UI-facing endpoints (need Postgres)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.embed import HashingEmbedder
from app.graph import call_flow
from app.ingest.service import ingest_repo
from app.main import app

API = Path(__file__).parent / "fixtures" / "api_repo"
client = TestClient(app)


@pytest.fixture
def repo(conn, tmp_path):
    root = tmp_path / "api"
    shutil.copytree(API, root)
    stats = ingest_repo(conn, root, HashingEmbedder())
    yield stats["repo_id"], root
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()


def _endpoint(repo_id: int, method: str, path: str) -> dict:
    rows = client.get(f"/repos/{repo_id}/endpoints").json()
    return next(e for e in rows if e["method"] == method and e["path"] == path)


def _symbol(repo_id: int, name: str) -> dict:
    return client.get(f"/repos/{repo_id}/symbols", params={"q": name}).json()[0]


# ----------------------------------------------------------------- files


def test_files_lists_indexed_files_with_counts(repo):
    repo_id, _ = repo

    rows = {f["path"]: f for f in client.get(f"/repos/{repo_id}/files").json()}

    assert set(rows) == {"fastapi_app.py", "express_app.js"}
    assert rows["fastapi_app.py"]["language"] == "python"
    assert rows["fastapi_app.py"]["endpoints"] == 5
    assert rows["fastapi_app.py"]["symbols"] >= 8


def test_file_content_returns_source_and_symbol_ranges(repo):
    repo_id, _ = repo

    r = client.get(f"/repos/{repo_id}/files/content", params={"path": "fastapi_app.py"}).json()

    assert "def verify_password" in r["content"]
    assert r["changed_since_indexed"] is False
    symbols = {s["name"]: s for s in r["symbols"]}
    assert symbols["verify_password"]["kind"] == "function"
    lines = r["content"].splitlines()
    assert lines[symbols["verify_password"]["start_line"] - 1].startswith("def verify_password")


def test_file_content_flags_files_changed_since_indexing(repo):
    repo_id, root = repo
    (root / "fastapi_app.py").write_text("# edited\n" + (root / "fastapi_app.py").read_text())

    r = client.get(f"/repos/{repo_id}/files/content", params={"path": "fastapi_app.py"}).json()

    assert r["changed_since_indexed"] is True


def test_file_content_only_serves_indexed_paths(repo):
    repo_id, _ = repo

    r = client.get(f"/repos/{repo_id}/files/content", params={"path": "../../etc/passwd"})

    assert r.status_code == 404


def test_file_content_blocks_indexed_row_that_escapes_repo(conn, repo):
    """Defence in depth: even a poisoned index row cannot read outside the repo."""
    repo_id, root = repo
    (root.parent / "secret.py").write_text("TOKEN = 'x'\n")
    conn.execute(
        "INSERT INTO files (repo_id, path, language, sha256) VALUES (%s, %s, 'python', 'x')",
        (repo_id, "../secret.py"),
    )
    conn.commit()

    r = client.get(f"/repos/{repo_id}/files/content", params={"path": "../secret.py"})

    assert r.status_code == 400


def test_unknown_repo_is_404(conn):
    assert client.get("/repos/999999/files").status_code == 404
    assert client.get("/repos/999999/symbols", params={"q": "x"}).status_code == 404


# --------------------------------------------------------------- symbols


def test_symbol_search_ranks_exact_then_prefix_then_substring(repo):
    repo_id, _ = repo

    names = [s["name"] for s in client.get(f"/repos/{repo_id}/symbols", params={"q": "login"}).json()]

    assert names[0] == "login"  # exact matches first
    assert names.count("login") == 2  # python + javascript definitions


def test_symbol_search_escapes_like_wildcards(repo):
    repo_id, _ = repo

    assert client.get(f"/repos/{repo_id}/symbols", params={"q": "%"}).json() == []
    # '_' must match a literal underscore only, not "any single character"
    underscore = client.get(f"/repos/{repo_id}/symbols", params={"q": "_"}).json()
    assert underscore
    assert all("_" in s["qualified_name"] for s in underscore)
    assert "login" not in {s["name"] for s in underscore}


def test_symbol_search_kind_filter_and_empty_query_lists(repo):
    repo_id, _ = repo

    funcs = client.get(f"/repos/{repo_id}/symbols", params={"kind": "function"}).json()

    assert funcs and all(s["kind"] == "function" for s in funcs)


# ------------------------------------------------------------------ flow


def test_flow_from_endpoint_reaches_auth_evidence(repo):
    repo_id, _ = repo
    ep = _endpoint(repo_id, "GET", "/reports")

    flow = client.get(
        f"/repos/{repo_id}/graph/flow", params={"endpoint_id": ep["id"], "depth": 3}
    ).json()

    labels = {n["label"]: n for n in flow["nodes"]}
    assert flow["root"] == f"e:{ep['id']}"
    assert {"GET /reports", "reports", "build_report", "get_current_user", "decode_token"} <= set(labels)
    assert labels["jwt.decode"]["type"] == "external"
    assert labels["jwt.decode"]["auth_related"] is True
    assert labels["GET /reports"]["requires_auth"] is True
    edge_pairs = {(e["source"], e["target"]) for e in flow["edges"]}
    assert (labels["reports"]["id"], labels["build_report"]["id"]) in edge_pairs
    assert flow["truncated"] is False


def test_flow_depth_limits_the_walk(repo):
    repo_id, _ = repo
    ep = _endpoint(repo_id, "GET", "/reports")

    flow = client.get(
        f"/repos/{repo_id}/graph/flow", params={"endpoint_id": ep["id"], "depth": 1}
    ).json()

    labels = {n["label"] for n in flow["nodes"]}
    assert "build_report" in labels
    assert "get_current_user" not in labels


def test_flow_up_finds_callers_and_routes(repo):
    repo_id, _ = repo
    chunk = _symbol(repo_id, "build_report")["chunk_id"]

    flow = client.get(
        f"/repos/{repo_id}/graph/flow",
        params={"chunk_id": chunk, "direction": "up", "depth": 2},
    ).json()

    labels = {n["label"] for n in flow["nodes"]}
    assert {"build_report", "reports", "GET /reports"} <= labels


def test_flow_node_cap_sets_truncated(conn, repo):
    repo_id, _ = repo
    ep = _endpoint(repo_id, "GET", "/reports")

    flow = call_flow(conn, repo_id, endpoint_id=ep["id"], depth=4, max_nodes=3)

    assert len(flow["nodes"]) == 3
    assert flow["truncated"] is True


def test_flow_validates_arguments(repo):
    repo_id, _ = repo

    assert client.get(f"/repos/{repo_id}/graph/flow").status_code == 400
    assert client.get(
        f"/repos/{repo_id}/graph/flow", params={"endpoint_id": 1, "chunk_id": 1}
    ).status_code == 400
    assert client.get(
        f"/repos/{repo_id}/graph/flow", params={"chunk_id": 1, "direction": "sideways"}
    ).status_code == 400
    assert client.get(
        f"/repos/{repo_id}/graph/flow", params={"endpoint_id": 999999}
    ).status_code == 404


# --------------------------------------------------------------- explain


def test_explain_grounds_prompt_in_callees_callers_and_endpoint(repo, monkeypatch):
    repo_id, _ = repo
    chunk = _symbol(repo_id, "reports")["chunk_id"]
    seen = {}

    def fake_chat(messages):
        seen["user"] = messages[1]["content"]
        return "It builds the report [1] using build_report [2]."

    monkeypatch.setattr(llm, "chat", fake_chat)

    body = client.post("/explain", json={"repo_id": repo_id, "chunk_id": chunk}).json()

    assert body["answer"].startswith("It builds the report")
    assert body["error"] is None
    assert body["sources"][0]["chunk_id"] == chunk
    assert any(s["name"] == "build_report" for s in body["sources"])
    assert "GET /reports" in seen["user"]
    assert "def build_report" in seen["user"]


def test_explain_degrades_without_llm(repo, monkeypatch):
    repo_id, _ = repo
    chunk = _symbol(repo_id, "build_report")["chunk_id"]

    def down(_messages):
        raise llm.LLMError("connection refused")

    monkeypatch.setattr(llm, "chat", down)

    body = client.post("/explain", json={"repo_id": repo_id, "chunk_id": chunk}).json()

    assert body["answer"] is None
    assert "connection refused" in body["error"]
    assert body["sources"]
    assert any("reports" in c for c in body["callers"])


def test_explain_unknown_chunk_is_404(repo):
    repo_id, _ = repo

    assert client.post("/explain", json={"repo_id": repo_id, "chunk_id": 999999}).status_code == 404


def test_existing_responses_gain_fields_without_losing_any(repo):
    repo_id, _ = repo

    ep = _endpoint(repo_id, "GET", "/reports")

    assert {"id", "method", "path", "framework", "file", "line", "handler",
            "handles_authentication", "requires_auth", "evidence"} <= set(ep)
    assert ep["handler_chunk_id"] is not None
