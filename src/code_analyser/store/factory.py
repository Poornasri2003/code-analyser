"""get_store() factory."""
from __future__ import annotations


def get_store(store_type: str = "neo4j"):
    if store_type == "neo4j":
        from code_analyser.store.neo4j_store import Neo4jStore
        return Neo4jStore()
    elif store_type == "inmemory":
        from code_analyser.store.inmemory import InMemoryStore
        return InMemoryStore()
    else:
        raise ValueError(f"Unknown store type: {store_type!r}")
