"""GraphStore protocol."""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol, Tuple

from code_analyser.models import StoredEdge, StoredNode


class GraphStore(Protocol):
    def ensure_schema(self) -> None:
        """Create constraints and indexes if they don't exist."""
        ...

    def write(
        self,
        nodes: List[StoredNode],
        edges: List[StoredEdge],
        user_id: str,
        run_id: str,
    ) -> Tuple[int, int]:
        """
        Write nodes and edges. Returns (nodes_written, edges_written).
        Re-analysing same source updates, never duplicates.
        """
        ...

    def query(
        self,
        user_id: str,
        run_id: str,
        qvec: List[float],
        k: int = 8,
    ) -> List[Dict[str, Any]]:
        """Vector similarity query returning subgraph dicts."""
        ...
