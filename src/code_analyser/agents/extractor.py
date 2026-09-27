"""Extractor agent — extracts nodes and edges from a single file."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from code_analyser.models import ExtractorOutput, GraphEdge, GraphNode
from code_analyser.llm.protocol import LLMFormatError


def run_extractor(
    root: Path,
    rel_path: str,
    client,
) -> ExtractorOutput:
    """Extract code graph nodes/edges from a single file.

    Raises LLMFormatError if the response is structurally invalid.
    """
    from code_analyser.tools.fs import read_file
    try:
        content = read_file(root, rel_path)
    except Exception:
        content = ""

    system = "Extract code graph nodes and relationships as JSON."
    user = f"File: {rel_path}\n\n{content[:8000]}"

    raw, _ = client.complete_json(system, user)

    try:
        return _parse_extractor_response(raw)
    except (KeyError, ValueError, TypeError) as exc:
        raise LLMFormatError(f"Extractor response invalid: {exc}") from exc


def _parse_extractor_response(raw: Dict[str, Any]) -> ExtractorOutput:
    nodes = [GraphNode.model_validate(n) for n in raw.get("nodes", [])]
    edges = [GraphEdge.model_validate(e) for e in raw.get("relationships", [])]
    return ExtractorOutput(nodes=nodes, relationships=edges)
