"""Deterministic repository insights: everything the UI shows to explain a
codebase *without* an LLM (structure, hotspots, dependencies, per-function facts)."""

import posixpath
import re
import sys
from collections import defaultdict

import psycopg

from app.graph import AUTH_CALL_RE, GUARD_RE, list_endpoints

# ------------------------------------------------------------------ imports

_NODE_BUILTINS = frozenset(
    "assert async_hooks buffer child_process cluster console constants crypto dgram dns domain "
    "events fs http http2 https inspector module net os path perf_hooks process punycode "
    "querystring readline repl stream string_decoder sys timers tls tty url util v8 vm "
    "worker_threads zlib".split()
)
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
_JS_EXTS = ("", ".js", ".jsx", ".mjs", ".cjs", "/index.js", "/index.jsx", "/index.mjs")


def external_name(module: str, language: str) -> str | None:
    """Top-level package of an import, or None for relative imports."""
    if module.startswith("."):
        return None
    if language == "javascript":
        module = module.removeprefix("node:")
        parts = module.split("/")
        return "/".join(parts[:2]) if module.startswith("@") and len(parts) > 1 else parts[0]
    return module.split(".")[0]


def is_stdlib(name: str, language: str, raw: str = "") -> bool:
    if language == "javascript":
        return raw.startswith("node:") or name in _NODE_BUILTINS
    return name in _STDLIB


class ImportResolver:
    """Resolve import strings to files of the indexed repo (heuristic)."""

    def __init__(self, paths: set[str]) -> None:
        self.paths = paths
        self._by_suffix: dict[str, list[str]] = defaultdict(list)
        # Every directory name and module stem in the repo: an unresolved import
        # whose top-level name is one of these is first-party (e.g. a namespace
        # package without __init__.py), not a third-party dependency.
        self._first_party: set[str] = set()
        for p in paths:
            parts = p.split("/")
            self._first_party.update(parts[:-1])
            self._first_party.add(parts[-1].rsplit(".", 1)[0])
            if not p.endswith(".py"):
                continue
            stem = p[:-3]
            stem = stem.removesuffix("/__init__") if stem.endswith("/__init__") else stem
            parts = stem.split("/")
            for i in range(len(parts)):
                self._by_suffix[".".join(parts[i:])].append(p)

    def resolve(self, importer: str, module: str, language: str) -> str | None:
        here = posixpath.dirname(importer)
        if language == "javascript":
            if not module.startswith("."):
                return None
            target = posixpath.normpath(posixpath.join(here, module))
            for ext in _JS_EXTS:
                if target + ext in self.paths:
                    return target + ext
            return None

        level = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".")
        if level:
            base = here
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            target = posixpath.join(base, *rest.split(".")) if rest else base
            for cand in (target + ".py", posixpath.join(target, "__init__.py")):
                if cand in self.paths:
                    return cand
            return None

        matches = self._by_suffix.get(rest, [])
        # An absolute import is only valid relative to a *source root*: the
        # directory above the matched module must be the importer's own
        # directory or one of its ancestors (repo root, a service root, ...).
        # Without this, `import logging` resolved to some other service's
        # app/core/logging.py just because the file name matched.
        tail = rest.replace(".", "/")
        usable = []
        for p in matches:
            stem = p[: -len("/__init__.py")] if p.endswith("/__init__.py") else p[:-3]
            prefix = stem[: len(stem) - len(tail)].rstrip("/")
            if stem.endswith(tail) and (prefix == "" or importer.startswith(prefix + "/")):
                usable.append(p)
        matches = usable
        if not matches:
            return None

        def shared(p: str) -> int:
            a, b = p.split("/"), importer.split("/")
            n = 0
            while n < min(len(a), len(b)) - 1 and a[n] == b[n]:
                n += 1
            return n

        # nearest to the importer wins; ties go to the shortest path
        return max(matches, key=lambda p: (shared(p), -len(p)))


    def is_first_party(self, name: str) -> bool:
        if name in _STDLIB:
            return False  # a local logging.py does not turn `import logging` first-party
        return name in self._first_party


def resolve_import(importer: str, module: str, language: str, paths: set[str]) -> str | None:
    return ImportResolver(paths).resolve(importer, module, language)


# --------------------------------------------------------------- vocabulary


