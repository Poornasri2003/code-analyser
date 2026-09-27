"""Answer agent — answers a question grounded in retrieved graph context."""
from __future__ import annotations
from typing import Any, Dict, List

from code_analyser.models import AnswerOutput, Citation
from code_analyser.llm.protocol import LLMFormatError

_MAX_RETRIES = 2


def run_answer_agent(
    question: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    client,
) -> AnswerOutput:
    """Generate a grounded answer to *question* using the given subgraph context.

    If the LLM cites node_ids not present in *nodes*, the answer is returned
    with ``grounded=False`` (fail-closed). Retries up to ``_MAX_RETRIES`` times.
    """
    known_ids = {n["id"] for n in nodes}
    system = "Answer the question using only the provided code graph context."
    user = (
        f"Question: {question}\n\n"
        f"Nodes: {[{'id': n['id'], 'name': n.get('name'), 'description': n.get('description')} for n in nodes]}"
    )

    for attempt in range(_MAX_RETRIES):
        try:
            raw, _ = client.complete_json(system, user)
        except LLMFormatError:
            continue

        # Models return citations either as objects or as bare id strings.
        cited_ids = {
            c.get("node_id") if isinstance(c, dict) else c
            for c in (raw.get("citations") or [])
        }
        subgraph_ids = set(raw.get("subgraph_node_ids", []))
        all_cited = cited_ids | subgraph_ids

        # Validate citations are grounded in the context
        if all_cited - known_ids - {None}:
            # Cited IDs not in context — will retry or fail closed
            if attempt == _MAX_RETRIES - 1:
                return AnswerOutput(
                    answer=raw.get("answer", ""),
                    citations=[],
                    grounded=False,
                    subgraph_node_ids=[],
                )
            continue

        citations = [
            Citation.model_validate(c)
            for c in (raw.get("citations") or [])
            if isinstance(c, dict)
        ]
        return AnswerOutput(
            answer=raw.get("answer", ""),
            citations=citations,
            grounded=raw.get("grounded", True),
            subgraph_node_ids=list(subgraph_ids & known_ids),
        )

    # Exhausted retries
    return AnswerOutput(
        answer="Could not produce a grounded answer.",
        citations=[],
        grounded=False,
        subgraph_node_ids=[],
    )
