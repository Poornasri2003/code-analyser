"""Tool 7: validate_graph  Tool 8: assign_ids"""
from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, List, Tuple

from code_analyser.models import (
    ExtractorOutput, GraphEdge, GraphNode, StoredEdge, StoredNode,
)


def _sha1_id(user_id: str, run_id: str, local_id: str) -> str:
    raw = f"{user_id}|{run_id}|{local_id}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def validate_graph(
    raw: Dict[str, Any],
    file_line_count: int,
) -> Tuple[ExtractorOutput, Dict[str, Any]]:
    """
    Tool 7 — validate_graph(raw_json, file_len) -> (clean_batch, drop_report)

    Drops nodes with blank description/name/type; drops duplicate local_ids
    (keep first); nulls self-parent; nulls parent pointing to absent node;
    drops edges whose source is absent; clamps line numbers to [1, file_len].
    """
    report: Dict[str, Any] = {
        "nodes_dropped_blank": 0,
        "nodes_dropped_duplicate": 0,
        "parent_ids_nulled": 0,
        "edges_dropped_dangling": 0,
    }

    raw_nodes = raw.get("nodes", [])
    raw_edges = raw.get("relationships", [])

    seen_ids: set[str] = set()
    clean_nodes: List[GraphNode] = []

    for n in raw_nodes:
        if not isinstance(n, dict):
            report["nodes_dropped_blank"] += 1
            continue
        # require name, description, type, local_id
        if not (n.get("name") or "").strip():
            report["nodes_dropped_blank"] += 1
            continue
        if not (n.get("description") or "").strip():
            report["nodes_dropped_blank"] += 1
            continue
        if not n.get("type"):
            report["nodes_dropped_blank"] += 1
            continue
        lid = (n.get("local_id") or "").strip()
        if not lid:
            report["nodes_dropped_blank"] += 1
            continue

        if lid in seen_ids:
            report["nodes_dropped_duplicate"] += 1
            continue
        seen_ids.add(lid)

        # clamp line numbers
        ls = n.get("line_start")
        le = n.get("line_end")
        if ls is not None:
            n["line_start"] = max(1, min(int(ls), file_line_count))
        if le is not None:
            n["line_end"] = max(1, min(int(le), file_line_count))

        # self-parent
        if n.get("parent_local_id") == lid:
            n["parent_local_id"] = None
            report["parent_ids_nulled"] += 1

        try:
            clean_nodes.append(GraphNode.model_validate(n))
        except Exception:
            report["nodes_dropped_blank"] += 1

    # null parents pointing at absent nodes
    for node in clean_nodes:
        if node.parent_local_id and node.parent_local_id not in seen_ids:
            node.parent_local_id = None
            report["parent_ids_nulled"] += 1

    # validate edges — drop if source not in known nodes
    clean_edges: List[GraphEdge] = []
    for e in raw_edges:
        if not isinstance(e, dict):
            report["edges_dropped_dangling"] += 1
            continue
        src = e.get("source_local_id", "")
        tgt = e.get("target_local_id", "")
        if not src or not tgt:
            report["edges_dropped_dangling"] += 1
            continue
        if src not in seen_ids:
            report["edges_dropped_dangling"] += 1
            continue
        try:
            clean_edges.append(GraphEdge.model_validate(e))
        except Exception:
            report["edges_dropped_dangling"] += 1

    return ExtractorOutput(nodes=clean_nodes, relationships=clean_edges), report


def assign_ids(
    batch: ExtractorOutput,
    user_id: str,
    run_id: str,
) -> Tuple[List[StoredNode], List[StoredEdge]]:
    """
    Tool 8 — assign_ids(batch, user_id, run_id) -> ([StoredNode], [StoredEdge])

    Assigns deterministic sha1-based ids.
    Computes parent_id and ancestor_ids (root -> immediate parent).
    """
    node_map: Dict[str, GraphNode] = {n.local_id: n for n in batch.nodes}

    def _ancestors(local_id: str) -> List[str]:
        chain: List[str] = []
        visited: set[str] = set()
        current = node_map.get(local_id)
        if not current:
            return chain
        parent_lid = current.parent_local_id
        while parent_lid and parent_lid not in visited:
            visited.add(parent_lid)
            chain.append(_sha1_id(user_id, run_id, parent_lid))
            parent_node = node_map.get(parent_lid)
            if not parent_node:
                break
            parent_lid = parent_node.parent_local_id
        chain.reverse()
        return chain

    stored_nodes: List[StoredNode] = []
    for node in batch.nodes:
        nid = _sha1_id(user_id, run_id, node.local_id)
        parent_id = (
            _sha1_id(user_id, run_id, node.parent_local_id)
            if node.parent_local_id
            else None
        )
        ancestor_ids = _ancestors(node.local_id)
        props = node.properties if isinstance(node.properties, dict) else {}
        stored_nodes.append(
            StoredNode(
                id=nid,
                local_id=node.local_id,
                user_id=user_id,
                run_id=run_id,
                type=node.type,
                name=node.name,
                description=node.description,
                path=node.path,
                line_start=node.line_start,
                line_end=node.line_end,
                parent_id=parent_id,
                ancestor_ids=ancestor_ids,
                props_json=json.dumps(props),
            )
        )

    lid_to_id = {n.local_id: _sha1_id(user_id, run_id, n.local_id) for n in batch.nodes}

    stored_edges: List[StoredEdge] = []
    for edge in batch.relationships:
        src_id = lid_to_id.get(edge.source_local_id)
        tgt_id = lid_to_id.get(edge.target_local_id)
        if not src_id or not tgt_id:
            continue
        stored_edges.append(
            StoredEdge(
                source_id=src_id,
                target_id=tgt_id,
                type=edge.type,
                description=edge.description,
                evidence_path=edge.evidence_path,
                evidence_line=edge.evidence_line,
            )
        )

    return stored_nodes, stored_edges