_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)(test_[^/]*|[^/]*_test\.py|conftest\.py)$|\.(test|spec)\.[jt]sx?$")


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def complexity_label(value: int) -> str:
    if value <= 5:
        return "low"
    if value <= 10:
        return "moderate"
    return "high"


def describe_chunk(f: dict) -> list[str]:
    """Plain-language facts about one function/class, built from static analysis
    only, so it works with no LLM. Each item is a self-contained sentence."""
    out: list[str] = []
    span = f["end_line"] - f["start_line"] + 1
    noun = {"method": "method", "class": "class"}.get(f["kind"], "function")
    out.append(
        f"`{f['qualified_name']}` is a {noun} in `{f['file']}` "
        f"(lines {f['start_line']}-{f['end_line']}, {span} line{'s' if span != 1 else ''})."
    )
    if f.get("doc"):
        out.append(f"Its documentation says: “{f['doc']}”")

    for e in f.get("endpoints", []):
        if e["handles_authentication"]:
            role = "it performs authentication"
        elif e["requires_auth"]:
            role = "it is protected by authentication"
        else:
            role = "no authentication was detected on it"
        out.append(f"It handles the route `{e['method']} {e['path']}`; {role}.")

    internal, external = f.get("callees_internal", []), f.get("callees_external", [])
    if internal or external:
        parts = []
        if internal:
            names = ", ".join(f"`{c['name']}`" for c in internal[:5])
            more = f" and {len(internal) - 5} more" if len(internal) > 5 else ""
            parts.append(f"{len(internal)} function{'s' if len(internal) != 1 else ''} in this repo ({names}{more})")
        if external:
            names = ", ".join(f"`{c}`" for c in external[:5])
            more = f" and {len(external) - 5} more" if len(external) > 5 else ""
            parts.append(f"{len(external)} external call{'s' if len(external) != 1 else ''} ({names}{more})")
        out.append("It calls " + " and ".join(parts) + ".")
    else:
        out.append("It makes no calls to other indexed functions.")

    callers = f.get("callers", [])
    if callers:
        names = ", ".join(f"`{c['name']}`" for c in callers[:5])
        more = f" and {len(callers) - 5} more" if len(callers) > 5 else ""
        out.append(f"It is called from {len(callers)} place{'s' if len(callers) != 1 else ''}: {names}{more}.")
    elif not f.get("endpoints"):
        out.append("Nothing else in the index calls it, so it is an entry point, a callback, or unused.")

    authish = [c for c in external if AUTH_CALL_RE.search(c)] + [
        c["name"] for c in internal if AUTH_CALL_RE.search(c["name"])
    ]
    if authish:
        out.append("It touches authentication code: " + ", ".join(f"`{a}`" for a in dict.fromkeys(authish)) + ".")

    c = f.get("complexity", 0)
    if c:
        out.append(f"Complexity {c} ({complexity_label(c)}): {max(c - 1, 0)} branch point{'s' if c != 2 else ''}.")
    return out


# ----------------------------------------------------------------- overview


def _fan_in(conn: psycopg.Connection, repo_id: int) -> dict[int, int]:
    rows = conn.execute(
        """
        SELECT callee_chunk_id, count(DISTINCT caller_chunk_id)
        FROM call_edges
        WHERE repo_id = %s AND callee_chunk_id IS NOT NULL AND caller_chunk_id <> callee_chunk_id
        GROUP BY callee_chunk_id
        """,
        (repo_id,),
    ).fetchall()
    return {cid: n for cid, n in rows}


