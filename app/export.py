"""Compact, token-budgeted exports of a repository for use as LLM context.

Embeddings are only a *search index*; an LLM reads text, so the thing worth
exporting is the structured facts RepoMind already extracted (architecture,
routes with auth roles, signatures, docs, hot spots), packed into a budget.
That is typically a small fraction of the raw source, which is what keeps a
downstream model's token bill down. Nothing here calls a model.

Three things keep it honest and safe to hand to someone else's model:
  * scope:      export one folder/service in full detail instead of a thin
                slice of everything
  * redaction:  secret-looking text is removed and counted (best effort)
  * freshness:  files that changed on disk since indexing are reported
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg

from app.graph import list_endpoints
from app.ingest.walker import iter_source_files
from app.insights import fan_in_by_chunk, is_test_path, module_graph, repo_overview, under_prefix
from app.redact import Redactor

DETAILS = ("overview", "map", "source")
FORMATS = ("markdown", "json")
MIN_TOKENS, MAX_TOKENS, DEFAULT_TOKENS = 1_000, 200_000, 30_000

# Real tokenizers differ by model (roughly +-25% on code); 4 chars/token is the
# usual planning figure. Everything reported here is an *estimate*.
CHARS_PER_TOKEN = 4

MAX_SYMBOLS_PER_FILE = 60
MAX_SOURCE_LINES = 120
MAX_FRESHNESS_FILES = 3_000
# Shares of the room left after the essentials (overview, architecture, auth, hotspots):
FULL_ROUTES_SHARE = 0.6  # use the detailed route format if it fits in this share
ROUTES_CEILING = 0.5  # otherwise compact routes may take up to this share


# Typographic punctuation and emoji add tokens and noise without adding meaning,
# and break in some terminals. Text in other languages is left untouched.
_PUNCT = str.maketrans(
    {
        "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00a0": " ", "\u2022": "-", "\u2192": "->", "\u2190": "<-",
        "\u00d7": "x", "\u200b": "", "\ufeff": "",
    }
)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
_SPACES = re.compile(r"[ \t]{2,}")


def plain(text: str) -> str:
    """Normalise typographic punctuation and drop emoji."""
    if not text or text.isascii():
        return text
    return _SPACES.sub(" ", _EMOJI.sub("", text.translate(_PUNCT))).strip()


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
    focus: str
    overview: dict
    arch: dict
    endpoints: list[dict]
    files: list[_File]
    redactor: Redactor
    freshness: dict
    omitted_tests: int = 0
    key_chunks: list[int] = field(default_factory=list)


# ---------------------------------------------------------------- gathering


def _architecture(conn: psycopg.Connection, repo_id: int, start: str = "") -> dict:
    """Module graph, opened inside the folder that holds nearly all the code."""
    root, graph = start, module_graph(conn, repo_id, start, "dir")
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


def _freshness(conn: psycopg.Connection, repo_id: int, paths: list[str], focus: str = "") -> dict:
    """Which indexed files differ from what is on disk now (by content hash),
    and which supported files exist on disk that were never indexed."""
    repo_path, indexed_at = conn.execute(
        "SELECT path, indexed_at FROM repos WHERE id = %s", (repo_id,)
    ).fetchone()
    stamp = indexed_at.isoformat() if isinstance(indexed_at, datetime) else None
    root = Path(repo_path)
    if not root.is_dir():
        return {"available": False, "checked": 0, "changed": [], "changed_count": 0,
                "missing_count": 0, "new": [], "new_count": 0, "indexed_at": stamp}

    sha = dict(conn.execute("SELECT path, sha256 FROM files WHERE repo_id = %s", (repo_id,)).fetchall())
    changed: list[str] = []
    missing = checked = 0
    resolved_root = root.resolve()
    for rel in paths[:MAX_FRESHNESS_FILES]:
        target = (root / rel).resolve()
        if not target.is_relative_to(resolved_root) or not target.is_file():
            missing += 1
            continue
        checked += 1
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha.get(rel):
            changed.append(rel)
    new = [
        rel for rel, _, _ in iter_source_files(root)
        if rel not in sha and under_prefix(rel, focus) and not is_test_path(rel)
    ]
    return {"available": True, "checked": checked, "changed": changed[:10], "changed_count": len(changed),
            "missing_count": missing, "new": new[:10], "new_count": len(new), "indexed_at": stamp}


def _gather(conn: psycopg.Connection, repo_id: int, focus: str = "") -> _Plan:
    focus = focus.strip("/")
    name = conn.execute("SELECT name FROM repos WHERE id = %s", (repo_id,)).fetchone()[0]
    redactor = Redactor()
    overview = repo_overview(conn, repo_id, focus)
    endpoints = [
        e for e in list_endpoints(conn, repo_id)
        if under_prefix(e["file"], focus) and not is_test_path(e["file"])
    ]
    fan_in = fan_in_by_chunk(conn, repo_id)

    rows = [
        r for r in conn.execute(
            "SELECT id, path, language, loc FROM files WHERE repo_id = %s ORDER BY path", (repo_id,)
        ).fetchall()
        if under_prefix(r[1], focus)
    ]
    if not rows:
        raise ValueError(f"no indexed files under '{focus}'")
    in_scope = {r[0] for r in rows}

    module_docs = {
        fid: plain(redactor.clean(doc))
        for fid, doc in conn.execute(
            "SELECT file_id, doc FROM chunks WHERE repo_id = %s AND kind = 'module' AND doc <> ''",
            (repo_id,),
        ).fetchall()
        if fid in in_scope
    }
    symbols: dict[int, list[dict]] = {}
    for fid, cid, kind, qname, start, end, sig, doc, cx, loc in conn.execute(
        """
        SELECT file_id, id, kind, qualified_name, start_line, end_line, signature, doc, complexity, loc
        FROM chunks WHERE repo_id = %s AND kind <> 'module' ORDER BY file_id, start_line
        """,
        (repo_id,),
    ):
        if fid not in in_scope:
            continue
        symbols.setdefault(fid, []).append(
            {
                "chunk_id": cid, "kind": kind, "name": qname, "line": start, "end_line": end,
                "signature": plain(redactor.clean(sig or qname)), "doc": plain(redactor.clean(doc)),
                "complexity": cx, "loc": loc, "fan_in": fan_in.get(cid, 0),
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

    return _Plan(
        name, focus, overview, _architecture(conn, repo_id, focus), endpoints, files, redactor,
        _freshness(conn, repo_id, [r[1] for r in rows], focus), omitted, list(dict.fromkeys(key)),
    )


def _source_bodies(
    conn: psycopg.Connection, repo_id: int, ids: list[int], redactor: Redactor
) -> list[dict]:
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
        code = "\n".join(lines[:MAX_SOURCE_LINES]) + ("\n# ... truncated" if clipped else "")
        out.append(
            {"chunk_id": cid, "path": path, "language": lang, "name": qname, "line": line,
             "code": plain(redactor.clean(code))}
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


def _freshness_note(fr: dict) -> str:
    if not fr["available"]:
        return "> Freshness: the source folder is not mounted, so changes since indexing cannot be checked.\n"
    bad = fr["changed_count"] + fr["missing_count"] + fr["new_count"]
    if not bad:
        return ""
    names = ", ".join(f"`{p}`" for p in fr["changed"][:5])
    more = f" and {fr['changed_count'] - 5} more" if fr["changed_count"] > 5 else ""
    parts = []
    if fr["changed_count"]:
        parts.append(f"{fr['changed_count']} changed ({names}{more})")
    if fr["missing_count"]:
        parts.append(f"{fr['missing_count']} no longer on disk")
    if fr["new_count"]:
        parts.append(f"{fr['new_count']} new files not indexed yet")
    return f"> Warning: indexed files differ from disk: {'; '.join(parts)}. Re-run ingest for a fresh export.\n"


def _markdown(plan: _Plan, detail: str, budget: _Budget, bodies: list[dict]) -> tuple[str, dict]:
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
        f"{lang['language']} {round(100 * lang['loc'] / max(t['loc'], 1))}%" for lang in o["languages"]
    )
    must(f"# {plan.name}: codebase map" + (f" ({plan.focus}/ only)" if plan.focus else "") + "\n")
    must(
        "> Generated by RepoMind from static analysis (no LLM). Line numbers refer to the indexed "
        "revision. `callers N` = called from N places; `cx N` = complexity, shown when >= 6.\n"
    )
    if plan.focus:
        must(
            f"> Scope: `{plan.focus}/` only. Counts describe this folder; caller counts consider "
            "the whole repository.\n"
        )
    note = _freshness_note(plan.freshness)
    if note:
        must(note)
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
    guard_lines = [
        f"- `{g['name']}` ({g['file']}:{g['line']}), used {g.get('fan_in', 0)} times" for g in o["guards"][:6]
    ]
    if auth or guard_lines:
        txt = "## Authentication\n"
        txt += "".join(
            f"- `{e['method']} {e['path']}` -> {e['handler'] or 'inline'} ({e['file']}:{e['line']})\n"
            for e in auth[:12]
        )
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
        _closing(parts, plan, omitted)
        return "\n".join(parts), omitted

    # ---- endpoints: grouped by file, most important files first. Use the
    # detailed format when it fits; otherwise a compact one (no handler names),
    # so more routes survive a tight budget.
    by_file: dict[str, list[dict]] = {}
    for e in plan.endpoints:
        by_file.setdefault(e["file"], []).append(e)
    order = {f.path: i for i, f in enumerate(plan.files)}
    ordered = sorted(by_file, key=lambda p: order.get(p, 10**6))

    def route_blocks(compact: bool) -> list[tuple[int, str]]:
        blocks = []
        for path in ordered:
            eps = by_file[path]
            if compact:
                body = "".join(f"- {e['method']} {e['path']} [{_role(e)}]\n" for e in eps)
            else:
                body = "".join(
                    f"- {e['method']} {e['path']} -> {e['handler'] or 'inline'} [{_role(e)}]\n" for e in eps
                )
            blocks.append((len(eps), f"### {path}\n{body}"))
        return blocks

    if plan.endpoints:
        room = max(budget.limit - budget.used, 0)
        full_cost = sum(estimate_tokens(b) for _, b in route_blocks(False))
        compact = full_cost > room * FULL_ROUTES_SHARE
        header = "## HTTP endpoints\n" + (
            "(handler names left out to fit the budget; raise it or use a folder scope for more)\n"
            if compact else ""
        )
        cap = budget.used + (int(room * ROUTES_CEILING) if compact else room)
        chosen: list[str] = []
        spent = budget.used + estimate_tokens(header)
        for count, block in route_blocks(compact):
            cost = estimate_tokens(block)
            if spent + cost <= min(cap, budget.limit):
                chosen.append(block)
                spent += cost
            else:
                omitted["endpoints"] += count
        # the heading is only worth printing if at least one route made it
        if chosen and optional(header):
            for block in chosen:
                optional(block)
        else:
            omitted["endpoints"] = len(plan.endpoints)

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
            fence = b["language"] if b["language"] in ("python", "typescript") else "javascript"
            block = f"### {b['path']}:{b['line']} `{b['name']}`\n```{fence}\n{b['code']}\n```\n"
            if not optional(block):
                omitted["source"] += 1

    _closing(parts, plan, omitted)
    return "\n".join(parts), omitted


def _closing(parts: list[str], plan: _Plan, omitted: dict) -> None:
    if plan.omitted_tests:
        parts.append(f"\n_{plan.omitted_tests} test files were left out._\n")
    if plan.redactor.total:
        parts.append(f"\n_{plan.redactor.total} possible secrets were redacted from this export._\n")
    if any(omitted.values()):
        parts.append(
            "\n_Trimmed to fit the token budget: "
            + ", ".join(f"{v} {k}" for k, v in omitted.items() if v)
            + " omitted. Raise the budget, or export a single folder for more detail._\n"
        )


def _json(plan: _Plan, detail: str, budget: _Budget, bodies: list[dict]) -> tuple[str, dict]:
    o, t = plan.overview, plan.overview["totals"]
    omitted = {"endpoints": 0, "files": 0, "symbols": 0, "source": 0}
    dump = lambda x: json.dumps(x, separators=(",", ":"), ensure_ascii=False)  # noqa: E731
    doc: dict = {
        "repo": plan.name,
        "scope": plan.focus or None,
        "generated_by": "RepoMind static analysis (no LLM)",
        "freshness": {
            k: plan.freshness[k]
            for k in ("available", "changed_count", "missing_count", "new_count", "indexed_at")
        },
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
        "guards": [
            {"name": g["name"], "file": g["file"], "line": g["line"], "uses": g.get("fan_in", 0)}
            for g in o["guards"]
        ],
        "hotspots": {
            "most_called": [
                {"name": h["name"], "file": h["file"], "callers": h["fan_in"]}
                for h in o["hotspots"]["most_called"]
            ],
            "most_complex": [
                {"name": h["name"], "file": h["file"], "complexity": h["complexity"]}
                for h in o["hotspots"]["most_complex"]
            ],
        },
    }
    budget.force(dump(doc))

    if detail != "overview":
        order = {f.path: i for i, f in enumerate(plan.files)}
        ordered = sorted(plan.endpoints, key=lambda e: (order.get(e["file"], 10**6), e["line"]))
        detailed = [
            {"method": e["method"], "path": e["path"], "handler": e["handler"],
             "file": e["file"], "line": e["line"], "auth": _role(e)}
            for e in ordered
        ]
        # Detailed rows when they fit; otherwise grouped by file with no handler/line.
        room = max(budget.limit - budget.used, 0)
        if estimate_tokens(dump(detailed)) <= room * FULL_ROUTES_SHARE:
            doc["endpoints"] = detailed
            budget.force(dump(detailed))
        else:
            grouped: dict[str, list] = {}
            cap = budget.used + int(room * ROUTES_CEILING)
            for e in ordered:
                row = [e["method"], e["path"], _role(e)]
                if budget.used + estimate_tokens(dump(row)) > min(cap, budget.limit):
                    omitted["endpoints"] += 1
                    continue
                grouped.setdefault(e["file"], []).append(row)
                budget.force(dump(row))
            if grouped:
                doc["endpoints_by_file"] = grouped
                doc["endpoint_row"] = ["method", "path", "auth"]

        files_out = []
        for f in plan.files:
            item = {"path": f.path, "loc": f.loc, "doc": f.doc, "symbols": [
                {k: s[k] for k in ("signature", "doc", "line", "complexity", "fan_in")}
                for s in f.symbols[:MAX_SYMBOLS_PER_FILE]
            ]}
            if budget.add(dump(item)):
                files_out.append(item)
                continue
            stub = {"path": f.path, "loc": f.loc, "symbol_count": len(f.symbols)}
            if budget.add(dump(stub)):
                files_out.append(stub)
                omitted["symbols"] += len(f.symbols)
            else:
                omitted["files"] += 1
        doc["files"] = files_out

    if detail == "source":
        src = []
        for b in bodies:
            if budget.add(dump(b)):
                src.append(b)
            else:
                omitted["source"] += 1
        doc["key_source"] = src

    if plan.redactor.total:
        doc["redacted_secrets"] = plan.redactor.total
    if any(omitted.values()):
        doc["trimmed"] = {k: v for k, v in omitted.items() if v}
    return dump(doc), omitted


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
        content, omitted = _markdown(plan, detail, budget, bodies)
    else:
        content, omitted = _json(plan, detail, budget, bodies)
    tokens = estimate_tokens(content)
    return {
        "format": fmt,
        "detail": detail,
        "focus": plan.focus,
        "content": content,
        "estimated_tokens": tokens,
        "budget": max_tokens,
        "over_budget": tokens > max_tokens,  # only the unavoidable essentials can exceed it
        "truncated": any(omitted.values()),
        "omitted": omitted,
        "files_included": len(plan.files) - omitted["files"],
        "test_files_left_out": plan.omitted_tests,
        "redactions": plan.redactor.report(),
        "freshness": plan.freshness,
    }


def build_export(
    conn: psycopg.Connection,
    repo_id: int,
    *,
    detail: str = "map",
    max_tokens: int = DEFAULT_TOKENS,
    fmt: str = "markdown",
    focus: str = "",
) -> dict:
    _validate(detail, max_tokens, fmt)
    plan = _gather(conn, repo_id, focus)
    bodies = _source_bodies(conn, repo_id, plan.key_chunks, plan.redactor) if detail == "source" else []
    return _render(plan, bodies, detail, max_tokens, fmt)


def export_estimates(conn: psycopg.Connection, repo_id: int, focus: str = "") -> dict:
    """What each export level costs naturally, versus pasting the raw source.

    The repo is analysed once and rendered three times (gathering is the slow part)."""
    focus = focus.strip("/")
    raw_chars = conn.execute(
        """
        SELECT coalesce(sum(char_length(c.content)), 0)
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.kind IN ('function', 'method', 'class', 'module')
          AND (%s = '' OR f.path = %s OR starts_with(f.path, %s))
        """,
        (repo_id, focus, focus, focus + "/"),
    ).fetchone()[0]
    out = {"full_source_tokens": math.ceil(raw_chars / CHARS_PER_TOKEN), "chars_per_token": CHARS_PER_TOKEN}
    plan = _gather(conn, repo_id, focus)
    bodies = _source_bodies(conn, repo_id, plan.key_chunks, plan.redactor)
    for detail in DETAILS:
        res = _render(plan, bodies if detail == "source" else [], detail, MAX_TOKENS, "markdown")
        out[f"{detail}_tokens"] = res["estimated_tokens"]
    return out
