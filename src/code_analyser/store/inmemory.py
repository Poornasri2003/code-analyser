"""InMemoryStore — no database required, used in tests."""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

from code_analyser.models import StoredEdge, StoredNode


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryStore:
    """Satisfies the GraphStore protocol using plain dicts. Thread-unsafe."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}   # id -> node dict
        self._edges: List[Dict[str, Any]] = []

    def ensure_schema(self) -> None:
        """No-op for in-memory store."""
        pass

    def write(
        self,
        nodes: List[StoredNode],
        edges: List[StoredEdge],
        user_id: str,
        run_id: str,
    ) -> Tuple[int, int]:
        """
        Upsert nodes and edges for a user/run.
        Re-analysing the same run updates, never duplicates.
        """
        # Upsert nodes
        for n in nodes:
            self._nodes[n.id] = n.model_dump()

        # Remove old edges for this run, then insert new ones (idempotent)
        self._edges = [
            e for e in self._edges
            if not (e.get("user_id") == user_id and e.get("run_id") == run_id)
        ]
        for e in edges:
            d = e.model_dump()
            d["user_id"] = user_id
            d["run_id"] = run_id
            self._edges.append(d)

        return len(nodes), len(edges)

    def query(
        self,
        user_id: str,
        run_id: str,
        qvec: List[float],
        k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search, then expand to ancestors + children.
        Returns a list with one element: {"nodes": [...], "edges": [...]}.
        """
        candidates = [
            n for n in self._nodes.values()
            if n.get("user_id") == user_id and n.get("run_id") == run_id
        ]
        if not candidates:
            return []

        # score by cosine; nodes without embeddings score 0
        scored = []
        for n in candidates:
            emb = n.get("embedding")
            score = _cosine(qvec, emb) if emb else 0.0
            scored.append((score, n))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_k = [n for _, n in scored[:k]]

        result_ids: set[str] = {n["id"] for n in top_k}

        # add ancestors
        for n in top_k:
            for aid in n.get("ancestor_ids", []):
                result_ids.add(aid)

        # add direct children
        for n in self._nodes.values():
            if n.get("parent_id") in result_ids and n.get("user_id") == user_id:
                result_ids.add(n["id"])

        # cap at 60
        result_ids = set(list(result_ids)[:60])
        nodes_out = [self._nodes[i] for i in result_ids if i in self._nodes]

        # edges between result nodes
        edges_out = [
            e for e in self._edges
            if e.get("source_id") in result_ids and e.get("target_id") in result_ids
        ]

        return [{"nodes": nodes_out, "edges": edges_out}]

    # ── Legacy helpers kept for any tests that use them directly ─────────────

    def upsert_node(self, node: Dict[str, Any]) -> None:
        self._nodes[node["id"]] = node

    def query_all(
        self, user_id: str, run_id: str, *, limit: int = 500
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """The whole graph for one run: every node and every edge."""
        nodes = self.query_nodes(user_id, run_id, limit=limit)
        edges = [
            e for e in self._edges
            if e.get("user_id") == user_id and e.get("run_id") == run_id
        ]
        return nodes, edges

    def query_nodes(self, user_id: str, run_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        return [
            n for n in self._nodes.values()
            if n.get("user_id") == user_id and n.get("run_id") == run_id
        ][:limit]

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
