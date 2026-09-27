"""Answer agent — answers a question grounded in the code graph.

It handles two kinds of question. "explain" questions ask how something works;
the answer walks the relationship chain. "change" questions ask where to add a
feature or what a modification affects; the answer names the place to change,
then walks the edges outward to find everything impacted.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analyser import config
from code_analyser.graph_context import render_context
from code_analyser.llm.protocol import LLMFormatError
from code_analyser.models import AnswerOutput, Citation

_MAX_RETRIES = 2

SYSTEM = """You are Code Analyser, an onboarding assistant. A developer has just been \
handed an unfamiliar codebase (or a set of documents) and needs to understand it \
quickly without reading every file. You answer ONLY from the GRAPH provided, which \
was extracted from their files. Every node has an [id], a type, a name, a location \
(path:lines) and a description; RELATIONSHIPS show who CALLS, IMPORTS, READS, WRITES \
or CONTAINS whom.

First decide what kind of question this is:
- "explain": how something works, what it does, where it lives, what calls what.
- "change": they want to add a feature, fix a bug, change behaviour or refactor, or \
they ask where something should go or what breaks if they touch something.

Return ONE json object with exactly these keys:
{
  "mode": "explain" | "change",
  "answer": "The direct answer in plain language, 2-5 short paragraphs. Lead with the \
answer, then the detail. Put real function, class and file names in backticks, e.g. \
`login` in `shop/auth.py`. No filler, no restating the question.",
  "steps": ["For explain: how control or data flows, one step per item, naming the \
function and file at each step. For change: the implementation plan, one concrete edit \
per item, in the order to make them."],
  "where_to_add": [{"target": "path or path::symbol that exists in the graph", \
"why": "why this is the right place"}],
  "impact": [{"target": "path::symbol that exists in the graph", "relationship": \
"how it is connected, e.g. 'calls login' or 'imported by auth.py'", "effect": "what \
happens to it and what to check"}],
  "also_update": ["tests, configuration, documentation or callers that must change too"],
  "risks": ["what could break, and how to guard against it"],
  "citations": ["the [id] of every node your answer relies on"],
  "follow_ups": ["2-3 short questions this developer would naturally ask next"],
  "grounded": true
}

Rules:
- Use ONLY the graph. Never invent a file, function, parameter or behaviour.
- Cite the [id] of every node you rely on. Never cite an id that is not in the graph.
- For "change", where_to_add and impact are required. Find impact by walking the \
RELATIONSHIPS outward from what is being changed: every caller, importer, reader or \
writer of it is affected, and so are their callers when the change alters a signature \
or a return value. Say which of those actually need editing and which only need \
re-testing.
- For "explain", make the steps follow the relationship chain rather than list nodes. \
Leave where_to_add, impact, also_update and risks empty unless genuinely useful.
- Write for someone new to the project: explain a project-specific term the first time \
you use it.
- If the graph does not contain the answer, say so plainly, mention the closest thing \
that IS in the graph, set grounded to false and cite nothing. Do not guess."""


def _str_list(value: Any, limit: int = 12) -> List[str]:
    """Models sometimes return objects where strings were asked for."""
    out: List[str] = []
    for item in value or []:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = " — ".join(str(v) for v in item.values() if v)
        else:
            text = str(item)
        text = text.strip()
        if text:
            out.append(text)
    return out[:limit]


def _dict_list(value: Any, keys: List[str], limit: int = 12) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in value or []:
        if isinstance(item, dict):
            row = {k: str(item.get(k) or "").strip() for k in keys}
        else:
            row = {keys[0]: str(item).strip(), **{k: "" for k in keys[1:]}}
        if any(row.values()):
            out.append(row)
    return out[:limit]


def _cited_ids(raw: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for c in raw.get("citations") or []:
        cid = c.get("node_id") if isinstance(c, dict) else c
        if isinstance(cid, str) and cid:
            ids.append(cid.strip().strip("[]"))
    for cid in raw.get("subgraph_node_ids") or []:
        if isinstance(cid, str) and cid:
            ids.append(cid.strip().strip("[]"))
    return list(dict.fromkeys(ids))


def _history_block(history: Optional[List[Dict[str, str]]]) -> str:
    if not history:
        return ""
    lines = ["CONVERSATION SO FAR (for context; answer only the new question):"]
    for turn in history[-4:]:
        q = (turn.get("q") or "").strip()
        a = (turn.get("a") or "").strip()
        if q:
            lines.append(f"Q: {q[:300]}")
        if a:
            lines.append(f"A: {a[:500]}")
    return "\n".join(lines) + "\n\n"


def run_answer_agent(
    question: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    client,
    history: Optional[List[Dict[str, str]]] = None,
) -> AnswerOutput:
    """Generate a grounded answer to *question* from the given graph.

    A citation of an id the model was never shown means it is making things
    up, so that attempt is retried. On the final attempt, unknown ids are
    dropped if any real ones remain, and the answer fails closed otherwise.
    """
    context, shown_ids = render_context(nodes, edges, config.ANSWER_CONTEXT_CHARS)
    by_id = {n["id"]: n for n in nodes if "id" in n}
    user = f"{_history_block(history)}GRAPH:\n{context}\n\nQUESTION: {question}"

    for attempt in range(_MAX_RETRIES):
        try:
            raw, _ = client.complete_json(SYSTEM, user, max_tokens=config.ANSWER_MAX_TOKENS)
        except LLMFormatError:
            continue
        if not isinstance(raw, dict):
            continue

        cited = _cited_ids(raw)
        known = [c for c in cited if c in shown_ids or (not shown_ids and c in by_id)]
        unknown = [c for c in cited if c not in known]

        if unknown and attempt < _MAX_RETRIES - 1:
            continue
        if cited and not known:
            return AnswerOutput(
                answer=raw.get("answer") or "",
                citations=[],
                grounded=False,
                subgraph_node_ids=[],
            )

        citations = []
        for cid in known:
            n = by_id.get(cid, {})
            citations.append(Citation(
                node_id=cid,
                path=n.get("path") or "",
                line_start=n.get("line_start"),
                line_end=n.get("line_end"),
                name=n.get("name"),
                type=n.get("type"),
            ))

        mode = str(raw.get("mode") or "explain").lower()
        grounded = bool(raw.get("grounded", True)) and bool(raw.get("answer"))
        return AnswerOutput(
            answer=raw.get("answer") or "",
            citations=citations,
            grounded=grounded,
            subgraph_node_ids=known,
            mode="change" if mode.startswith("change") else "explain",
            steps=_str_list(raw.get("steps")),
            where_to_add=_dict_list(raw.get("where_to_add"), ["target", "why"]),
            impact=_dict_list(raw.get("impact"), ["target", "relationship", "effect"]),
            also_update=_str_list(raw.get("also_update")),
            risks=_str_list(raw.get("risks")),
            follow_ups=_str_list(raw.get("follow_ups"), limit=4),
        )

    return AnswerOutput(
        answer="Could not produce a grounded answer.",
        citations=[],
        grounded=False,
        subgraph_node_ids=[],
    )
