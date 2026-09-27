"""Tool 9: embed + FakeEmbedder for tests."""
from __future__ import annotations
import threading
from typing import List

_model = None
_lock = threading.Lock()


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

    Returns a list of 384-dim float vectors using all-MiniLM-L6-v2.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


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
