"""Queries over the code graph: endpoint inventory with auth classification,
and callers / callees of a function."""

import re
from dataclasses import dataclass

import psycopg

from app.ingest.analysis import AUTH_CALL_PATTERN

# The endpoint exists to perform authentication (login, token issue, ...).
AUTHN_PATH_RE = re.compile(
    r"log_?in|log_?out|sign_?(in|up|out)|register|oauth|token|session|password|"
    r"\bauth\b|/auth|callback|refresh",
    re.I,
)
# The endpoint is guarded: decorators / middleware / dependencies that enforce auth.
GUARD_RE = re.compile(
    r"login_?required|jwt|auth_?required|requires?_?auth|require_?auth|authenticat|"
    r"authoriz|permission|roles?_?required|current_?user|verify_?token|protect|"
    r"guard|passport|bearer|oauth2|security|is_?admin|require_?admin",
    re.I,
)
AUTH_CALL_RE = re.compile(AUTH_CALL_PATTERN, re.I)

MAX_CALL_DEPTH = 3


@dataclass(frozen=True)
class Classification:
    handles_authentication: bool
    requires_auth: bool
    evidence: list[str]


def classify(
    path: str,
    handler_name: str | None,
    signals: list[str],
    call_names: list[str],
) -> Classification:
    """Pure heuristic: decide an endpoint's auth role and say why."""
    evidence: list[str] = []

    handles = False
    for label, text in (("path", path), ("handler", handler_name or "")):
        if text and AUTHN_PATH_RE.search(text):
            handles = True
            evidence.append(f"{label} '{text}' looks like an authentication endpoint")

    guards = [s for s in signals if GUARD_RE.search(s)]
    for s in guards:
        evidence.append(f"guarded by '{s}'")

    auth_calls = [c for c in call_names if AUTH_CALL_RE.search(c)]
    for c in auth_calls:
        evidence.append(f"calls '{c}'")

    # An auth endpoint calling jwt/bcrypt is *performing* auth, not requiring it.
    requires = bool(guards) or (bool(auth_calls) and not handles)
    return Classification(handles, requires, evidence)


def list_endpoints(conn: psycopg.Connection, repo_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.id, f.path, e.method, e.path, e.framework, e.line,
               e.handler_name, e.handler_chunk_id, e.signals, e.inline_calls
        FROM endpoints e JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = %s
        ORDER BY f.path, e.line, e.method
        """,
        (repo_id,),
    ).fetchall()

    # Names called (transitively, bounded depth) from each handler.
    reachable: dict[int, list[str]] = {}
    for root_id, callee_full in conn.execute(
        """
        WITH RECURSIVE reach(root, chunk_id, depth) AS (
            SELECT DISTINCT handler_chunk_id, handler_chunk_id, 0
            FROM endpoints WHERE repo_id = %s AND handler_chunk_id IS NOT NULL
            UNION
            SELECT r.root, ce.callee_chunk_id, r.depth + 1
            FROM reach r JOIN call_edges ce ON ce.caller_chunk_id = r.chunk_id
            WHERE ce.callee_chunk_id IS NOT NULL AND r.depth < %s
        )
        SELECT DISTINCT r.root, ce.callee_full
        FROM reach r JOIN call_edges ce ON ce.caller_chunk_id = r.chunk_id
        """,
        (repo_id, MAX_CALL_DEPTH),
    ):
        reachable.setdefault(root_id, []).append(callee_full)

    out = []
    for eid, file, method, path, framework, line, handler, handler_chunk, signals, inline in rows:
        calls = sorted(set(reachable.get(handler_chunk, [])) | set(inline))
        c = classify(path, handler, list(signals), calls)
        out.append(
            {
                "id": eid,
                "method": method,
                "path": path,
                "framework": framework,
                "file": file,
                "line": line,
                "handler": handler,
                "handler_chunk_id": handler_chunk,
                "handles_authentication": c.handles_authentication,
                "requires_auth": c.requires_auth,
                "evidence": c.evidence,
            }
        )
    return out


FLOW_MAX_NODES = 60
FLOW_MAX_EXTERNALS_PER_CALLER = 4


class FlowTargetNotFound(LookupError):
    pass


def _chunk_nodes(conn: psycopg.Connection, repo_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.qualified_name, c.kind, f.path, c.start_line, c.end_line
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.id = ANY(%s)
        """,
        (repo_id, ids),
    ).fetchall()
    return {
        cid: {
            "id": f"c:{cid}",
            "type": "method" if kind == "method" else ("class" if kind == "class" else "function"),
            "label": qualified,
            "name": name,
            "file": path,
            "start_line": start,
            "end_line": end,
            "chunk_id": cid,
            "auth_related": bool(AUTH_CALL_RE.search(name)),
        }
        for cid, name, qualified, kind, path, start, end in rows
    }


