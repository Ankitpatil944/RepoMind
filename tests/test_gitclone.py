import pytest
from fastapi.testclient import TestClient

from app import gitclone, main
from app.gitclone import GitError, parse_git_url


def test_parses_and_normalises():
    url, name = parse_git_url("https://github.com/Owner/Repo")
    assert url == "https://github.com/Owner/Repo.git"
    assert name == "Owner__Repo"
    assert parse_git_url("https://github.com/o/r.git/")[1] == "o__r"


@pytest.mark.parametrize(
    "bad",
    [
        "http://github.com/o/r",
        "git@github.com:o/r.git",
        "ssh://github.com/o/r",
        "https://user:tok@github.com/o/r",
        "https://evil.example.com/o/r",
        "https://github.com/o",
        "https://github.com/o/../r",
        "https://github.com/o/r?x=1",
        "https://github.com/-upload-pack=x/r",
        "file:///etc/passwd",
    ],
)
def test_rejects_unsafe_urls(bad):
    with pytest.raises(GitError):
        parse_git_url(bad)


def test_host_allowlist_is_configurable(monkeypatch):
    monkeypatch.setenv("GIT_HOSTS", "git.example.com")
    assert parse_git_url("https://git.example.com/a/b")[1] == "a__b"
    with pytest.raises(GitError):
        parse_git_url("https://github.com/a/b")


def test_fetch_clones_then_refreshes(tmp_path, monkeypatch):
    monkeypatch.setenv("CLONES_DIR", str(tmp_path))
    calls: list[list[str]] = []

    def fake_git(args, cwd=None):
        calls.append(args)
        if args[0] == "clone":
            (tmp_path / "o__r" / ".git").mkdir(parents=True)

    monkeypatch.setattr(gitclone, "_git", fake_git)

    dest = gitclone.fetch("https://github.com/o/r")
    assert dest == tmp_path / "o__r"
    assert calls[0][:4] == ["clone", "--depth", "1", "--no-tags"]
    assert calls[0][4] == "--"  # URL can never be parsed as an option

    gitclone.fetch("https://github.com/o/r")  # second call refreshes, no new clone
    assert [c[0] for c in calls] == ["clone", "fetch", "reset"]


def test_ingest_requires_exactly_one_source():
    c = TestClient(main.app)
    assert c.post("/ingest", json={}).status_code == 422
    both = c.post("/ingest", json={"path": "/repos/x", "url": "https://github.com/o/r"})
    assert both.status_code == 422


def test_ingest_bad_url_is_a_400():
    c = TestClient(main.app)
    r = c.post("/ingest", json={"url": "https://evil.example.com/o/r"})
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"]


def test_job_endpoint_validates_before_queueing():
    c = TestClient(main.app)
    assert c.post("/ingest/jobs", json={}).status_code == 422
    r = c.post("/ingest/jobs", json={"url": "https://evil.example.com/o/r"})
    assert r.status_code == 400
    assert c.get("/jobs/nope").status_code == 404