def repo_overview(conn: psycopg.Connection, repo_id: int) -> dict:
    files = conn.execute(
        "SELECT id, path, language, loc FROM files WHERE repo_id = %s ORDER BY path", (repo_id,)
    ).fetchall()
    paths = {p for _, p, _, _ in files}

    kinds = dict(
        conn.execute(
            "SELECT kind, count(*) FROM chunks WHERE repo_id = %s GROUP BY kind", (repo_id,)
        ).fetchall()
    )
    by_language: dict[str, dict] = {}
    for _, _, lang, loc in files:
        entry = by_language.setdefault(lang, {"language": lang, "files": 0, "loc": 0})
        entry["files"] += 1
        entry["loc"] += loc

    endpoints = list_endpoints(conn, repo_id)
    auth = {
        "authentication": sum(e["handles_authentication"] for e in endpoints),
        "protected": sum(e["requires_auth"] and not e["handles_authentication"] for e in endpoints),
        "public": sum(not e["handles_authentication"] and not e["requires_auth"] for e in endpoints),
    }

    fan_in = _fan_in(conn, repo_id)
    funcs = conn.execute(
        """
        SELECT c.id, c.name, c.qualified_name, f.path, c.start_line, c.complexity, c.loc, c.doc
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.kind IN ('function', 'method')
        """,
        (repo_id,),
    ).fetchall()

    def item(row, **extra) -> dict:
        cid, name, qualified, path, line, cx, loc, doc = row
        return {
            "chunk_id": cid, "name": qualified, "file": path, "line": line,
            "complexity": cx, "loc": loc, "doc": doc, **extra,
        }

    # Hotspots are about the product code, so test files are left out of them.
    funcs = [r for r in funcs if not is_test_path(r[3])]
    most_called = [
        item(r, fan_in=fan_in[r[0]])
        for r in sorted(funcs, key=lambda r: (-fan_in.get(r[0], 0), r[2]))
        if fan_in.get(r[0], 0) > 0
    ][:8]
    most_complex = [
        item(r, label=complexity_label(r[5]))
        for r in sorted(funcs, key=lambda r: (-r[5], -r[6], r[2]))
        if r[5] > 1
    ][:8]
    guards = [
        item(r, fan_in=fan_in.get(r[0], 0))
        for r in sorted(funcs, key=lambda r: (-fan_in.get(r[0], 0), r[2]))
        if (AUTH_CALL_RE.search(r[1]) or GUARD_RE.search(r[1]))
    ][:8]
    largest = sorted((f for f in files if not is_test_path(f[1])), key=lambda f: -f[3])[:8]

    # dependencies
    resolver = ImportResolver(paths)
    file_lang = {fid: lang for fid, _, lang, _ in files}
    file_path = {fid: p for fid, p, _, _ in files}
    third: dict[str, set[int]] = defaultdict(set)
    std: dict[str, set[int]] = defaultdict(set)
    internal_links: set[tuple[str, str]] = set()
    for fid, module in conn.execute(
        "SELECT file_id, module FROM file_imports WHERE repo_id = %s", (repo_id,)
    ):
        lang = file_lang.get(fid)
        if lang is None:
            continue
        target = resolver.resolve(file_path[fid], module, lang)
        if target is not None:
            if target != file_path[fid]:
                internal_links.add((file_path[fid], target))
            continue
        name = external_name(module, lang)
        if not name or (lang == "python" and resolver.is_first_party(name)):
            continue
        (std if is_stdlib(name, lang, module) else third)[name].add(fid)

    def ranked(d: dict[str, set[int]]) -> list[dict]:
        return [
            {"name": k, "files": len(v)}
            for k, v in sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ][:14]

    total_loc = sum(f[3] for f in files)
    return {
        "totals": {
            "files": len(files),
            "loc": total_loc,
            "functions": kinds.get("function", 0) + kinds.get("method", 0),
            "classes": kinds.get("class", 0),
            "endpoints": len(endpoints),
            "internal_links": len(internal_links),
        },
        "languages": sorted(by_language.values(), key=lambda e: -e["loc"]),
        "auth": auth,
        "hotspots": {
            "most_called": most_called,
            "most_complex": most_complex,
            "largest_files": [{"path": p, "loc": loc, "language": lang} for _, p, lang, loc in largest],
        },
        "guards": guards,
        "dependencies": {"third_party": ranked(third), "stdlib": ranked(std)},
        "frameworks": sorted({e["framework"] for e in endpoints}),
    }


# ------------------------------------------------------------ module graph

MAX_MODULE_NODES = 60


