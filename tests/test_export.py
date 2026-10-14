"""Token-budgeted LLM-context export (needs Postgres)."""

import json
import shutil
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


# ------------------------------------------------------------------ scope


def test_focus_exports_one_folder_in_detail(shop):
    out = _export(shop, detail="map", max_tokens=60_000, focus="app/routes")
    md = out["content"]

    assert md.startswith("# shop_api: codebase map (app/routes/ only)")
    assert "Scope: `app/routes/` only" in md
    assert "- 4 files |" in md and "14 HTTP endpoints" in md
    assert "- POST /auth/login -> login [auth]" in md
    assert "/webhooks/stripe" not in md  # outside the folder
    assert "### app/security.py" not in md
    assert out["focus"] == "app/routes"
    assert out["truncated"] is False


def test_focus_accepts_slashes_and_rejects_unknown_folders(shop):
    assert _export(shop, focus="/app/routes/")["focus"] == "app/routes"
    r = client.get(f"/repos/{shop}/export", params={"focus": "nope/nothing"})
    assert r.status_code == 400 and "no indexed files" in r.json()["detail"]
    est = client.get(f"/repos/{shop}/export/estimate", params={"focus": "app/routes"}).json()
    whole = client.get(f"/repos/{shop}/export/estimate").json()
    assert est["full_source_tokens"] < whole["full_source_tokens"]


def test_focus_json_is_scoped_too(shop):
    data = json.loads(_export(shop, detail="map", max_tokens=60_000, format="json", focus="webhooks")["content"])

    assert data["scope"] == "webhooks"
    assert data["totals"]["endpoints"] == 2
    assert {f["path"] for f in data["files"]} == {"webhooks/server.js"}


# ----------------------------------------------------------- compact routes


def _routes_repo(root: Path, per_file: int = 30) -> None:
    for name in ("users", "orders", "items"):
        lines = ["from fastapi import APIRouter", f"router = APIRouter(prefix='/{name}')", ""]
        for i in range(per_file):
            lines += [f"@router.get('/r{i}')", f"def {name}_handler_{i}():", "    return {}", ""]
        (root / f"{name}.py").write_text("\n".join(lines))


@pytest.fixture
def many_routes(conn, tmp_path):
    root = tmp_path / "routes"
    root.mkdir()
    _routes_repo(root)  # 90 routes
    repo_id = ingest_repo(conn, root, HashingEmbedder())["repo_id"]
    yield repo_id
    conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
    conn.commit()


def test_tight_budget_uses_compact_routes_and_still_lists_some(many_routes):
    roomy = _export(many_routes, detail="map", max_tokens=60_000)["content"]
    tight = _export(many_routes, detail="map", max_tokens=1_700)["content"]

    assert "handler names left out" not in roomy
    assert "- GET /users/r3 -> users_handler_3 [public]" in roomy

    assert "handler names left out" in tight
    listed = [ln for ln in tight.splitlines() if ln.startswith("- GET /")]
    assert listed and all("->" not in ln and ln.endswith("[public]") for ln in listed)
    assert len(listed) >= 10


def test_compact_header_is_never_printed_without_routes(many_routes):
    for budget in (1_000, 1_100, 1_200):
        out = _export(many_routes, detail="map", max_tokens=budget)
        md = out["content"]
        listed = [ln for ln in md.splitlines() if ln.startswith("- GET /")]
        if "## HTTP endpoints" in md:
            assert listed, f"heading without any route at budget {budget}"
        else:
            assert out["omitted"]["endpoints"] == 90


def test_json_switches_to_grouped_rows_under_pressure(many_routes):
    detailed = json.loads(_export(many_routes, detail="map", max_tokens=60_000, format="json")["content"])
    assert len(detailed["endpoints"]) == 90 and "endpoints_by_file" not in detailed

    out = _export(many_routes, detail="map", max_tokens=1_700, format="json")
    data = json.loads(out["content"])

    assert "endpoints" not in data  # detailed rows would not fit
    assert data["endpoint_row"] == ["method", "path", "auth"]
    rows = [r for rows in data["endpoints_by_file"].values() for r in rows]
    assert len(rows) == 90 and all(len(r) == 3 for r in rows)  # compact keeps them all
    assert out["omitted"]["endpoints"] == 0


def test_json_trims_routes_when_even_the_compact_form_does_not_fit(many_routes):
    out = _export(many_routes, detail="map", max_tokens=1_150, format="json")
    data = json.loads(out["content"])

    rows = [r for rows in data.get("endpoints_by_file", {}).values() for r in rows]
    assert len(rows) < 90
    assert out["omitted"]["endpoints"] == 90 - len(rows)
    assert out["truncated"] is True


# ------------------------------------------------------------- redaction

SECRET_SOURCE = """\
DATABASE_URL = "postgresql://svc:Sup3rS3cretPw@db:5432/app"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


def connect(password: str = "hunter2-hunter2", retries: int = 3):
    \"\"\"Open a connection. Use token ghp_""" + "a" * 36 + """ in CI.\"\"\"
    api_key = "sk_live_""" + "b" * 24 + """"
    return DATABASE_URL, api_key, password


def first():
    return connect()


def second():
    return connect()
"""


