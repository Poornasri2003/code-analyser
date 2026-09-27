"""Pydantic models for every agent contract."""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ── Planner ───────────────────────────────────────────────────────────────────

class FileRoute(BaseModel):
    path: str
    route: Literal["code", "doc", "skip"]
    priority: int = 2
    reason: Optional[str] = None

# Alias used in some agent files
RouteEntry = FileRoute


class PlannerOutput(BaseModel):
    kind: Literal["code", "docs", "mixed", "data"]
    reasoning: str
    project_summary: str
    routes: List[FileRoute]


# ── Extractor (shared contract for CodeGraphAgent and DocGraphAgent) ──────────

class GraphNode(BaseModel):
    local_id: str
    type: Literal[
        "Repo", "Directory", "File", "Module", "Class", "Function", "Method",
        "Config", "Document", "Section", "Table", "Concept", "Entity",
    ]
    name: str
    description: str
    parent_local_id: Optional[str] = None
    path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_local_id: str
    target_local_id: str
    type: Literal[
        "CONTAINS", "CALLS", "IMPORTS", "RETURNS", "RAISES", "READS", "WRITES",
        "REFERENCES", "DEPENDS_ON", "MENTIONS", "DEFINED_BY", "RELATED_TO",
    ]
    description: str
    evidence_path: str
    evidence_line: Optional[int] = None


class ExtractorOutput(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    relationships: List[GraphEdge] = Field(default_factory=list)


# ── Linker ────────────────────────────────────────────────────────────────────

class ResolvedRef(BaseModel):
    dangling_target: str
    resolved_local_id: str
    confidence: Literal["high", "medium"]

# Alias
LinkerResolved = ResolvedRef


class MergeDirective(BaseModel):
    keep: str
    merge: str
    why: str

# Alias
LinkerMerge = MergeDirective


class DroppedRef(BaseModel):
    dangling_target: str
    why: str

# Alias
LinkerDropped = DroppedRef


class LinkerOutput(BaseModel):
    resolved: List[ResolvedRef] = Field(default_factory=list)
    merges: List[MergeDirective] = Field(default_factory=list)
    dropped: List[DroppedRef] = Field(default_factory=list)


# ── Answer ────────────────────────────────────────────────────────────────────

class Citation(BaseModel):
    node_id: str
    path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None


class AnswerOutput(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    grounded: bool = True
    subgraph_node_ids: List[str] = Field(default_factory=list)


# ── Stored nodes/edges (after id assignment) ──────────────────────────────────

class StoredNode(BaseModel):
    id: str
    local_id: str
    user_id: str
    run_id: str
    type: str
    name: str
    description: str
    path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    parent_id: Optional[str] = None
    ancestor_ids: List[str] = Field(default_factory=list)
    props_json: str = "{}"
    embedding: Optional[List[float]] = None


class StoredEdge(BaseModel):
    source_id: str
    target_id: str
    type: str
    description: str
    evidence_path: str
    evidence_line: Optional[int] = None


# ── Run report ────────────────────────────────────────────────────────────────

class RunReport(BaseModel):
    run_id: str
    user_id: str = ""
    source: str = ""
    files_total: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    nodes_written: int = 0
    edges_written: int = 0
    nodes_dropped: int = 0
    edges_dropped: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0
    failures: List[Dict[str, Any]] = Field(default_factory=list)

# Alias used in some files
AnalysisReport = RunReport


# ── File manifest entry ────────────────────────────────────────────────────────

class ManifestEntry(BaseModel):
    path: str
    extension: str = ""
    size: int = 0
    line_count: int = 0
    # legacy alias
    size_bytes: int = 0
    language: str = ""