def module_graph(conn: psycopg.Connection, repo_id: int, root: str = "", level: str = "dir") -> dict:
    """Dependency graph between directories (or files) from resolved imports.

    root=''  -> top-level directories; root='app' -> what is inside app/.
    level='file' lists individual files under `root` instead of grouping."""
    root = root.strip("/")
    rows = conn.execute(
        """
        SELECT f.id, f.path, f.language, f.loc,
               (SELECT count(*) FROM endpoints e WHERE e.file_id = f.id),
               (SELECT coalesce(sum(c.complexity), 0) FROM chunks c
                  WHERE c.file_id = f.id AND c.kind IN ('function', 'method')),
               (SELECT count(*) FROM chunks c
                  WHERE c.file_id = f.id AND c.kind IN ('function', 'method', 'class'))
        FROM files f WHERE f.repo_id = %s
        """,
        (repo_id,),
    ).fetchall()
    info = {p: (lang, loc, eps, cx, syms) for _, p, lang, loc, eps, cx, syms in rows}
    path_of = {fid: p for fid, p, *_ in rows}
    resolver = ImportResolver(set(info))

    prefix = f"{root}/" if root else ""

    def group_of(path: str) -> tuple[str, str] | None:
        """(node id, 'dir'|'file') for a file path, or None if outside root."""
        if prefix and not path.startswith(prefix):
            return None
        rel = path[len(prefix):]
        if level != "file" and "/" in rel:
            return f"{prefix}{rel.split('/')[0]}", "dir"
        return path, "file"

    edges: dict[tuple[str, str], int] = defaultdict(int)
    for fid, module in conn.execute(
        "SELECT file_id, module FROM file_imports WHERE repo_id = %s", (repo_id,)
    ):
        src_path = path_of.get(fid)
        if src_path is None:
            continue
        lang = info[src_path][0]
        target = resolver.resolve(src_path, module, lang)
        if target is None or target == src_path:
            continue
        a, b = group_of(src_path), group_of(target)
        if a is None or b is None or a[0] == b[0]:
            continue
        edges[(a[0], b[0])] += 1

    nodes: dict[str, dict] = {}
    for path, (lang, loc, eps, cx, syms) in info.items():
        g = group_of(path)
        if g is None:
            continue
        gid, kind = g
        node = nodes.setdefault(
            gid,
            {
                "id": gid,
                "kind": kind,
                "label": gid.rsplit("/", 1)[-1] or gid,
                "path": gid,
                "files": 0,
                "loc": 0,
                "endpoints": 0,
                "complexity": 0,
                "symbols": 0,
                "languages": [],
            },
        )
        node["files"] += 1
        node["loc"] += loc
        node["endpoints"] += eps
        node["complexity"] += cx
        node["symbols"] += syms
        if lang not in node["languages"]:
            node["languages"].append(lang)

    degree: dict[str, int] = defaultdict(int)
    for (a, b), w in edges.items():
        degree[a] += w
        degree[b] += w
    ordered = sorted(nodes.values(), key=lambda n: (-degree[n["id"]], -n["loc"], n["id"]))
    truncated = len(ordered) > MAX_MODULE_NODES
    kept = {n["id"] for n in ordered[:MAX_MODULE_NODES]}
    for n in nodes.values():
        n["degree"] = degree[n["id"]]

    return {
        "root": root,
        "level": level,
        "nodes": [n for n in ordered if n["id"] in kept],
        "edges": [
            {"id": f"{a}->{b}", "source": a, "target": b, "weight": w}
            for (a, b), w in sorted(edges.items())
            if a in kept and b in kept
        ],
        "truncated": truncated,
        "breadcrumb": root.split("/") if root else [],
    }


# ------------------------------------------------------------ chunk / file facts


