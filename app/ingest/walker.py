import os
from collections.abc import Iterator
from pathlib import Path

from app.ingest.parser import EXTENSIONS

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
MAX_FILE_BYTES = 1_000_000


def iter_source_files(root: Path) -> Iterator[tuple[str, str, Path]]:
    """Yield (relative posix path, language, absolute path) for supported source files."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            language = EXTENSIONS.get(Path(filename).suffix.lower())
            if language is None:
                continue
            path = Path(dirpath) / filename
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            yield path.relative_to(root).as_posix(), language, path
