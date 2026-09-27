"""Tool 9: embed + FakeEmbedder for tests."""
from __future__ import annotations
import hashlib
import math
import os
import re
import threading
from typing import List

DIM = 384

_model = None
_lock = threading.Lock()

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _split_identifier(token: str) -> List[str]:
    """camelCase and snake_case carry most of the meaning in code, so index
    the parts as well as the whole."""
    parts = re.split(r"_+", token)
    out: List[str] = []
    for part in parts:
        out.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+", part) or [part])
    return [p for p in out if p]


def _hash_embed(text: str) -> List[float]:
    """Hashing vectoriser: no model, no download, no torch. Lower quality than
    a transformer but deterministic and adequate for the small graphs a single
    run produces."""
    vec = [0.0] * DIM
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    expanded: List[str] = []
    for t in tokens:
        expanded.append(t)
        expanded.extend(p.lower() for p in _split_identifier(t))
    if not expanded:
        return vec
    for tok in expanded:
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed(texts: List[str]) -> List[List[float]]:
    """
    Tool 9 — embed(texts) -> [vector]

    Returns 384-dim vectors. EMBEDDER=transformer uses all-MiniLM-L6-v2, which
    needs torch and roughly 2GB; the default hashing embedder needs neither and
    keeps the image small enough for a free host.
    """
    if not texts:
        return []
    if os.getenv("EMBEDDER", "hashing").lower() == "transformer":
        model = _get_model()
        return [v.tolist() for v in model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False)]
    return [_hash_embed(t) for t in texts]


class FakeEmbedder:
    """
    Deterministic fake embedder for tests. No model required.
    Returns 384-dim zero vectors so cosine similarity comparisons don't crash.
    """

    DIM = 384

    @staticmethod
    def embed(texts: List[str]) -> List[List[float]]:
        """Accept a list of strings, return list of zero vectors."""
        return [[0.0] * FakeEmbedder.DIM for _ in texts]
