"""Embedding providers. Model libraries are imported lazily so tests and
tooling never need them (or a model download)."""

import hashlib
import math
import os
import threading
from functools import lru_cache
from typing import Protocol

from app.text import split_identifiers

EMBED_DIM = 384  # BAAI/bge-small-en-v1.5; must match chunks.embedding vector(384)


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed (no PyTorch, no API key)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self._model_name)
            return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._load().embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._load().query_embed(text))).tolist()


class HashingEmbedder:
    """Deterministic bag-of-words embedder. No model, so it is used in tests
    and for offline smoke runs; quality is far below a real model."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self._dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in split_identifiers(text):
            digest = hashlib.md5(word.encode()).digest()
            vec[int.from_bytes(digest[:4], "big") % self._dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@lru_cache
def get_embedder() -> Embedder:
    kind = os.environ.get("EMBEDDER", "fastembed")
    if kind == "hashing":
        return HashingEmbedder()
    if kind == "fastembed":
        return FastEmbedEmbedder(os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    raise RuntimeError(f"unknown EMBEDDER: {kind}")


def to_pgvector(vec: list[float]) -> str:
    """pgvector text literal; use with `%s::vector`."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
