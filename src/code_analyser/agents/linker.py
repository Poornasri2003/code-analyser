"""Linker agent — resolves dangling cross-file references."""
from __future__ import annotations
from pathlib import Path

from code_analyser.models import ExtractorOutput, GraphEdge, LinkerOutput


def run_linker(
    staged: ExtractorOutput,
    client,
    root: Path,
) -> LinkerOutput:
    """Ask the LLM to resolve dangling targets and identify merges/drops."""
    system = "You are a code graph linker. Resolve dangling references."
    dangling = [
        e.target_local_id
        for e in staged.relationships
        if not any(n.local_id == e.target_local_id for n in staged.nodes)
    ]
    user = f"Dangling targets: {dangling}"

    raw, _ = client.complete_json(system, user)
    return LinkerOutput.model_validate(raw)


def apply_linker_output(
    staged: ExtractorOutput,
    linker_out: LinkerOutput,
) -> ExtractorOutput:
    """Apply linker resolutions and drops to the staged ExtractorOutput.

    - Resolved: update target_local_id on matching edges.
    - Dropped: remove matching edges.
    """
    drop_targets = {d.dangling_target for d in linker_out.dropped}
    resolve_map = {r.dangling_target: r.resolved_local_id for r in linker_out.resolved}

    new_edges = []
    for edge in staged.relationships:
        tgt = edge.target_local_id
        if tgt in drop_targets:
            continue
        if tgt in resolve_map:
            edge = GraphEdge(
                source_local_id=edge.source_local_id,
                target_local_id=resolve_map[tgt],
                type=edge.type,
                description=edge.description,
                evidence_path=edge.evidence_path,
                evidence_line=edge.evidence_line,
            )
        new_edges.append(edge)

    return ExtractorOutput(nodes=staged.nodes, relationships=new_edges)
