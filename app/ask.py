"""Turn retrieved chunks into a grounded, citable prompt."""

import re

from app.retrieval import Hit

SYSTEM_PROMPT = (
    "You are RepoMind, an assistant that explains a codebase. Answer ONLY from the "
    "numbered code snippets provided. Cite snippets inline like [1] or [2][3]. "
    "Mention file paths and function names when useful. If the snippets do not "
    "contain the answer, say so plainly instead of guessing."
)


def format_snippet(number: int, hit: Hit) -> str:
    header = f"[{number}] {hit.file}:{hit.start_line}-{hit.end_line} ({hit.kind} {hit.qualified_name})"
    return f"{header}\n```\n{hit.content}\n```"


_ENDPOINT_QUESTION = re.compile(
    r"\b(endpoints?|apis?|routes?|auth\w*|log_?in|sign_?(in|up)|protected|public|"
    r"permissions?|handlers?)\b",
    re.I,
)
MAX_ENDPOINT_LINES = 60


def is_endpoint_question(question: str) -> bool:
    return bool(_ENDPOINT_QUESTION.search(question))


def format_endpoint(e: dict) -> str:
    tags = []
    if e["handles_authentication"]:
        tags.append("authentication")
    if e["requires_auth"]:
        tags.append("requires auth")
    if not tags:
        tags.append("no auth detected")
    handler = f" -> {e['handler']}" if e["handler"] else ""
    where = f"{e['file']}:{e['line']}"
    why = f" ({'; '.join(e['evidence'])})" if e["evidence"] else ""
    return f"- {e['method']} {e['path']}{handler} [{where}] [{', '.join(tags)}]{why}"


def build_messages(
    question: str, hits: list[Hit], endpoints: list[dict] | None = None
) -> list[dict[str, str]]:
    context = "\n\n".join(format_snippet(i, h) for i, h in enumerate(hits, start=1))
    parts = [f"Code snippets:\n\n{context}"]
    if endpoints:
        lines = "\n".join(format_endpoint(e) for e in endpoints[:MAX_ENDPOINT_LINES])
        parts.append(
            "Detected HTTP endpoints (static analysis; authoritative for routes and "
            f"auth classification):\n{lines}"
        )
    parts.append(f"Question: {question}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def citation(number: int, hit: Hit) -> dict:
    return {
        "ref": number,
        "file": hit.file,
        "start_line": hit.start_line,
        "end_line": hit.end_line,
        "kind": hit.kind,
        "name": hit.qualified_name,
        "score": round(hit.score, 4),
        "matched_by": hit.matched_by,
    }
