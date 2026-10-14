"""Compact, token-budgeted exports of a repository for use as LLM context.

Embeddings are only a *search index*; an LLM reads text, so the thing worth
exporting is the structured facts RepoMind already extracted (architecture,
routes with auth roles, signatures, docs, hot spots), packed into a budget.
That is typically a small fraction of the raw source, which is what keeps a
downstream model's token bill down. Nothing here calls a model."""

import json
import math
from dataclasses import dataclass, field

import psycopg

from app.graph import list_endpoints
from app.insights import fan_in_by_chunk, is_test_path, module_graph, repo_overview

DETAILS = ("overview", "map", "source")
FORMATS = ("markdown", "json")
MIN_TOKENS, MAX_TOKENS, DEFAULT_TOKENS = 1_000, 200_000, 30_000

# Real tokenizers differ by model (roughly +-25% on code); 4 chars/token is the
# usual planning figure. Everything reported here is an *estimate*.
CHARS_PER_TOKEN = 4

MAX_SYMBOLS_PER_FILE = 60
MAX_SOURCE_LINES = 120


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def fits(self, text: str) -> bool:
        return self.used + estimate_tokens(text) <= self.limit

    def add(self, text: str) -> bool:
        if not self.fits(text):
            return False
        self.used += estimate_tokens(text)
        return True

    def force(self, text: str) -> None:
        self.used += estimate_tokens(text)


@dataclass
class _File:
    path: str
    language: str
    loc: int
    doc: str
    endpoints: int
    symbols: list[dict]
    score: float = 0.0


@dataclass
class _Plan:
    name: str
    overview: dict
    arch: dict
    endpoints: list[dict]
    files: list[_File]
    omitted_tests: int = 0
    key_chunks: list[int] = field(default_factory=list)


# ---------------------------------------------------------------- gathering


def _architecture(conn: psycopg.Connection, repo_id: int) -> dict:
    """Module graph, opened inside the folder that holds nearly all the code."""
    root, graph = "", module_graph(conn, repo_id, "", "dir")
    for _ in range(2):
        nodes = graph["nodes"]
        total = sum(n["loc"] for n in nodes)
        top = max(nodes, key=lambda n: n["loc"], default=None)
        if top and top["kind"] == "dir" and total and top["loc"] / total >= 0.85 and len(nodes) <= 6:
            root = top["path"]
            graph = module_graph(conn, repo_id, root, "dir")
        else:
            break
    return {**graph, "root": root}


