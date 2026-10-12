"""Cross-encoder reranking (optional). Imported lazily like the embedder."""

import os
import threading
from functools import lru_cache
from typing import Protocol


class Reranker(Protocol):
    def score(self, query: str, documents: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                self._model = TextCrossEncoder(self._model_name)
            return self._model

    def score(self, query: str, documents: list[str]) -> list[float]:
        return [float(s) for s in self._load().rerank(query, documents)]


@lru_cache
def get_reranker() -> Reranker | None:
    kind = os.environ.get("RERANKER", "fastembed")
    if kind == "none":
        return None
    if kind == "fastembed":
        return FastEmbedReranker(os.environ.get("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2"))
    raise RuntimeError(f"unknown RERANKER: {kind}")
