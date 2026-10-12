"""Text helpers shared by indexing and retrieval."""

import re

_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")

STOPWORDS = frozenset(
    "a an and are as at be by do does for from how i in is it of on or "
    "that the this to what when where which who why with".split()
)


def split_identifiers(text: str) -> list[str]:
    """'hashPassword' / 'hash_password' / 'HTTPServer' -> lowercase words."""
    return [w.lower() for w in _WORD.findall(text)]


def search_text(path: str, qualified_name: str, content: str) -> str:
    """Text fed to keyword search: split-out identifiers make `hash_password`
    findable by the query 'password hash'."""
    words = split_identifiers(f"{path} {qualified_name}")
    return f"{path} {qualified_name} {' '.join(words)}\n{content}"


def embedding_text(path: str, kind: str, qualified_name: str, content: str) -> str:
    return f"{path}\n{kind} {qualified_name}\n{content}"


def query_terms(query: str) -> list[str]:
    seen: dict[str, None] = {}
    for word in split_identifiers(query):
        if word not in STOPWORDS and len(word) > 1:
            seen[word] = None
    return list(seen)