def _gather(conn: psycopg.Connection, repo_id: int) -> _Plan:
    name = conn.execute("SELECT name FROM repos WHERE id = %s", (repo_id,)).fetchone()[0]
    overview = repo_overview(conn, repo_id)
    endpoints = [e for e in list_endpoints(conn, repo_id) if not is_test_path(e["file"])]
    fan_in = fan_in_by_chunk(conn, repo_id)

    rows = conn.execute(
        "SELECT id, path, language, loc FROM files WHERE repo_id = %s ORDER BY path", (repo_id,)
    ).fetchall()
    module_docs = dict(
        conn.execute(
            "SELECT file_id, doc FROM chunks WHERE repo_id = %s AND kind = 'module' AND doc <> ''",
            (repo_id,),
        ).fetchall()
    )
    symbols: dict[int, list[dict]] = {}
    for fid, cid, kind, qname, start, end, sig, doc, cx, loc in conn.execute(
        """
        SELECT file_id, id, kind, qualified_name, start_line, end_line, signature, doc, complexity, loc
        FROM chunks WHERE repo_id = %s AND kind <> 'module' ORDER BY file_id, start_line
        """,
        (repo_id,),
    ):
        symbols.setdefault(fid, []).append(
            {
                "chunk_id": cid, "kind": kind, "name": qname, "line": start, "end_line": end,
                "signature": sig or qname, "doc": doc, "complexity": cx, "loc": loc,
                "fan_in": fan_in.get(cid, 0),
            }
        )

    ep_count: dict[str, int] = {}
    for e in endpoints:
        ep_count[e["file"]] = ep_count.get(e["file"], 0) + 1

    files, omitted = [], 0
    for fid, path, lang, loc in rows:
        if is_test_path(path):
            omitted += 1
            continue
        syms = symbols.get(fid, [])
        f = _File(path, lang, loc, module_docs.get(fid, ""), ep_count.get(path, 0), syms)
        # importance: routes first, then how depended-upon its code is, then size
        f.score = f.endpoints * 5 + sum(s["fan_in"] for s in syms) + loc / 200
        files.append(f)
    files.sort(key=lambda f: (-f.score, f.path))

    # chunks worth showing as source: handlers (auth first), hubs, guards, hairy code
    key: list[int] = []
    rank = {True: 0, False: 1}
    for e in sorted(endpoints, key=lambda e: (rank[e["handles_authentication"]], not e["requires_auth"])):
        if e["handler_chunk_id"]:
            key.append(e["handler_chunk_id"])
    key += [h["chunk_id"] for h in overview["hotspots"]["most_called"]]
    key += [h["chunk_id"] for h in overview["guards"]]
    key += [h["chunk_id"] for h in overview["hotspots"]["most_complex"]]

    return _Plan(name, overview, _architecture(conn, repo_id), endpoints, files, omitted,
                 list(dict.fromkeys(key)))


