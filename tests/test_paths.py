import os

import pytest
from fastapi import HTTPException

from app.main import _resolve_repo_path


def test_allows_any_configured_root_and_rejects_others(tmp_path, monkeypatch):
    a, b, outside = tmp_path / "a", tmp_path / "b", tmp_path / "outside"
    for d in (a / "proj", b / "proj", outside):
        d.mkdir(parents=True)
    monkeypatch.setenv("REPOS_ROOT", os.pathsep.join([str(a), str(b)]))

    assert _resolve_repo_path(str(a / "proj")) == (a / "proj").resolve()
    assert _resolve_repo_path(str(b / "proj")) == (b / "proj").resolve()
    with pytest.raises(HTTPException) as e:
        _resolve_repo_path(str(outside))
    assert e.value.status_code == 400


def test_rejects_traversal_out_of_root(tmp_path, monkeypatch):
    (tmp_path / "root" / "p").mkdir(parents=True)
    monkeypatch.setenv("REPOS_ROOT", str(tmp_path / "root"))

    with pytest.raises(HTTPException):
        _resolve_repo_path(str(tmp_path / "root" / "p" / ".." / ".."))
