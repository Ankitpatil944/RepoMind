import httpx
import pytest

from app import cli


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://repomind.test", transport=httpx.MockTransport(handler))


REPOS = [
    {"id": 3, "name": "shop", "path": "/repos/shop", "files": 4, "chunks": 20, "indexed_at": None},
    {"id": 9, "name": "shop", "path": "/samples/shop", "files": 4, "chunks": 20, "indexed_at": None},
]


def test_resolve_repo_by_id_and_newest_name():
    c = _client(lambda r: httpx.Response(200, json=REPOS))

    assert cli.resolve_repo(c, "5") == 5
    assert cli.resolve_repo(c, "shop") == 9


def test_resolve_repo_unknown_lists_known_names():
    c = _client(lambda r: httpx.Response(200, json=REPOS))

    with pytest.raises(SystemExit) as e:
        cli.resolve_repo(c, "nope")

    assert "shop" in str(e.value)


def test_ingest_prefixes_relative_names(capsys):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(
            200, json={"repo_id": 7, "files_indexed": 2, "files_unchanged": 0, "chunks": 11}
        )

    assert cli.main(["ingest", "myproj"], client=_client(handler)) == 0
    assert '"/repos/myproj"' in seen["body"]
    assert "Indexed repo id 7" in capsys.readouterr().out


def test_ask_prints_answer_and_sources(capsys):
    def handler(request):
        if request.url.path == "/repos":
            return httpx.Response(200, json=REPOS)
        return httpx.Response(
            200,
            json={
                "answer": "Login is POST /auth/login [1].",
                "error": None,
                "sources": [
                    {"ref": 1, "file": "auth.py", "start_line": 10, "end_line": 13, "name": "login"}
                ],
            },
        )

    assert cli.main(["ask", "shop", "how to log in"], client=_client(handler)) == 0
    out = capsys.readouterr().out
    assert "Login is POST /auth/login [1]." in out
    assert "[1] auth.py:10-13  login" in out


def test_ask_without_llm_still_shows_sources_and_hint(capsys):
    resp = {
        "answer": None,
        "error": "LLM request failed",
        "sources": [{"ref": 1, "file": "a.py", "start_line": 1, "end_line": 2, "name": "f"}],
    }
    c = _client(lambda r: httpx.Response(200, json=REPOS if r.url.path == "/repos" else resp))

    assert cli.main(["ask", "3", "q"], client=c) == 0
    out = capsys.readouterr().out
    assert "No answer: LLM request failed" in out
    assert "Enable /ask" in out
    assert "a.py:1-2" in out


def test_api_error_is_reported_not_raised(capsys):
    c = _client(lambda r: httpx.Response(400, json={"detail": "path must be inside one of: /repos"}))

    assert cli.main(["ingest", "/etc"], client=c) == 1
    assert "path must be inside" in capsys.readouterr().err


def test_unreachable_api_gives_a_hint(capsys):
    def handler(request):
        raise httpx.ConnectError("refused")

    assert cli.main(["repos"], client=_client(handler)) == 1
    assert "docker compose up -d" in capsys.readouterr().err


def test_format_endpoints_marks_auth():
    rows = [
        {"method": "POST", "path": "/auth/login", "file": "a.py", "line": 3, "handler": "login",
         "handles_authentication": True, "requires_auth": False},
        {"method": "GET", "path": "/me", "file": "a.py", "line": 9, "handler": None,
         "handles_authentication": False, "requires_auth": True},
    ]

    out = cli.format_endpoints(rows)

    assert "AUTH" in out.splitlines()[0]
    assert "protected" in out.splitlines()[1]
    assert "(inline)" in out.splitlines()[1]
