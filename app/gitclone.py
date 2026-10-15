"""Index a project straight from a Git URL.

Only public https URLs on an allow-listed host are accepted, the clone is shallow,
and git never prompts for credentials. The clone lands in CLONES_DIR (a writable
volume) and is then ingested exactly like a local folder.
"""

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_HOSTS = "github.com,gitlab.com,bitbucket.org"
CLONE_TIMEOUT_S = 180
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GitError(ValueError):
    """Bad URL or a failed clone; the message is safe to show to the user."""


def allowed_hosts() -> set[str]:
    raw = os.environ.get("GIT_HOSTS", DEFAULT_HOSTS)
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def looks_like_url(value: str) -> bool:
    return value.startswith(("https://", "http://", "git@", "ssh://"))


def parse_git_url(raw: str) -> tuple[str, str]:
    """Return (clean https URL, folder name 'owner__repo') or raise GitError."""
    url = raw.strip()
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise GitError("only https:// Git URLs are supported")
    if parts.username or parts.password or "@" in parts.netloc:
        raise GitError("URLs with credentials are not accepted; use a public repository URL")
    host = (parts.hostname or "").lower()
    if host not in allowed_hosts():
        raise GitError(f"host '{host}' is not allowed (allowed: {', '.join(sorted(allowed_hosts()))})")
    if parts.query or parts.fragment or parts.port:
        raise GitError("URL must look like https://github.com/owner/repo")

    segments = [s for s in parts.path.split("/") if s]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][:-4]
    if len(segments) < 2 or not all(_SEGMENT.match(s) and s not in (".", "..") for s in segments):
        raise GitError("URL must look like https://github.com/owner/repo")

    clean = f"https://{host}/{'/'.join(segments)}.git"
    return clean, "__".join(segments)


def clones_dir() -> Path:
    return Path(os.environ.get("CLONES_DIR", "/clones"))


def _git(args: list[str], cwd: Path | None = None) -> None:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S
        )
    except FileNotFoundError as e:
        raise GitError("git is not installed in this environment") from e
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git timed out after {CLONE_TIMEOUT_S}s (repository too large?)") from e
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["unknown error"]
        raise GitError(f"git failed: {tail[0]}")


def fetch(raw_url: str) -> Path:
    """Clone (or refresh) the repository and return the local folder."""
    url, name = parse_git_url(raw_url)
    root = clones_dir()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / name
    if (dest / ".git").is_dir():
        _git(["fetch", "--depth", "1", "origin", "HEAD"], cwd=dest)
        _git(["reset", "--hard", "FETCH_HEAD"], cwd=dest)
    else:
        _git(["clone", "--depth", "1", "--no-tags", "--", url, str(dest)])
    return dest
