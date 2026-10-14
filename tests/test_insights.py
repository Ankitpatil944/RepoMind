"""Deterministic insights: facts, import resolution, overview, module graph."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.embed import HashingEmbedder
from app.ingest.parser import parse_source
from app.ingest.service import ingest_repo
from app.insights import (
    ImportResolver,
    complexity_label,
    describe_chunk,
    external_name,
    is_stdlib,
    resolve_import,
)
from app.main import app

SHOP = Path(__file__).parent.parent / "evals" / "repos" / "shop_api"
client = TestClient(app)


# ---------------------------------------------------------- parser facts


def test_python_signature_doc_complexity_and_loc():
    src = b'''
def login(email: str, password: str) -> dict:
    """Exchange credentials for a token. Extra detail."""
    if not email or not password:
        return {}
    for _ in range(3):
        pass
    return {"ok": True}
'''
    chunk = next(c for c in parse_source(src, "python") if c.name == "login")

    assert chunk.signature == "def login(email: str, password: str) -> dict"
    assert chunk.doc == "Exchange credentials for a token."
    # 1 + if + (boolean `or`) + for
    assert chunk.complexity == 4
    assert chunk.loc == 7


def test_python_decorated_function_signature_excludes_decorator():
    src = b'@router.post("/login")\ndef login(x):\n    """Do it."""\n    return x\n'

    chunk = next(c for c in parse_source(src, "python") if c.name == "login")

    assert chunk.signature == "def login(x)"
    assert chunk.start_line == 1  # chunk still includes the decorator


def test_class_loc_covers_methods_but_content_does_not():
    src = b"class A:\n    x = 1\n\n    def f(self):\n        return 1\n\n    def g(self):\n        return 2\n"

    cls = next(c for c in parse_source(src, "python") if c.kind == "class")

    assert cls.loc == 8
    assert "def f" not in cls.content
    assert cls.signature == "class A"


def test_module_docstring_lands_on_the_module_chunk():
    src = b'"""Shared password helpers."""\nimport os\n\nX = 1\n'

    module = parse_source(src, "python")[0]

    assert module.kind == "module"
    assert module.doc == "Shared password helpers."


def test_javascript_jsdoc_signature_and_logical_operators():
    src = (
        b"/**\n * Verify the webhook signature.\n * @param {object} req\n */\n"
        b"function verify(req, res, next) {\n"
        b"  if (!req.sig || req.sig !== expected) { return res.end() }\n"
        b"  next()\n}\n"
        b"const add = (a, b) => a + b\n"
    )
    chunks = {c.name: c for c in parse_source(src, "javascript")}

    assert chunks["verify"].doc == "Verify the webhook signature."
    assert chunks["verify"].signature == "function verify(req, res, next)"
    assert chunks["verify"].complexity == 3  # 1 + if + ||
    assert chunks["add"].signature == "const add = (a, b)"


# ------------------------------------------------------- import resolution

PATHS = {
    "app/security.py",
    "app/routes/auth.py",
    "app/routes/__init__.py",
    "app/services/payments.py",
    "web/server.js",
    "web/lib/util.js",
    "web/lib/index.js",
}


def test_resolves_absolute_relative_and_package_python_imports():
    r = ImportResolver(PATHS)

    assert r.resolve("app/routes/auth.py", "app.security", "python") == "app/security.py"
    assert r.resolve("app/routes/auth.py", "app.routes", "python") == "app/routes/__init__.py"
    assert r.resolve("app/routes/auth.py", "..security", "python") == "app/security.py"
    assert r.resolve("app/routes/auth.py", ".", "python") == "app/routes/__init__.py"
    assert r.resolve("app/main.py", "app.routes.auth", "python") == "app/routes/auth.py"
    assert r.resolve("app/main.py", "fastapi", "python") is None


def test_resolves_javascript_relative_imports_only():
    assert resolve_import("web/server.js", "./lib/util", "javascript", PATHS) == "web/lib/util.js"
    assert resolve_import("web/server.js", "./lib", "javascript", PATHS) == "web/lib/index.js"
    assert resolve_import("web/server.js", "express", "javascript", PATHS) is None


def test_suffix_match_handles_a_subfolder_root_and_prefers_nearest():
    paths = {"svc-a/app/security.py", "svc-b/app/security.py", "svc-a/app/main.py"}

    assert resolve_import("svc-a/app/main.py", "app.security", "python", paths) == "svc-a/app/security.py"


def test_namespace_packages_are_first_party_not_dependencies():
    # no __init__.py anywhere, so `app.routes` resolves to no file
    r = ImportResolver({"app/routes/auth.py", "app/main.py"})

    assert r.resolve("app/main.py", "app.routes", "python") is None
    assert r.is_first_party("app") and r.is_first_party("routes")
    assert not r.is_first_party("fastapi")


def test_stdlib_name_does_not_resolve_to_another_services_file():
    """`import logging` must not become billing/app/core/logging.py."""
    paths = {
        "services/billing/app/core/logging.py",
        "services/billing/app/main.py",
        "services/auth/app/main.py",
    }
    r = ImportResolver(paths)

    assert r.resolve("services/auth/app/main.py", "logging", "python") is None
    assert r.resolve("services/billing/app/main.py", "logging", "python") is None
    # ...but the real package path still resolves from the right place
    assert (
        r.resolve("services/billing/app/main.py", "app.core.logging", "python")
        == "services/billing/app/core/logging.py"
    )
    assert r.resolve("services/auth/app/main.py", "app.core.logging", "python") is None


def test_each_service_resolves_its_own_app_package():
    paths = {
        "services/a/app/db.py",
        "services/b/app/db.py",
        "services/a/app/main.py",
        "services/b/app/main.py",
    }
    r = ImportResolver(paths)

    assert r.resolve("services/a/app/main.py", "app.db", "python") == "services/a/app/db.py"
    assert r.resolve("services/b/app/main.py", "app.db", "python") == "services/b/app/db.py"


def test_stdlib_names_are_never_first_party_even_with_a_local_file_of_that_name():
    r = ImportResolver({"services/x/app/core/logging.py"})

    assert not r.is_first_party("logging")
    assert r.is_first_party("core")


def test_test_paths_are_recognised():
    from app.insights import is_test_path

    for p in ("tests/test_x.py", "services/a/tests/unit/helpers.py", "app/test_api.py",
              "app/api_test.py", "conftest.py", "web/__tests__/a.js", "web/a.spec.ts"):
        assert is_test_path(p), p
    for p in ("app/contest.py", "app/latest.py", "app/testing_utils_prod.py", "app/routes/auth.py"):
        assert not is_test_path(p), p


def test_external_names_and_stdlib_classification():
    assert external_name("fastapi.APIRouter", "python") == "fastapi"
    assert external_name(".security", "python") is None
    assert external_name("@scope/pkg/sub", "javascript") == "@scope/pkg"
    assert is_stdlib("hashlib", "python")
    assert not is_stdlib("fastapi", "python")
    assert is_stdlib("fs", "javascript")
    assert is_stdlib("anything", "javascript", "node:thing")


# ---------------------------------------------------------------- summary


def test_describe_chunk_is_plain_language_and_flags_auth():
    facts = {
        "qualified_name": "login", "kind": "function", "file": "app/routes/auth.py",
        "start_line": 15, "end_line": 21, "doc": "Exchange credentials for a token.",
        "complexity": 4,
        "endpoints": [{"method": "POST", "path": "/auth/login",
                       "handles_authentication": True, "requires_auth": False}],
        "callees_internal": [{"name": "verify_password"}, {"name": "run_query"}],
        "callees_external": ["jwt.encode"],
        "callers": [],
    }

    text = " ".join(describe_chunk(facts))

    assert "`login` is a function in `app/routes/auth.py` (lines 15-21, 7 lines)" in text
    assert "Exchange credentials for a token." in text
    assert "`POST /auth/login`; it performs authentication" in text
    assert "2 functions in this repo" in text and "1 external call" in text
    assert "touches authentication code: `jwt.encode`, `verify_password`" in text
    assert "Complexity 4 (low)" in text


def test_complexity_labels():
    assert [complexity_label(n) for n in (1, 5, 6, 10, 11)] == ["low", "low", "moderate", "moderate", "high"]


# ------------------------------------------------------- DB-backed insights


@pytest.fixture
def shop(conn):
    stats = ingest_repo(conn, SHOP, HashingEmbedder())
    yield stats["repo_id"]
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()


def test_overview_summarises_the_repo_without_an_llm(shop):
    o = client.get(f"/repos/{shop}/overview").json()

    t = o["totals"]
    assert t["files"] == 13 and t["loc"] > 200
    assert t["endpoints"] == 17
    assert t["functions"] > 20 and t["classes"] >= 3
    assert t["internal_links"] > 5

    langs = {entry["language"]: entry for entry in o["languages"]}
    assert set(langs) == {"python", "javascript"}
    assert langs["python"]["loc"] > langs["javascript"]["loc"]

    # 5 /auth/* routes; 7 guarded business routes (orders x4, products POST,
    # admin x2); the HMAC-signed webhook is a known classifier miss -> public.
    assert o["auth"]["authentication"] == 5
    assert o["auth"]["protected"] == 7
    assert sum(o["auth"].values()) == t["endpoints"]

    third = {d["name"] for d in o["dependencies"]["third_party"]}
    assert {"fastapi", "jwt", "httpx", "psycopg"} <= third
    stdlib = {d["name"] for d in o["dependencies"]["stdlib"]}
    assert {"hashlib", "os"} <= stdlib
    assert "app" not in third  # first-party packages are not "dependencies"

    called = {h["name"]: h["fan_in"] for h in o["hotspots"]["most_called"]}
    assert called["run_query"] >= 3
    assert o["hotspots"]["most_complex"][0]["complexity"] >= 2
    assert o["hotspots"]["largest_files"][0]["loc"] >= o["hotspots"]["largest_files"][-1]["loc"]
    guard_names = {g["name"] for g in o["guards"]}
    assert {"get_current_user", "require_admin"} <= guard_names
    assert set(o["frameworks"]) == {"fastapi", "express"}


def test_module_graph_groups_by_directory_and_drills_in(shop):
    top = client.get(f"/repos/{shop}/graph/modules").json()

    ids = {n["id"] for n in top["nodes"]}
    assert {"app", "webhooks"} <= ids
    app_node = next(n for n in top["nodes"] if n["id"] == "app")
    assert app_node["kind"] == "dir" and app_node["files"] >= 10 and app_node["endpoints"] == 15

    inside = client.get(f"/repos/{shop}/graph/modules", params={"root": "app"}).json()
    labels = {n["label"] for n in inside["nodes"]}
    assert {"routes", "services", "security.py", "db.py"} <= labels
    pairs = {(e["source"], e["target"]) for e in inside["edges"]}
    assert ("app/routes", "app/security.py") in pairs  # routes import security helpers
    assert ("app/routes", "app/services") in pairs
    assert inside["breadcrumb"] == ["app"]


def test_module_graph_file_level_lists_files(shop):
    g = client.get(f"/repos/{shop}/graph/modules", params={"root": "app/routes", "level": "file"}).json()

    assert {n["label"] for n in g["nodes"]} == {"admin.py", "auth.py", "orders.py", "products.py"}
    assert all(n["kind"] == "file" for n in g["nodes"])
    assert client.get(f"/repos/{shop}/graph/modules", params={"level": "x"}).status_code == 400


def test_chunk_facts_include_callers_callees_and_summary(shop):
    sym = client.get(f"/repos/{shop}/symbols", params={"q": "verify_password"}).json()[0]

    f = client.get(f"/repos/{shop}/chunks/{sym['chunk_id']}/facts").json()

    assert f["signature"] == "def verify_password(raw: str, salt: bytes, expected: str) -> bool"
    assert f["complexity"] >= 1 and f["loc"] >= 2
    assert {"login"} <= {c["name"] for c in f["callers"]}
    assert "hash_password" in {c["name"] for c in f["callees_internal"]}
    assert "hmac.compare_digest" in f["callees_external"]
    assert any("It is called from" in s for s in f["summary"])


def test_chunk_facts_for_endpoint_handler_mention_the_route(shop):
    sym = client.get(f"/repos/{shop}/symbols", params={"q": "login"}).json()
    login = next(s for s in sym if s["file"] == "app/routes/auth.py")

    f = client.get(f"/repos/{shop}/chunks/{login['chunk_id']}/facts").json()

    assert f["doc"] == "Exchange an email and password for an access token."
    assert f["endpoints"][0]["path"] == "/auth/login"
    assert any("performs authentication" in s for s in f["summary"])


def test_file_info_lists_symbols_imports_and_importers(shop):
    info = client.get(f"/repos/{shop}/files/info", params={"path": "app/security.py"}).json()

    assert info["doc"] == "Password hashing and JWT helpers shared by every route module."
    names = {s["name"] for s in info["symbols"]}
    assert {"hash_password", "get_current_user", "require_admin"} <= names
    assert "jwt" in info["imports"]["third_party"]
    assert "hashlib" in info["imports"]["stdlib"]
    assert "app/routes/auth.py" in info["imported_by"]
    gcu = next(s for s in info["symbols"] if s["name"] == "get_current_user")
    assert gcu["fan_in"] >= 1 and gcu["signature"].startswith("def get_current_user")


def test_files_endpoint_carries_loc_and_complexity(shop):
    rows = {f["path"]: f for f in client.get(f"/repos/{shop}/files").json()}

    assert rows["app/security.py"]["loc"] > 30
    assert rows["app/security.py"]["complexity"] >= 5


def test_capabilities_never_raises_and_reports_llm_status():
    body = client.get("/capabilities").json()

    assert body["llm"]["status"] in ("ready", "unreachable", "error")
    assert "model" in body["llm"]
