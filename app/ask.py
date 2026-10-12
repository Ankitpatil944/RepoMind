"""Turn retrieved chunks into a grounded, citable prompt."""

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


def build_messages(question: str, hits: list[Hit]) -> list[dict[str, str]]:
    context = "\n\n".join(format_snippet(i, h) for i, h in enumerate(hits, start=1))
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Code snippets:\n\n{context}\n\nQuestion: {question}"},
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