def test_secrets_never_reach_the_export(conn, tmp_path):
    repo = tmp_path / "leaky"
    repo.mkdir()
    (repo / "db.py").write_text(SECRET_SOURCE)
    repo_id = ingest_repo(conn, repo, HashingEmbedder())["repo_id"]
    try:
        for detail in ("map", "source"):
            for fmt in ("markdown", "json"):
                out = _export(repo_id, detail=detail, max_tokens=60_000, format=fmt)
                for leaked in ("Sup3rS3cretPw", "AKIAIOSFODNN7EXAMPLE", "hunter2-hunter2", "ghp_aaaa", "sk_live_bbbb"):
                    assert leaked not in out["content"], (detail, fmt, leaked)
                # the map carries only the signature; `source` also carries the body
                assert out["redactions"]["total"] >= (3 if detail == "source" else 1)
        md = _export(repo_id, detail="source", max_tokens=60_000)["content"]
        assert "possible secrets were redacted" in md
        assert "def connect(" in md  # the code itself is still useful
    finally:
        conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
        conn.commit()


# --------------------------------------------------------------- freshness


@pytest.fixture
def shop_copy(conn, tmp_path):
    root = tmp_path / "shop"
    shutil.copytree(SHOP, root)
    stats = ingest_repo(conn, root, HashingEmbedder())
    yield stats["repo_id"], root
    conn.execute("DELETE FROM repos WHERE id = %s", (stats["repo_id"],))
    conn.commit()


def test_freshness_is_clean_right_after_indexing(shop_copy):
    repo_id, _ = shop_copy

    out = _export(repo_id)

    assert out["freshness"]["available"] is True
    assert out["freshness"]["changed_count"] == 0 and out["freshness"]["missing_count"] == 0
    assert "Warning: indexed files differ" not in out["content"]


def test_freshness_flags_changed_and_deleted_files(shop_copy):
    repo_id, root = shop_copy
    (root / "app" / "security.py").write_text("# edited\n" + (root / "app" / "security.py").read_text())
    (root / "app" / "models.py").unlink()

    out = _export(repo_id)

    fr = out["freshness"]
    assert fr["changed"] == ["app/security.py"] and fr["changed_count"] == 1
    assert fr["missing_count"] == 1
    assert "Warning: indexed files differ from disk" in out["content"]
    assert "1 changed (`app/security.py`)" in out["content"]
    assert "1 no longer on disk" in out["content"]


def test_freshness_says_when_the_folder_is_not_available(conn, shop_copy):
    repo_id, _ = shop_copy
    conn.execute("UPDATE repos SET path = %s WHERE id = %s", ("/definitely/not/mounted", repo_id))
    conn.commit()

    out = _export(repo_id)

    assert out["freshness"]["available"] is False
    assert "cannot be checked" in out["content"]


# ----------------------------------------------------------- plain text


def test_typographic_punctuation_and_emoji_are_normalised(conn, tmp_path):
    repo = tmp_path / "fancy"
    repo.mkdir()
    (repo / "m.py").write_text(
        '"""Module \u2014 does things."""\n\n\n'
        'def go(x):\n'
        '    """Run it \u2014 fast \U0001F680 and \u201csafe\u201d\u2026"""\n'
        "    return x\n\n\n"
        "def a():\n    return go(1)\n\n\n"
        "def b():\n    return go(2)\n",
        encoding="utf-8",
    )
    repo_id = ingest_repo(conn, repo, HashingEmbedder())["repo_id"]
    try:
        for detail in ("map", "source"):
            for fmt in ("markdown", "json"):
                text = _export(repo_id, detail=detail, max_tokens=60_000, format=fmt)["content"]
                assert text.isascii(), (detail, fmt, sorted({c for c in text if ord(c) > 127}))
        md = _export(repo_id, detail="map", max_tokens=60_000)["content"]
        assert "Run it - fast and" in md and '"safe"...' in md
        assert "Module - does things." in md
    finally:
        conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
        conn.commit()


def test_other_languages_are_preserved(conn, tmp_path):
    repo = tmp_path / "intl"
    repo.mkdir()
    (repo / "m.py").write_text(
        'def saluer():\n    """Dire bonjour \u00e0 l\u2019\u00e9quipe \u65e5\u672c\u8a9e."""\n    return 1\n',
        encoding="utf-8",
    )
    repo_id = ingest_repo(conn, repo, HashingEmbedder())["repo_id"]
    try:
        md = _export(repo_id, detail="map", max_tokens=60_000)["content"]
        assert "\u00e0" in md and "\u00e9quipe" in md and "\u65e5\u672c\u8a9e" in md  # accents + CJK kept
        assert "l'" in md  # but the typographic apostrophe became ASCII
    finally:
        conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
        conn.commit()


def test_freshness_reports_new_files_that_were_never_indexed(shop_copy):
    repo_id, root = shop_copy
    (root / "app" / "brand_new.py").write_text("def added():\n    return 1\n")
    (root / "notes.txt").write_text("not source")  # unsupported types are ignored

    out = _export(repo_id)

    fr = out["freshness"]
    assert fr["new"] == ["app/brand_new.py"] and fr["new_count"] == 1
    assert fr["changed_count"] == 0
    assert "1 new files not indexed yet" in out["content"]


def test_new_files_outside_the_scope_are_not_reported(shop_copy):
    repo_id, root = shop_copy
    (root / "webhooks" / "extra.js").write_text("module.exports = 1\n")

    scoped = _export(repo_id, focus="app/routes")
    whole = _export(repo_id)

    assert scoped["freshness"]["new_count"] == 0
    assert whole["freshness"]["new_count"] == 1
