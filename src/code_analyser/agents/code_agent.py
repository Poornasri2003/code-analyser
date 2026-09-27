"""Agent 2 — CodeGraphAgent. Extracts nodes and edges from source code files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_analyser.models import ExtractorOutput
from code_analyser.llm.protocol import LLMClient, LLMFormatError
from code_analyser import config
from code_analyser.tools.fs import list_dir, read_file
from code_analyser.tools.search import search, find_references

SYSTEM_PROMPT = """You are CodeGraphAgent. You analyse source code and return a
knowledge graph as strict JSON. Return ONLY this object — no prose, no fences:

{
  "nodes": [...],
  "relationships": [...]
}

Node schema:
{
  "local_id": "<path>::<symbol>",
  "type": "Module|Class|Function|Method|File|Config|Entity",
  "name": "<symbol name>",
  "description": "Plain language 1-3 sentences. What it is and what it is for.
                  Written for a newcomer who has never seen this project. NEVER blank.",
  "parent_local_id": "<enclosing node local_id>",
  "path": "<relative file path>",
  "line_start": <integer>,
  "line_end": <integer>,
  "properties": {
    "signature": "full signature string",
    "inputs": ["param: type — what it means"],
    "outputs": "return type and meaning",
    "language": "python|javascript|..."
  }
}

Relationship schema:
{
  "source_local_id": "...",
  "target_local_id": "...",
  "type": "CONTAINS|CALLS|IMPORTS|RETURNS|RAISES|READS|WRITES|REFERENCES|DEPENDS_ON|MENTIONS|DEFINED_BY|RELATED_TO",
  "description": "one sentence explaining why this edge exists",
  "evidence_path": "<file path>",
  "evidence_line": <line number where you saw this>
}

Rules:
- One node per module, class, function, and method.
- Fill signature, inputs, outputs for every callable.
- Emit CALLS edges for functions invoked in the body.
- Emit IMPORTS edges for every import statement (resolve relative imports to repo paths).
- Emit RAISES for explicit raise statements.
- Emit READS/WRITES for file, database or environment variable access.
- Every node except the file root sets parent_local_id to its enclosing node.
- local_id format: "<path>" for files, "<path>::<symbol>" for symbols.
- line_start/line_end are absolute line numbers in the original file.
- If your chunk started at offset N, add N-1 to all line numbers.
- Only emit a relationship you actually saw. Put the exact line in evidence_line.
- If a referenced symbol is in a file you were not shown, still emit the relationship
  using the path from the import — the Linker will resolve it.
- Twenty accurate nodes beat eighty guessed ones. Never invent symbols or line numbers.
- description must never be blank and must never just restate the name.
"""


def _chunk_file(content: str, chunk_lines: int = config.CHUNK_LINES) -> List[Tuple[int, str]]:
    """Split file content into (start_line_1indexed, chunk_text) tuples."""
    lines = content.splitlines(keepends=True)
    chunks = []
    for i in range(0, len(lines), chunk_lines):
        start = i + 1  # 1-indexed
        chunk = "".join(lines[i : i + chunk_lines])
        chunks.append((start, chunk))
    return chunks


def run_code_agent(
    root: Path,
    relpath: str,
    client: LLMClient,
) -> ExtractorOutput:
    """
    Run CodeGraphAgent on one file.
    Returns ExtractorOutput. Raises LLMFormatError on bad model output.
    """
    content = read_file(root, relpath)
    file_lines = content.count("\n") + 1
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