def chunk_facts(conn: psycopg.Connection, repo_id: int, chunk_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT c.id, c.name, c.qualified_name, c.kind, f.path, f.id, f.language,
               c.start_line, c.end_line, c.signature, c.doc, c.complexity, c.loc
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.id = %s AND c.repo_id = %s
        """,
        (chunk_id, repo_id),
    ).fetchone()
    if row is None:
        return None
    cid, name, qualified, kind, path, file_id, lang, start, end, signature, doc, cx, loc = row

    callees = conn.execute(
        """
        SELECT DISTINCT ON (cc.id) cc.id, cc.qualified_name, f.path, cc.start_line
        FROM call_edges ce
        JOIN chunks cc ON cc.id = ce.callee_chunk_id
        JOIN files f ON f.id = cc.file_id
        WHERE ce.caller_chunk_id = %s AND cc.id <> %s
        ORDER BY cc.id
        """,
        (cid, cid),
    ).fetchall()
    externals = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT callee_full FROM call_edges
            WHERE caller_chunk_id = %s AND callee_chunk_id IS NULL AND callee_full LIKE '%%.%%'
            ORDER BY callee_full LIMIT 24
            """,
            (cid,),
        )
    ]
    callers = conn.execute(
        """
        SELECT DISTINCT ON (c.id) c.id, c.qualified_name, f.path, ce.line
        FROM call_edges ce
        JOIN chunks c ON c.id = ce.caller_chunk_id
        JOIN files f ON f.id = c.file_id
        WHERE ce.callee_chunk_id = %s AND c.id <> %s
        ORDER BY c.id
        LIMIT 24
        """,
        (cid, cid),
    ).fetchall()
    endpoints = [e for e in list_endpoints(conn, repo_id) if e["handler_chunk_id"] == cid]

    facts = {
        "chunk_id": cid,
        "name": name,
        "qualified_name": qualified,
        "kind": kind,
        "file": path,
        "language": lang,
        "start_line": start,
        "end_line": end,
        "signature": signature,
        "doc": doc,
        "complexity": cx,
        "complexity_label": complexity_label(cx) if cx else None,
        "loc": loc,
        "callees_internal": [
            {"chunk_id": i, "name": n, "file": p, "line": ln} for i, n, p, ln in callees
        ],
        "callees_external": externals,
        "callers": [{"chunk_id": i, "name": n, "file": p, "line": ln} for i, n, p, ln in callers],
        "endpoints": [
            {k: e[k] for k in ("id", "method", "path", "handles_authentication", "requires_auth", "evidence")}
            for e in endpoints
        ],
    }
    facts["summary"] = describe_chunk(facts)
    return facts


def file_info(conn: psycopg.Connection, repo_id: int, path: str) -> dict | None:
    row = conn.execute(
        "SELECT id, language, loc FROM files WHERE repo_id = %s AND path = %s", (repo_id, path)
    ).fetchone()
    if row is None:
        return None
    file_id, lang, loc = row

    chunks = conn.execute(
        """
        SELECT c.id, c.kind, c.qualified_name, c.start_line, c.end_line, c.signature,
               c.doc, c.complexity, c.loc
        FROM chunks c WHERE c.file_id = %s ORDER BY c.start_line
        """,
        (file_id,),
    ).fetchall()
    fan_in = _fan_in(conn, repo_id)
    module_doc = next((c[6] for c in chunks if c[1] == "module"), "")

    all_paths = {
        r[0] for r in conn.execute("SELECT path FROM files WHERE repo_id = %s", (repo_id,))
    }
    resolver = ImportResolver(all_paths)
    internal: set[str] = set()
    external: set[str] = set()
    stdlib: set[str] = set()
    for (module,) in conn.execute("SELECT module FROM file_imports WHERE file_id = %s", (file_id,)):
        target = resolver.resolve(path, module, lang)
        if target is not None:
            if target != path:
                internal.add(target)
            continue
        name = external_name(module, lang)
        if name and not (lang == "python" and resolver.is_first_party(name)):
            (stdlib if is_stdlib(name, lang, module) else external).add(name)

    importers: set[str] = set()
    for fp, module, flang in conn.execute(
        """
        SELECT f.path, i.module, f.language FROM file_imports i
        JOIN files f ON f.id = i.file_id WHERE i.repo_id = %s AND f.id <> %s
        """,
        (repo_id, file_id),
    ):
        if resolver.resolve(fp, module, flang) == path:
            importers.add(fp)

    endpoints = conn.execute(
        "SELECT method, path, line FROM endpoints WHERE file_id = %s ORDER BY line", (file_id,)
    ).fetchall()

    return {
        "path": path,
        "language": lang,
        "loc": loc,
        "doc": module_doc,
        "symbols": [
            {
                "chunk_id": cid, "kind": kind, "name": qualified, "start_line": s, "end_line": e,
                "signature": sig, "doc": doc, "complexity": cx, "loc": ln,
                "fan_in": fan_in.get(cid, 0),
            }
            for cid, kind, qualified, s, e, sig, doc, cx, ln in chunks
            if kind != "module"
        ],
        "imports": {
            "internal": sorted(internal),
            "third_party": sorted(external),
            "stdlib": sorted(stdlib),
        },
        "imported_by": sorted(importers),
        "endpoints": [{"method": m, "path": p, "line": ln} for m, p, ln in endpoints],
    }
