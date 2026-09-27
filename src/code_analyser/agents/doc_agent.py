"""Agent 3 — DocGraphAgent. Extracts nodes and edges from documentation files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from code_analyser.models import ExtractorOutput
from code_analyser.llm.protocol import LLMClient, LLMFormatError
from code_analyser import config
from code_analyser.tools.fs import list_dir, read_file

SYSTEM_PROMPT = """You are DocGraphAgent. You analyse documentation, specifications,
configs, and prose files and return a knowledge graph as strict JSON.
Return ONLY this object — no prose, no fences:

{
  "nodes": [...],
  "relationships": [...]
}

Node schema:
{
  "local_id": "<path>#<heading-slug>" for sections, "<path>" for the document itself,
              "<concept-name>" for concepts/entities,
  "type": "Document|Section|Concept|Entity|Table|Config",
  "name": "<heading text or concept name>",
  "description": "Plain language 1-3 sentences. What this section or concept is.
                  Written for a newcomer. NEVER blank, NEVER just the heading.",
  "parent_local_id": "<parent section or document local_id>",
  "path": "<relative file path>",
  "line_start": <integer>,
  "line_end": <integer>,
  "properties": {}
}

Relationship schema:
{
  "source_local_id": "...",
  "target_local_id": "...",
  "type": "CONTAINS|REFERENCES|MENTIONS|RELATED_TO|DEPENDS_ON|DEFINED_BY",
  "description": "one sentence",
  "evidence_path": "<file path>",
  "evidence_line": <integer>
}

Rules:
- One Document node for the file itself.
- One Section node per heading, nested by heading depth (h2 inside h1, etc.).
- Concept and Entity nodes for important things the document is ABOUT — systems,
  roles, formats, obligations, parameters. Not every noun — only meaningful ones.
- Link sections with REFERENCES when one section points at another.
- Concepts with RELATED_TO when they are genuinely related, description says how.
- Where prose names a file, endpoint, table, or command, emit a MENTIONS edge
  whose target_local_id is that path or name — this stitches docs onto the code graph.
- Every node except the document root sets parent_local_id to the enclosing node.
- heading-slug: lowercase, spaces to hyphens, remove punctuation. E.g. "## API Auth" -> "api-auth"
- line_start/line_end: if chunk starts at N, add N-1 to all line numbers.
- Only emit what you actually saw. evidence_line is where you saw it.
- Never invent a heading, path or concept.
"""


def _chunk_file(content: str, chunk_lines: int = config.CHUNK_LINES) -> List[Tuple[int, str]]:
    lines = content.splitlines(keepends=True)
    chunks = []
    for i in range(0, len(lines), chunk_lines):
        start = i + 1
        chunk = "".join(lines[i : i + chunk_lines])
        chunks.append((start, chunk))
    return chunks


def run_doc_agent(
    root: Path,
    relpath: str,
    client: LLMClient,
) -> ExtractorOutput:
    """
    Run DocGraphAgent on one file.
    Returns ExtractorOutput. Raises LLMFormatError on bad model output.
    """
    content = read_file(root, relpath)
    chunks = _chunk_file(content)

    all_nodes: List[Dict[str, Any]] = []
    all_edges: List[Dict[str, Any]] = []

    for start_line, chunk_text in chunks:
        user_prompt = f"""FILE: {relpath}
CHUNK starting at line {start_line} (add {start_line - 1} to all relative line numbers):

{chunk_text}

Extract nodes and relationships. Return only the JSON object."""

        raw, _ = client.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=8192)
        all_nodes.extend(raw.get("nodes", []))
        all_edges.extend(raw.get("relationships", []))

    return ExtractorOutput.model_validate({"nodes": all_nodes, "relationships": all_edges})
