from pathlib import Path

from app.ingest.parser import parse_source
from app.ingest.walker import iter_source_files

SAMPLE = Path(__file__).parent / "fixtures" / "sample_repo"


def _chunks(filename: str, language: str):
    return parse_source((SAMPLE / filename).read_bytes(), language)


def test_python_functions_methods_and_classes():
    by_name = {c.qualified_name: c for c in _chunks("auth.py", "python")}

    assert {"hash_password", "login", "SessionStore", "SessionStore.get", "SessionStore.put"} <= set(by_name)
    assert by_name["login"].kind == "function"
    assert by_name["SessionStore.get"].kind == "method"
    assert by_name["SessionStore"].kind == "class"


def test_python_decorators_are_part_of_the_chunk():
    login = {c.qualified_name: c for c in _chunks("auth.py", "python")}["login"]

    assert login.content.startswith('@app.route("/login"')
    assert login.start_line == 10


def test_class_chunk_excludes_method_bodies():
    cls = {c.qualified_name: c for c in _chunks("auth.py", "python")}["SessionStore"]

    assert "ttl = 3600" in cls.content
    assert "def get" not in cls.content


def test_module_chunk_holds_top_level_code():
    module = _chunks("auth.py", "python")[0]

    assert module.kind == "module"
    assert "from flask import Flask" in module.content
    assert "def login" not in module.content


def test_javascript_arrow_functions_and_classes():
    by_name = {c.qualified_name: c for c in _chunks("server.js", "javascript")}

    assert by_name["requireAuth"].kind == "function"
    assert by_name["requireAuth"].content.startswith("const requireAuth")
    assert by_name["listUsers"].kind == "function"
    assert by_name["UserService.find"].kind == "method"
    assert 'app.get("/users"' in by_name["<module>"].content


def test_walker_skips_unsupported_and_ignored(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "notes.txt").write_text("hi")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("var a;")

    found = [rel for rel, _, _ in iter_source_files(tmp_path)]

    assert found == ["a.py"]
