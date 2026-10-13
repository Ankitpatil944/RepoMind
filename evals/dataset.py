import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    relevant: frozenset[str]  # "path/to/file.py::qualified_name"
    must_mention: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dataset:
    name: str
    repo_path: Path
    questions: list[Question]
    endpoints: list[dict] = field(default_factory=list)


def load_dataset(path: Path) -> Dataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    repo_path = (path.parent / raw["repo"]).resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"dataset repo not found: {repo_path}")
    questions = [
        Question(
            id=q["id"],
            question=q["question"],
            relevant=frozenset(q["relevant"]),
            must_mention=tuple(q.get("must_mention", [])),
        )
        for q in raw["questions"]
    ]
    if len({q.id for q in questions}) != len(questions):
        raise ValueError("duplicate question ids in dataset")
    return Dataset(raw["name"], repo_path, questions, raw.get("endpoints", []))
