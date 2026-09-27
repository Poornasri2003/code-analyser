"""
Orchestrator — owns the full analysis run.

Sequence:
  1. resolve source, build file manifest
  2. call Planner once -> routing plan
  3. execute plan file by file (code -> CodeAgent, doc -> DocAgent, skip -> skip)
  4. validate each agent's JSON, assign global ids
  5. call Linker once over the staged graph
  6. embed, write to store in batches
  7. record run report
"""
from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_analyser import config
from code_analyser.models import (
    ExtractorOutput, GraphEdge, GraphNode, ManifestEntry,
    RunReport, StoredEdge, StoredNode,
)
from code_analyser.llm.protocol import LLMClient, LLMFormatError
from code_analyser.tools.source import resolve_source, walk_files
from code_analyser.tools.fs import read_file
from code_analyser.tools.graph_tools import validate_graph, assign_ids
from code_analyser.agents.planner import run_planner
from code_analyser.agents.code_agent import run_code_agent
from code_analyser.agents.doc_agent import run_doc_agent
from code_analyser.agents.linker import run_linker, apply_linker_output


def _count_lines(root: Path, relpath: str) -> int:
    try:
        content = read_file(root, relpath)
        return content.count("\n") + 1
    except Exception:
        return 0


def _build_manifest(root: Path, relpaths: List[str]) -> List[ManifestEntry]:
    entries = []
    for rel in relpaths:
        fp = root / rel
        try:
            size = fp.stat().st_size
            line_count = _count_lines(root, rel)
            entries.append(
                ManifestEntry(
                    path=rel,
                    extension=fp.suffix.lower(),
                    size=size,
                    line_count=line_count,
                )
            )
        except OSError:
            pass
    return entries