def _source_bodies(conn: psycopg.Connection, repo_id: int, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = {
        r[0]: r
        for r in conn.execute(
            """
            SELECT c.id, f.path, f.language, c.qualified_name, c.start_line, c.content
            FROM chunks c JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s AND c.id = ANY(%s)
            """,
            (repo_id, ids),
        )
    }
    out = []
    for cid in ids:
        if cid not in rows or is_test_path(rows[cid][1]):
            continue
        _, path, lang, qname, line, content = rows[cid]
        lines = content.splitlines()
        clipped = len(lines) > MAX_SOURCE_LINES
        out.append(
            {
                "chunk_id": cid, "path": path, "language": lang, "name": qname, "line": line,
                "code": "\n".join(lines[:MAX_SOURCE_LINES]) + ("\n# ... truncated" if clipped else ""),
            }
        )
    return out


# ---------------------------------------------------------------- rendering


def _role(e: dict) -> str:
    if e["handles_authentication"]:
        return "auth"
    return "protected" if e["requires_auth"] else "public"


def _symbol_line(s: dict) -> str:
    tags = [f"L{s['line']}"]
    if s["complexity"] >= 6:
        tags.append(f"cx {s['complexity']}")
    if s["fan_in"] >= 2:
        tags.append(f"callers {s['fan_in']}")
    doc = f" - {s['doc']}" if s["doc"] else ""
    return f"- `{s['signature']}`{doc} [{', '.join(tags)}]"


def _markdown(plan: _Plan, detail: str, budget: _Budget, bodies: list[dict], gen_note: bool) -> tuple[str, dict]:
    o, t = plan.overview, plan.overview["totals"]
    omitted = {"endpoints": 0, "files": 0, "symbols": 0, "source": 0}
    parts: list[str] = []

    def must(text: str) -> None:
        parts.append(text)
        budget.force(text)

    def optional(text: str) -> bool:
        if budget.add(text):
            parts.append(text)
            return True
        return False

    langs = ", ".join(
        f"{l['language']} {round(100 * l['loc'] / max(t['loc'], 1))}%" for l in o["languages"]  # noqa: E741
    )
    must(f"# {plan.name}: codebase map\n")
    if gen_note:
        must(
            "> Generated by RepoMind from static analysis (no LLM). Line numbers refer to the indexed "
            "revision. `callers N` = called from N places; `cx N` = complexity, shown when >= 6.\n"
        )
    must(
        "## Overview\n"
        f"- {t['files']} files | {t['loc']:,} lines | {t['functions']:,} functions | {t['classes']:,} classes"
        f" | {t['endpoints']} HTTP endpoints\n"
        f"- Languages: {langs or 'n/a'}\n"
        f"- Frameworks: {', '.join(o['frameworks']) or 'none detected'}\n"
        f"- Auth surface: {o['auth']['authentication']} perform authentication, {o['auth']['protected']} "
        f"protected, {o['auth']['public']} with no auth signal detected\n"
    )

    arch = plan.arch
    scope = f" under `{arch['root']}/`" if arch["root"] else ""
    lines = [f"## Architecture{scope}"]
    for n in sorted(arch["nodes"], key=lambda n: -n["loc"]):
        routes = f", {n['endpoints']} routes" if n["endpoints"] else ""
        kind = "/" if n["kind"] == "dir" else ""
        lines.append(f"- `{n['label']}{kind}`: {n['loc']:,} lines, {n['files']} files{routes}")
    if arch["edges"]:
        lines.append("\nImports (importer -> imported, count):")
        for e in sorted(arch["edges"], key=lambda e: -e["weight"])[:25]:
            lines.append(f"- `{e['source'].split('/')[-1]}` -> `{e['target'].split('/')[-1]}` ({e['weight']})")
    elif len(arch["nodes"]) > 1:
        lines.append("\nThese modules do not import each other.")
    must("\n".join(lines) + "\n")

    deps = o["dependencies"]["third_party"]
    if deps:
        must("## Third-party dependencies\n" + ", ".join(f"{d['name']} ({d['files']})" for d in deps) + "\n")

    auth = [e for e in plan.endpoints if e["handles_authentication"]]
    guard_lines = [f"- `{g['name']}` ({g['file']}:{g['line']}), used {g.get('fan_in', 0)} times" for g in o["guards"][:6]]
    if auth or guard_lines:
        txt = "## Authentication\n"
        txt += "".join(f"- `{e['method']} {e['path']}` -> {e['handler'] or 'inline'} ({e['file']}:{e['line']})\n" for e in auth[:12])
        if len(auth) > 12:
            txt += f"- ... and {len(auth) - 12} more authentication endpoints\n"
        if guard_lines:
            txt += "Guards:\n" + "\n".join(guard_lines) + "\n"
        must(txt)

    hot = o["hotspots"]
    hs = ["## Hotspots"]
    if hot["most_called"]:
        hs.append("Most called: " + ", ".join(f"`{h['name']}` ({h['fan_in']})" for h in hot["most_called"][:6]))
    if hot["most_complex"]:
        hs.append("Most complex: " + ", ".join(f"`{h['name']}` (cx {h['complexity']})" for h in hot["most_complex"][:6]))
    if hot["largest_files"]:
        hs.append("Largest files: " + ", ".join(f"`{f['path']}` ({f['loc']})" for f in hot["largest_files"][:5]))
    if len(hs) > 1:
        must("\n".join(hs) + "\n")

    if detail == "overview":
        return "\n".join(parts), omitted

    # ---- endpoints: grouped by file, most important files first
    by_file: dict[str, list[dict]] = {}
    for e in plan.endpoints:
        by_file.setdefault(e["file"], []).append(e)
    order = {f.path: i for i, f in enumerate(plan.files)}
    ep_share = int(budget.limit * 0.45)
    if plan.endpoints:
        header = "## HTTP endpoints\n"
        if not optional(header):
            omitted["endpoints"] = len(plan.endpoints)
        else:
            for path in sorted(by_file, key=lambda p: order.get(p, 10**6)):
                eps = by_file[path]
                block = f"### {path}\n" + "".join(
                    f"- {e['method']} {e['path']} -> {e['handler'] or 'inline'} [{_role(e)}]\n" for e in eps
                )
                if budget.used + estimate_tokens(block) > min(ep_share, budget.limit):
                    omitted["endpoints"] += len(eps)
                    continue
                optional(block)

    # ---- files and signatures
    if plan.files:
        optional("## Files and symbols\n")
        for f in plan.files:
            syms = f.symbols
            head = f"### {f.path} ({f.loc} lines)" + (f" - {f.doc}" if f.doc else "") + "\n"
            body = "\n".join(_symbol_line(s) for s in syms[:MAX_SYMBOLS_PER_FILE])
            more = f"\n- ... {len(syms) - MAX_SYMBOLS_PER_FILE} more" if len(syms) > MAX_SYMBOLS_PER_FILE else ""
            block = head + (body + more + "\n" if syms else "")
            if optional(block):
                omitted["symbols"] += max(len(syms) - MAX_SYMBOLS_PER_FILE, 0)
                continue
            # no room for the full block: keep at least a one-line entry if possible
            stub = f"- `{f.path}` ({f.loc} lines, {len(syms)} symbols)\n"
            if not optional(stub):
                omitted["files"] += 1
            else:
                omitted["symbols"] += len(syms)

    # ---- key source (detail=source only)
    if detail == "source" and bodies:
        optional("## Key source\n")
        for b in bodies:
            fence = "python" if b["language"] == "python" else "javascript"
            block = f"### {b['path']}:{b['line']} `{b['name']}`\n```{fence}\n{b['code']}\n```\n"
            if not optional(block):
                omitted["source"] += 1

    if plan.omitted_tests:
        parts.append(f"\n_{plan.omitted_tests} test files were left out._\n")
    if any(omitted.values()):
        parts.append(
            "\n_Trimmed to fit the token budget: "
            + ", ".join(f"{v} {k}" for k, v in omitted.items() if v)
            + " omitted. Raise the budget for more._\n"
        )
    return "\n".join(parts), omitted


def _json(plan: _Plan, detail: str, budget: _Budget, bodies: list[dict]) -> tuple[str, dict]:
    o, t = plan.overview, plan.overview["totals"]
    omitted = {"endpoints": 0, "files": 0, "symbols": 0, "source": 0}
    doc: dict = {
        "repo": plan.name,
        "generated_by": "RepoMind static analysis (no LLM)",
        "totals": t,
        "languages": o["languages"],
        "frameworks": o["frameworks"],
        "auth_surface": o["auth"],
        "architecture": {
            "root": plan.arch["root"],
            "modules": [
                {k: n[k] for k in ("path", "kind", "loc", "files", "endpoints")} for n in plan.arch["nodes"]
            ],
            "imports": [
                {"from": e["source"], "to": e["target"], "count": e["weight"]} for e in plan.arch["edges"]
            ],
        },
        "dependencies": {"third_party": o["dependencies"]["third_party"]},
        "guards": [{"name": g["name"], "file": g["file"], "line": g["line"], "uses": g.get("fan_in", 0)} for g in o["guards"]],
        "hotspots": {
            "most_called": [{"name": h["name"], "file": h["file"], "callers": h["fan_in"]} for h in o["hotspots"]["most_called"]],
            "most_complex": [{"name": h["name"], "file": h["file"], "complexity": h["complexity"]} for h in o["hotspots"]["most_complex"]],
        },
    }
    budget.force(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))

    if detail != "overview":
        eps, ep_cap = [], int(budget.limit * 0.45)
        order = {f.path: i for i, f in enumerate(plan.files)}
        for e in sorted(plan.endpoints, key=lambda e: (order.get(e["file"], 10**6), e["line"])):
            item = {
                "method": e["method"], "path": e["path"], "handler": e["handler"],
                "file": e["file"], "line": e["line"], "auth": _role(e),
            }
            cost = estimate_tokens(json.dumps(item, separators=(",", ":")))
            if budget.used + cost <= min(ep_cap, budget.limit):
                budget.force(json.dumps(item, separators=(",", ":")))
                eps.append(item)
            else:
                omitted["endpoints"] += 1
        doc["endpoints"] = eps

        files_out = []
        for f in plan.files:
            item = {"path": f.path, "loc": f.loc, "doc": f.doc, "symbols": [
                {k: s[k] for k in ("signature", "doc", "line", "complexity", "fan_in")}
                for s in f.symbols[:MAX_SYMBOLS_PER_FILE]
            ]}
            text = json.dumps(item, separators=(",", ":"), ensure_ascii=False)
            if budget.add(text):
                files_out.append(item)
                continue
            stub = {"path": f.path, "loc": f.loc, "symbol_count": len(f.symbols)}
            if budget.add(json.dumps(stub, separators=(",", ":"))):
                files_out.append(stub)
                omitted["symbols"] += len(f.symbols)
            else:
                omitted["files"] += 1
        doc["files"] = files_out

    if detail == "source":
        src = []
        for b in bodies:
            if budget.add(json.dumps(b, separators=(",", ":"), ensure_ascii=False)):
                src.append(b)
            else:
                omitted["source"] += 1
        doc["key_source"] = src

    if any(omitted.values()):
        doc["trimmed"] = {k: v for k, v in omitted.items() if v}
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False), omitted