def call_flow(
    conn: psycopg.Connection,
    repo_id: int,
    *,
    endpoint_id: int | None = None,
    chunk_id: int | None = None,
    depth: int = 3,
    direction: str = "down",
    max_nodes: int = FLOW_MAX_NODES,
) -> dict:
    """Focused call graph around an endpoint or a function.

    direction: 'down' = what it calls, 'up' = who calls it (incl. routes that
    handle it), 'both'. Unresolved callees are kept as dashed 'external' nodes
    only when they look module-qualified (jwt.decode) or auth-related, so
    builtins don't clutter the picture. Never silently truncates: `truncated`
    is set when the node cap was hit."""
    depth = max(1, min(depth, 4))
    endpoints = {e["id"]: e for e in list_endpoints(conn, repo_id)}
    by_handler: dict[int, list[dict]] = {}
    for e in endpoints.values():
        if e["handler_chunk_id"] is not None:
            by_handler.setdefault(e["handler_chunk_id"], []).append(e)

    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], dict] = {}
    state = {"truncated": False}

    def add_node(node: dict) -> bool:
        if node["id"] in nodes:
            return True
        if len(nodes) >= max_nodes:
            state["truncated"] = True
            return False
        nodes[node["id"]] = node
        return True

    def add_edge(src: str, dst: str, line: int | None, kind: str = "calls") -> None:
        if src != dst and src in nodes and dst in nodes and (src, dst) not in edges:
            edges[(src, dst)] = {"id": f"{src}->{dst}", "source": src, "target": dst,
                                 "line": line, "kind": kind}

    def endpoint_node(e: dict) -> dict:
        return {
            "id": f"e:{e['id']}",
            "type": "endpoint",
            "label": f"{e['method']} {e['path']}",
            "method": e["method"],
            "path": e["path"],
            "file": e["file"],
            "start_line": e["line"],
            "end_line": e["line"],
            "endpoint_id": e["id"],
            "handles_authentication": e["handles_authentication"],
            "requires_auth": e["requires_auth"],
            "evidence": e["evidence"],
        }

    def external_node(full: str) -> dict:
        return {"id": f"x:{full}", "type": "external", "label": full,
                "auth_related": bool(AUTH_CALL_RE.search(full))}

    def keep_external(full: str) -> bool:
        return "." in full or bool(AUTH_CALL_RE.search(full))

    # ---- root
    if endpoint_id is not None:
        ep = endpoints.get(endpoint_id)
        if ep is None:
            raise FlowTargetNotFound(f"endpoint {endpoint_id} not found")
        add_node(endpoint_node(ep))
        root_id = f"e:{endpoint_id}"
        root_chunk = ep["handler_chunk_id"]
        if root_chunk is not None:
            info = _chunk_nodes(conn, repo_id, [root_chunk])
            if root_chunk in info:
                add_node(info[root_chunk])
                add_edge(root_id, f"c:{root_chunk}", None, "handles")
        else:
            inline = conn.execute(
                "SELECT inline_calls FROM endpoints WHERE id = %s", (endpoint_id,)
            ).fetchone()
            for full in (inline[0] if inline else [])[:FLOW_MAX_EXTERNALS_PER_CALLER]:
                if keep_external(full) and add_node(external_node(full)):
                    add_edge(root_id, f"x:{full}", None)
    elif chunk_id is not None:
        info = _chunk_nodes(conn, repo_id, [chunk_id])
        if chunk_id not in info:
            raise FlowTargetNotFound(f"chunk {chunk_id} not found")
        add_node(info[chunk_id])
        root_id, root_chunk = f"c:{chunk_id}", chunk_id
    else:
        raise FlowTargetNotFound("endpoint_id or chunk_id is required")

    if root_chunk is not None and direction in ("down", "both"):
        seen, frontier = {root_chunk}, [root_chunk]
        # `depth` hops of resolved callees, plus one extra pass that only attaches
        # the external calls (jwt.decode, ...) of the last layer: that is where
        # the auth evidence usually lives and it should not cost a hop.
        for level in range(depth + 1):
            if not frontier:
                break
            rows = conn.execute(
                """
                SELECT caller_chunk_id, callee_chunk_id, callee_full, line
                FROM call_edges WHERE repo_id = %s AND caller_chunk_id = ANY(%s)
                ORDER BY line
                """,
                (repo_id, frontier),
            ).fetchall()
            resolved = {r[1] for r in rows if r[1] is not None}
            info = _chunk_nodes(conn, repo_id, sorted(resolved - set(nodes_chunk_ids(nodes))))
            nxt: list[int] = []
            externals: dict[int, list[tuple[str, int]]] = {}
            for caller, callee, full, line in rows:
                if callee is not None and callee != caller:
                    if level >= depth:
                        continue
                    node = info.get(callee) or nodes.get(f"c:{callee}")
                    if node and add_node(node):
                        add_edge(f"c:{caller}", f"c:{callee}", line)
                        if callee not in seen:
                            seen.add(callee)
                            nxt.append(callee)
                elif callee is None and keep_external(full):
                    externals.setdefault(caller, []).append((full, line))
            for caller, calls in externals.items():
                unique = list(dict.fromkeys(calls))
                unique.sort(key=lambda c: (not AUTH_CALL_RE.search(c[0]), c[1]))
                for full, line in unique[:FLOW_MAX_EXTERNALS_PER_CALLER]:
                    if add_node(external_node(full)):
                        add_edge(f"c:{caller}", f"x:{full}", line)
                hidden = len(unique) - FLOW_MAX_EXTERNALS_PER_CALLER
                if hidden > 0 and f"c:{caller}" in nodes:
                    nodes[f"c:{caller}"]["hidden_calls"] = hidden
            frontier = nxt

    if root_chunk is not None and direction in ("up", "both"):
        seen, frontier = {root_chunk}, [root_chunk]
        for _ in range(depth):
            if not frontier:
                break
            for chunk in frontier:  # routes that handle this function
                for e in by_handler.get(chunk, []):
                    if add_node(endpoint_node(e)):
                        add_edge(f"e:{e['id']}", f"c:{chunk}", None, "handles")
            rows = conn.execute(
                """
                SELECT caller_chunk_id, callee_chunk_id, line
                FROM call_edges WHERE repo_id = %s AND callee_chunk_id = ANY(%s)
                ORDER BY line
                """,
                (repo_id, frontier),
            ).fetchall()
            info = _chunk_nodes(
                conn, repo_id, sorted({r[0] for r in rows} - set(nodes_chunk_ids(nodes)))
            )
            nxt = []
            for caller, callee, line in rows:
                node = info.get(caller) or nodes.get(f"c:{caller}")
                if node and caller != callee and add_node(node):
                    add_edge(f"c:{caller}", f"c:{callee}", line)
                    if caller not in seen:
                        seen.add(caller)
                        nxt.append(caller)
            frontier = nxt

    return {
        "root": root_id,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "truncated": state["truncated"],
        "depth": depth,
        "direction": direction,
    }


