from pathlib import Path

from app.graph import classify
from app.ingest.analysis import analyze_source

API = Path(__file__).parent / "fixtures" / "api_repo"
SAMPLE = Path(__file__).parent / "fixtures" / "sample_repo"


def _endpoints(path: Path, language: str) -> dict[tuple[str, str], object]:
    result = analyze_source(path.read_bytes(), language)
    return {(e.method, e.path): e for e in result.endpoints}


def test_flask_route_with_methods():
    eps = _endpoints(SAMPLE / "auth.py", "python")

    assert list(eps) == [("POST", "/login")]
    assert eps[("POST", "/login")].handler_name == "login"
    assert eps[("POST", "/login")].framework == "flask"


def test_fastapi_routes_and_dependencies():
    eps = _endpoints(API / "fastapi_app.py", "python")

    assert set(eps) == {
        ("POST", "/auth/login"),
        ("GET", "/users/me"),
        ("GET", "/health"),
        ("DELETE", "/users/{user_id}"),
        ("GET", "/reports"),
    }
    assert eps[("GET", "/users/me")].framework == "fastapi"
    assert "Depends(get_current_user)" in eps[("GET", "/users/me")].signals
    assert "Depends(require_admin)" in eps[("DELETE", "/users/{user_id}")].signals
    assert eps[("GET", "/health")].signals == ()


def test_python_calls_skip_decorators_and_record_imports():
    result = analyze_source((API / "fastapi_app.py").read_bytes(), "python")

    callees = {c.callee_full for c in result.calls}
    assert "jwt.decode" in callees
    assert "app.post" not in callees  # decorator call is not a function call
    assert {"jwt", "fastapi"} <= set(result.imports)


def test_express_routes_middleware_and_router_use():
    eps = _endpoints(API / "express_app.js", "javascript")

    assert set(eps) == {
        ("POST", "/api/login"),
        ("GET", "/orders"),
        ("GET", "/ping"),
        ("GET", "/me"),
    }
    assert eps[("POST", "/api/login")].handler_name == "login"
    assert eps[("POST", "/api/login")].signals == ()  # router.use does not apply to `app`
    assert eps[("GET", "/orders")].signals == ("requireAuth",)  # via router.use
    assert eps[("GET", "/me")].signals == ("requireAuth",)  # inline handler, explicit middleware
    assert eps[("GET", "/me")].handler_name is None
    assert "res.json" in eps[("GET", "/me")].inline_calls


def test_javascript_imports_include_require():
    result = analyze_source((API / "express_app.js").read_bytes(), "javascript")

    assert {"express", "jsonwebtoken"} <= set(result.imports)
    assert all(c.callee_name != "require" for c in result.calls)


def test_classify_authentication_endpoint_is_not_marked_protected():
    c = classify("/auth/login", "login", [], ["verify_password", "jwt.encode"])

    assert c.handles_authentication
    assert not c.requires_auth


def test_classify_guarded_and_transitive():
    guarded = classify("/users/me", "me", ["Depends(get_current_user)"], [])
    transitive = classify("/reports", "reports", [], ["build_report", "get_current_user"])
    public = classify("/health", "health", [], [])

    assert guarded.requires_auth and not guarded.handles_authentication
    assert transitive.requires_auth
    assert not public.requires_auth and not public.handles_authentication
    assert public.evidence == []