# --------------------------------------------------------------------- API


def _validate(detail: str, max_tokens: int, fmt: str) -> None:
    if detail not in DETAILS:
        raise ValueError(f"detail must be one of {DETAILS}")
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    if not MIN_TOKENS <= max_tokens <= MAX_TOKENS:
        raise ValueError(f"max_tokens must be between {MIN_TOKENS} and {MAX_TOKENS}")


def _render(plan: _Plan, bodies: list[dict], detail: str, max_tokens: int, fmt: str) -> dict:
    budget = _Budget(max_tokens)
    if fmt == "markdown":
        content, omitted = _markdown(plan, detail, budget, bodies, gen_note=True)
    else:
        content, omitted = _json(plan, detail, budget, bodies)
    tokens = estimate_tokens(content)
    return {
        "format": fmt,
        "detail": detail,
        "content": content,
        "estimated_tokens": tokens,
        "budget": max_tokens,
        "over_budget": tokens > max_tokens,  # only the unavoidable essentials can exceed it
        "truncated": any(omitted.values()),
        "omitted": omitted,
        "files_included": len(plan.files) - omitted["files"],
        "test_files_left_out": plan.omitted_tests,
    }


def build_export(
    conn: psycopg.Connection,
    repo_id: int,
    *,
    detail: str = "map",
    max_tokens: int = DEFAULT_TOKENS,
    fmt: str = "markdown",
) -> dict:
    _validate(detail, max_tokens, fmt)
    plan = _gather(conn, repo_id)
    bodies = _source_bodies(conn, repo_id, plan.key_chunks) if detail == "source" else []
    return _render(plan, bodies, detail, max_tokens, fmt)


def export_estimates(conn: psycopg.Connection, repo_id: int) -> dict:
    """What each export level costs naturally, versus pasting the raw source.

    The repo is analysed once and rendered three times (gathering is the slow part)."""
    raw_chars = conn.execute(
        """
        SELECT coalesce(sum(char_length(c.content)), 0)
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.kind IN ('function', 'method', 'class', 'module')
        """,
        (repo_id,),
    ).fetchone()[0]
    out = {"full_source_tokens": math.ceil(raw_chars / CHARS_PER_TOKEN), "chars_per_token": CHARS_PER_TOKEN}
    plan = _gather(conn, repo_id)
    bodies = _source_bodies(conn, repo_id, plan.key_chunks)
    for detail in DETAILS:
        res = _render(plan, bodies if detail == "source" else [], detail, MAX_TOKENS, "markdown")
        out[f"{detail}_tokens"] = res["estimated_tokens"]
    return out
