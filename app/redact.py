"""Best-effort secret redaction for text that may leave the machine.

This is a safety net, not a guarantee: it catches well-known token formats and
`password = "..."`-style assignments. It cannot recognise an arbitrary string
that happens to be a secret, so exports should still be skimmed before being
sent to a third party."""

import re
from collections import Counter

# (kind, pattern, group to replace; 0 = whole match)
_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S), 0),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), 0),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), 0),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b"), 0),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), 0),
    # scheme://user:PASSWORD@host
    ("url-password", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:([^\s/@]{3,})@"), 1),
    # password = "hunter2xyz"   token: 'abc...'   client_secret="..."
    ("credential-assignment", re.compile(
        r"""(?ix)
        \b[\w.\-]*(?:pass(?:word|wd)?|secret|token|api[_\-]?key|private[_\-]?key|auth[_\-]?key|credential)s?
        ["']?
        (?:\s*:\s*[A-Za-z_][\w\[\], .|]*)?      # optional annotation: password: str = "..."
        \s*[:=]\s*
        (?:f|r|b)?["']([^"'\s{}$%]{6,})["']
        """), 1),
]

PLACEHOLDER = re.compile(
    r"^(?:x+|\*+|\.+|<[^>]+>|\[REDACTED:[^\]]+\]|your[_\-].*|changeme|example.*|placeholder.*|none|null|todo)$",
    re.I,
)


class Redactor:
    """Collects what it removed so callers can report it."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def clean(self, text: str) -> str:
        if not text:
            return text
        for kind, pattern, group in _RULES:
            text = pattern.sub(lambda m, k=kind, g=group: self._sub(m, k, g), text)
        return text

    def _sub(self, m: re.Match[str], kind: str, group: int) -> str:
        whole = m.group(0)
        if group == 0:
            self.counts[kind] += 1
            return f"[REDACTED:{kind}]"
        secret = m.group(group)
        if PLACEHOLDER.match(secret):  # `password = "changeme"` carries no secret
            return whole
        self.counts[kind] += 1
        start, end = m.span(group)
        a = m.start(0)
        return whole[: start - a] + f"[REDACTED:{kind}]" + whole[end - a :]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def report(self) -> dict:
        return {"total": self.total, "by_kind": dict(self.counts)}
