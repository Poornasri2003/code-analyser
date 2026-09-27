"""Render a stored graph as text an LLM can reason over.

The overview, the answer agent and the symbols view all read the same graph,
so they share one rendering: every node with its location and signature, and
every relationship between nodes that made it into the budget.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

CODE_TYPES = {"Function", "Method", "Class", "Module"}


def node_props(node: Dict[str, Any]) -> Dict[str, Any]:
    """Stored nodes keep extra fields as a JSON string, because Neo4j cannot
    hold nested maps as property values."""
    raw = node.get("props_json")
    if isinstance(raw, str) and raw:
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except ValueError:
            return {}
    val = node.get("props")
    return val if isinstance(val, dict) else {}


def _fmt_inputs(inputs: Any) -> str:
    if isinstance(inputs, list):
        return "; ".join(str(i) for i in inputs if i)
    return str(inputs or "")


def render_node(n: Dict[str, Any]) -> str:
    props = node_props(n)
    loc = n.get("path") or ""
    if n.get("line_start"):
        loc += f":{n.get('line_start')}"
        if n.get("line_end") and n.get("line_end") != n.get("line_start"):
            loc += f"-{n.get('line_end')}"
    parts = [f"[{n['id']}] {n.get('type')} {n.get('name')}"]
    if loc:
        parts.append(f"({loc})")
    line = " ".join(parts) + f" — {n.get('description') or ''}"
    extras = []
    if props.get("signature"):
        extras.append(f"signature: {props['signature']}")
    if props.get("inputs"):
        extras.append(f"inputs: {_fmt_inputs(props['inputs'])}")
    if props.get("outputs"):
        extras.append(f"outputs: {props['outputs']}")
    if extras:
        line += " | " + " | ".join(extras)
    return line


def render_edge(e: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    src, tgt = by_id.get(e.get("source_id")), by_id.get(e.get("target_id"))
    if not src or not tgt:
        return None
    line = (f"{src.get('name')} [{src['id']}] -{e.get('type')}-> "
            f"{tgt.get('name')} [{tgt['id']}]")
    if e.get("description"):
        line += f": {e['description']}"
    if e.get("evidence_path"):
        ev = e["evidence_path"]
        if e.get("evidence_line"):
            ev += f":{e['evidence_line']}"
        line += f" ({ev})"
    return line


def render_context(
    nodes: Iterable[Dict[str, Any]],
    edges: Iterable[Dict[str, Any]],
    char_budget: int,
    *,
    group_by_file: bool = False,
) -> Tuple[str, Set[str]]:
    """Render nodes then relationships, stopping at *char_budget*.

    Nodes are taken in the order given, so callers pass the most relevant
    first and truncation drops the least relevant. An edge is only rendered
    when both of its endpoints were, so the model never sees a dangling id.
    Returns the text and the ids that were actually shown.
    """
    nodes = list(nodes)
    if group_by_file:
        nodes.sort(key=lambda n: ((n.get("path") or "~"), n.get("line_start") or 0))

    lines: List[str] = ["NODES:"]
    used = len(lines[0]) + 1
    shown: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        if "id" not in n:
            continue
        text = render_node(n)
        if used + len(text) + 1 > char_budget * 0.72 and shown:
            break
        lines.append(text)
        used += len(text) + 1
        shown[n["id"]] = n

    rel_lines = []
    for e in edges:
        text = render_edge(e, shown)
        if not text:
            continue
        if used + len(text) + 1 > char_budget:
            break
        rel_lines.append(text)
        used += len(text) + 1
    if rel_lines:
        lines.append("")
        lines.append("RELATIONSHIPS:")
        lines.extend(rel_lines)

    return "\n".join(lines), set(shown)


def looks_like_code(nodes: Iterable[Dict[str, Any]]) -> bool:
    return any(n.get("type") in CODE_TYPES for n in nodes)
