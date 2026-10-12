import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm
from app.ask import build_messages
from app.main import app
from app.retrieval import Hit


def _hit(**kw) -> Hit:
    base = dict(
        chunk_id=1, file="auth.py", kind="function", qualified_name="login",
        start_line=10, end_line=13, content="def login(): ...",
    )
    return Hit(**{**base, **kw})


def test_build_messages_numbers_snippets_with_locations():
    messages = build_messages("How do users log in?", [_hit(), _hit(file="server.js", start_line=4, end_line=7)])

    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "[1] auth.py:10-13 (function login)" in user
    assert "[2] server.js:4-7" in user
    assert user.rstrip().endswith("Question: How do users log in?")


def _client_returning(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_llm_chat_parses_openai_shape(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi [1]"}}]})

    out = llm.chat([{"role": "user", "content": "q"}], client=_client_returning(handler))

    assert out == "hi [1]"
    assert seen == {"url": "http://llm.test/v1/chat/completions", "auth": "Bearer secret"}


def test_llm_chat_wraps_http_errors(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")

    with pytest.raises(llm.LLMError):
        llm.chat([], client=_client_returning(lambda r: httpx.Response(500)))


def test_ask_returns_answer_and_citations(conn, indexed_repo, monkeypatch):
    captured = {}

    def fake_chat(messages):
        captured["messages"] = messages
        return "Login is handled by `login` in auth.py [1]."

    monkeypatch.setattr(llm, "chat", fake_chat)

    r = TestClient(app).post(
        "/ask", json={"repo_id": indexed_repo, "question": "which endpoint handles login"}
    )

    body = r.json()
    assert r.status_code == 200
    assert body["answer"].startswith("Login is handled")
    assert body["error"] is None
    assert body["sources"][0]["file"] == "auth.py"
    assert body["sources"][0]["start_line"] == 10
    assert "auth.py:10-13" in captured["messages"][1]["content"]


def test_ask_degrades_to_sources_when_llm_is_down(conn, indexed_repo, monkeypatch):
    def broken(_messages):
        raise llm.LLMError("connection refused")

    monkeypatch.setattr(llm, "chat", broken)

    r = TestClient(app).post("/ask", json={"repo_id": indexed_repo, "question": "login"})

    body = r.json()
    assert r.status_code == 200
    assert body["answer"] is None
    assert "connection refused" in body["error"]
    assert body["sources"]


def test_ask_unknown_repo_is_404(conn):
    r = TestClient(app).post("/ask", json={"repo_id": 999_999, "question": "anything"})

    assert r.status_code == 404


def test_search_returns_content_and_locations(conn, indexed_repo):
    r = TestClient(app).post("/search", json={"repo_id": indexed_repo, "query": "login", "top_k": 2})

    assert r.status_code == 200
    first = r.json()[0]
    assert first["name"] == "login"
    assert "def login" in first["content"]