def nodes_chunk_ids(nodes: dict[str, dict]) -> list[int]:
    return [n["chunk_id"] for n in nodes.values() if "chunk_id" in n]


def function_graph(conn: psycopg.Connection, repo_id: int, name: str) -> dict:
    definitions = conn.execute(
        """
        SELECT c.id, f.path, c.kind, c.qualified_name, c.start_line, c.end_line
        FROM chunks c JOIN files f ON f.id = c.file_id
        WHERE c.repo_id = %s AND c.name = %s AND c.kind IN ('function', 'method', 'class')
        ORDER BY f.path, c.start_line
        """,
        (repo_id, name),
    ).fetchall()
    ids = [d[0] for d in definitions]

    calls = conn.execute(
        """
        SELECT ce.callee_full, ce.line, f.path, cc.qualified_name
        FROM call_edges ce
        LEFT JOIN chunks cc ON cc.id = ce.callee_chunk_id
        LEFT JOIN files f ON f.id = cc.file_id
        WHERE ce.caller_chunk_id = ANY(%s)
        ORDER BY ce.line
        """,
        (ids,),
    ).fetchall()

    called_by = conn.execute(
        """
        SELECT f.path, c.qualified_name, ce.line
        FROM call_edges ce
        JOIN chunks c ON c.id = ce.caller_chunk_id
        JOIN files f ON f.id = ce.file_id
        WHERE ce.repo_id = %s AND ce.callee_name = %s
        ORDER BY f.path, ce.line
        """,
        (repo_id, name),
    ).fetchall()

    return {
        "name": name,
        "definitions": [
            {"file": p, "kind": k, "name": q, "start_line": s, "end_line": e}
            for _, p, k, q, s, e in definitions
        ],
        "calls": [
            {"callee": full, "line": line, "defined_in": path, "resolved_name": resolved}
            for full, line, path, resolved in calls
        ],
        "called_by": [
            {"file": p, "function": q, "line": line} for p, q, line in called_by
        ],
    }
