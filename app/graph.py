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
                "handles_authentication": c.handles_authentication,
                "requires_auth": c.requires_auth,
                "evidence": c.evidence,
            }
        )
    return out


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