class Orchestrator:
    def __init__(
        self,
        client: LLMClient,
        store,
        embed_fn=None,
        workdir: Optional[Path] = None,
    ) -> None:
        self.client = client
        self.store = store
        self.trace = None  # optional TraceLog; set by callers that want tracing
        self.workdir = workdir or Path("/tmp/code_analyser_workdir")
        if embed_fn is None:
            from code_analyser.tools.embed import embed
            self.embed_fn = embed
        else:
            self.embed_fn = embed_fn

    def _stage(self, name: str, event: str = "start", **detail):
        """Record a pipeline step and tell the wrapped client which stage its
        next call belongs to."""
        if self.trace is not None:
            self.trace.add(name, event, **detail)
        if hasattr(self.client, "stage"):
            self.client.stage = name

    def analyse(
        self,
        source: str,
        user_id: str,
        run_id: Optional[str] = None,
        max_files: Optional[int] = None,
    ) -> RunReport:
        t0 = time.time()
        run_id = run_id or str(uuid.uuid4())[:8]
        max_files = max_files or config.MAX_FILES

        report = RunReport(run_id=run_id, user_id=user_id, source=source)

        # ── 1. Resolve source ─────────────────────────────────────────────────
        self._stage("resolve", "start", source=source)
        self.workdir.mkdir(parents=True, exist_ok=True)
        root = resolve_source(source, self.workdir)
        self._stage("resolve", "done", root=str(root))

        # ── 2. Walk files ─────────────────────────────────────────────────────
        # The planner sees the whole tree, because truncating here would hand it
        # an alphabetical slice and its priorities could never surface the files
        # that matter. max_files is applied after routing instead.
        relpaths = walk_files(root)[:config.PLANNER_MANIFEST_LIMIT]
        manifest = _build_manifest(root, relpaths)
        report.files_total = len(manifest)
        self._stage("walk", "done", files_found=len(manifest))

        if not manifest:
            report.elapsed_seconds = time.time() - t0
            return report

        # ── 3. Planner ────────────────────────────────────────────────────────
        self._stage("planner", "start", files=len(manifest))
        plan = self._retry_agent(
            lambda: run_planner(root, manifest, self.client),
            "planner",
            report,
        )
        if plan is None:
            report.elapsed_seconds = time.time() - t0
            return report

        # Highest-priority files first, then apply the budget, so a capped run
        # analyses the important files rather than the alphabetically first ones.
        routes_by_path = {r.path: r for r in plan.routes}
        analysable = sorted(
            (r for r in plan.routes if r.route != "skip"),
            key=lambda r: (r.priority, r.path),
        )
        report.files_skipped += len(plan.routes) - len(analysable)
        sorted_routes = analysable[:max_files]
        report.files_skipped += len(analysable) - len(sorted_routes)
        self._stage("planner", "done", kind=plan.kind,
                    selected=[r.path for r in sorted_routes],
                    skipped=len(plan.routes) - len(sorted_routes),
                    reasoning=(plan.reasoning or "")[:300])

        # ── 4. Extract file by file ───────────────────────────────────────────
        staged_nodes: List[GraphNode] = []
        staged_edges: List[GraphEdge] = []
        total_drops: Dict[str, int] = {}

        for route in sorted_routes:
            relpath = route.path
            if route.route == "skip":
                report.files_skipped += 1
                continue

            # get file length for validation
            file_len = next((m.line_count for m in manifest if m.path == relpath), 1000)

            if route.route == "code":
                agent_fn = lambda: run_code_agent(root, relpath, self.client)
            else:
                agent_fn = lambda: run_doc_agent(root, relpath, self.client)

            self._stage(f"extract:{relpath}", "start",
                        file=relpath, route=route.route,
                        index=report.files_processed + report.files_failed + 1,
                        of=len(sorted_routes))
            raw_output = self._retry_agent(agent_fn, relpath, report)
            if raw_output is None:
                report.files_failed += 1
                self._stage(f"extract:{relpath}", "failed", file=relpath)
                continue

            # validate
            clean, drop_report = validate_graph(raw_output.model_dump(), file_len)
            for k, v in drop_report.items():
                total_drops[k] = total_drops.get(k, 0) + v

            staged_nodes.extend(clean.nodes)
            staged_edges.extend(clean.relationships)
            report.files_processed += 1
            self._stage(f"extract:{relpath}", "done", file=relpath,
                        nodes=len(clean.nodes), relationships=len(clean.relationships),
                        dropped={k: v for k, v in drop_report.items() if v})

        report.nodes_dropped = sum(
            v for k, v in total_drops.items() if "node" in k
        )
        report.edges_dropped = sum(
            v for k, v in total_drops.items() if "edge" in k
        )

        staged_batch = ExtractorOutput(nodes=staged_nodes, relationships=staged_edges)

        # ── 5. Linker ─────────────────────────────────────────────────────────
        self._stage("linker", "start", staged_nodes=len(staged_nodes),
                    staged_edges=len(staged_edges))
        linker_output = self._retry_agent(
            lambda: run_linker(staged_batch, self.client, root),
            "linker",
            report,
        )
        if linker_output is not None:
            staged_batch = apply_linker_output(staged_batch, linker_output)
            self._stage("linker", "done",
                        resolved=len(getattr(linker_output, "resolved", []) or []),
                        merges=len(getattr(linker_output, "merges", []) or []),
                        dropped=len(getattr(linker_output, "dropped", []) or []))

        # ── 6. Assign ids ─────────────────────────────────────────────────────
        stored_nodes, stored_edges = assign_ids(staged_batch, user_id, run_id)

        # ── 7. Embed ──────────────────────────────────────────────────────────
        texts = [f"{n.name}: {n.description}" for n in stored_nodes]
        self._stage("embed", "start", vectors=len(texts))
        if texts:
            vectors = self.embed_fn(texts)
            for node, vec in zip(stored_nodes, vectors):
                node.embedding = vec

        # ── 8. Write to store ─────────────────────────────────────────────────
        self.store.ensure_schema()
        nc, ec = self.store.write(stored_nodes, stored_edges, user_id, run_id)
        report.nodes_written = nc
        report.edges_written = ec
        self._stage("store", "done", nodes=nc, edges=ec)

        report.elapsed_seconds = time.time() - t0
        if self.trace is not None:
            report.tokens_used = self.trace.total_tokens
        return report

    def ask(
        self,
        question: str,
        user_id: str,
        run_id: str,
        k: int = 8,
    ) -> Dict[str, Any]:
        from code_analyser.agents.answer import run_answer_agent

        # embed the question
        qvec = self.embed_fn([question])[0]

        # retrieve subgraph
        results = self.store.query(user_id, run_id, qvec, k=k)
        if not results:
            return {
                "answer": "No graph found for this run. Please analyse a source first.",
                "citations": [],
                "grounded": False,
                "subgraph_node_ids": [],
            }

        subgraph = results[0]
        nodes = subgraph.get("nodes", [])
        edges = subgraph.get("edges", [])

        answer = run_answer_agent(question, nodes, edges, self.client)
        return answer.model_dump()

    def _retry_agent(self, fn, label: str, report: RunReport):
        """Run fn(), retry once on LLMFormatError, record failure and return None on second failure."""
        for attempt in range(2):
            try:
                return fn()
            except LLMFormatError as exc:
                if attempt == 0:
                    continue
                report.failures.append({"label": label, "error": str(exc)})
                return None
            except Exception as exc:
                report.failures.append({"label": label, "error": str(exc)})
                return None
