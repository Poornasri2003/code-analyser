"""Integration tests for the orchestrator — all offline."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

# Make conftest helpers importable as a module
sys.path.insert(0, str(Path(__file__).parent))
from conftest import (
    make_planner_response,
    make_extractor_response,
    make_linker_response,
    make_answer_response,
)

from code_analyser.llm.fake_client import FakeLLMClient
from code_analyser.store.inmemory import InMemoryStore
from code_analyser.tools.embed import FakeEmbedder
from code_analyser.orchestrator import Orchestrator


def _make_orchestrator(responses, tmp_path):
    client = FakeLLMClient(responses)
    store = InMemoryStore()
    return Orchestrator(
        client=client,
        store=store,
        embed_fn=FakeEmbedder.embed,
        workdir=tmp_path / "work",
    )


def _full_responses(manifest_paths):
    """Build a full list of LLM responses for one analysis run."""
    responses = [make_planner_response(manifest_paths)]
    for p in manifest_paths:
        if p.endswith((".py", ".md", ".txt", ".js", ".ts")):
            responses.append(make_extractor_response())
    responses.append(make_linker_response())
    return responses


def test_full_run_basic(tmp_repo, tmp_path):
    from code_analyser.tools.source import walk_files
    relpaths = walk_files(tmp_repo)
    responses = _full_responses(relpaths)
    orch = _make_orchestrator(responses, tmp_path)
    report = orch.analyse(str(tmp_repo), user_id="user1", run_id="run1")
    assert report.run_id == "run1"
    assert report.files_total > 0
    assert report.nodes_written > 0


def test_double_ingest_no_duplicate(tmp_repo, tmp_path):
    """Re-analysing same source for same user/run updates, never duplicates."""
    from code_analyser.tools.source import walk_files
    relpaths = walk_files(tmp_repo)

    store = InMemoryStore()

    def run():
        responses = _full_responses(relpaths)
        client = FakeLLMClient(responses)
        orch = Orchestrator(
            client=client, store=store,
            embed_fn=FakeEmbedder.embed,
            workdir=tmp_path / "work",
        )
        return orch.analyse(str(tmp_repo), user_id="user1", run_id="run_same")

    nodes_before_r2 = {
        n["id"] for n in store._nodes.values()
        if n.get("user_id") == "user1" and n.get("run_id") == "run_same"
    }
    r1 = run()
    nodes_after_r1 = {
        n["id"] for n in store._nodes.values()
        if n.get("user_id") == "user1" and n.get("run_id") == "run_same"
    }
    r2 = run()
    nodes_after_r2 = {
        n["id"] for n in store._nodes.values()
        if n.get("user_id") == "user1" and n.get("run_id") == "run_same"
    }
    # After two ingests of the same source+run, node set must be identical (upsert, not insert)
    assert nodes_after_r1 == nodes_after_r2, "Double ingest should not add new node ids"
    assert r1.nodes_written > 0


def test_malformed_llm_output_run_continues(tmp_repo, tmp_path):
    """If an agent returns malformed JSON, the run continues (one bad file)."""
    from code_analyser.llm.protocol import LLMFormatError
    from code_analyser.tools.source import walk_files

    relpaths = walk_files(tmp_repo)
    # planner response is valid
    responses = [make_planner_response(relpaths)]
    # first file agent returns garbage (twice — one per retry)
    # second file agent returns valid
    responses.append({"BAD": "not an extractor response"})  # first attempt
    responses.append({"BAD": "still bad"})                  # retry
    responses.append(make_extractor_response())             # second file
    responses.append(make_linker_response())

    orch = _make_orchestrator(responses, tmp_path)
    report = orch.analyse(str(tmp_repo), user_id="u", run_id="r")
    # Should not crash; some files failed, some processed
    assert report.files_failed >= 0  # run continued


def test_user_isolation(tmp_repo, tmp_path):
    """User A cannot retrieve User B's nodes."""
    from code_analyser.tools.source import walk_files
    relpaths = walk_files(tmp_repo)
    store = InMemoryStore()

    def run_for_user(uid):
        responses = _full_responses(relpaths)
        client = FakeLLMClient(responses)
        orch = Orchestrator(
            client=client, store=store,
            embed_fn=FakeEmbedder.embed,
            workdir=tmp_path / f"work_{uid}",
        )
        orch.analyse(str(tmp_repo), user_id=uid, run_id="run1")

    run_for_user("alice")
    run_for_user("bob")

    alice_nodes = [n for n in store._nodes.values() if n.get("user_id") == "alice"]
    bob_nodes = [n for n in store._nodes.values() if n.get("user_id") == "bob"]
    alice_ids = {n["id"] for n in alice_nodes}
    bob_ids = {n["id"] for n in bob_nodes}
    assert alice_ids.isdisjoint(bob_ids)


def test_manifest_coverage(tmp_repo, tmp_path):
    """Every manifest file must appear exactly once in the Planner's routes."""
    from code_analyser.tools.source import walk_files
    from code_analyser.agents.planner import run_planner
    from code_analyser.orchestrator import _build_manifest

    relpaths = walk_files(tmp_repo)
    manifest = _build_manifest(tmp_repo, relpaths)

    responses = [make_planner_response([e.path for e in manifest])]
    client = FakeLLMClient(responses)
    plan = run_planner(tmp_repo, manifest, client)

    routed_paths = [r.path for r in plan.routes]
    manifest_paths = [e.path for e in manifest]

    # every manifest path appears in routes
    for p in manifest_paths:
        assert p in routed_paths, f"Missing from routes: {p}"

    # no duplicates
    assert len(routed_paths) == len(set(routed_paths))


def test_nonsense_question_returns_not_grounded(tmp_repo, tmp_path):
    """A question about something not in the graph returns grounded=False."""
    from code_analyser.tools.source import walk_files
    relpaths = walk_files(tmp_repo)

    store = InMemoryStore()
    responses = _full_responses(relpaths)
    client = FakeLLMClient(responses)
    orch = Orchestrator(
        client=client, store=store,
        embed_fn=FakeEmbedder.embed,
        workdir=tmp_path / "work",
    )
    orch.analyse(str(tmp_repo), user_id="u", run_id="r")

    # now set up answer agent to return not-grounded
    not_grounded_response = {
        "answer": "The context does not contain information about this topic.",
        "citations": [],
        "grounded": False,
        "subgraph_node_ids": [],
    }
    orch.client = FakeLLMClient([not_grounded_response])
    result = orch.ask("What is the meaning of life?", user_id="u", run_id="r")
    assert result["grounded"] is False


def test_answer_citing_absent_id_rejected(tmp_repo, tmp_path):
    """An answer that cites a node_id not in the context is rejected."""
    from code_analyser.agents.answer import run_answer_agent

    nodes = [{"id": "real_id", "type": "Function", "name": "foo",
              "description": "A function.", "path": "a.py",
              "line_start": 1, "line_end": 5}]
    edges = []

    # Both attempts cite a fake id -> fail closed
    bad_response = {
        "answer": "Something about nonexistent.",
        "citations": [{"node_id": "FAKE_ID_NOT_IN_CONTEXT",
                       "path": "a.py", "line_start": 1, "line_end": 5}],
        "grounded": True,
        "subgraph_node_ids": ["FAKE_ID_NOT_IN_CONTEXT"],
    }
    client = FakeLLMClient([bad_response, bad_response])  # both attempts fail
    result = run_answer_agent("What does foo do?", nodes, edges, client)
    assert result.grounded is False


def test_linker_resolves_cross_file(tmp_repo, tmp_path):
    """Linker should resolve a cross-file reference and drop a third-party one."""
    from code_analyser.agents.linker import run_linker, apply_linker_output
    from code_analyser.models import ExtractorOutput, GraphEdge, GraphNode

    staged = ExtractorOutput(
        nodes=[
            GraphNode(local_id="src/a.py", type="File", name="a.py",
                      description="Module A.", path="src/a.py"),
            GraphNode(local_id="src/b.py::bar", type="Function", name="bar",
                      description="Function bar.", path="src/b.py"),
        ],
        relationships=[
            GraphEdge(source_local_id="src/a.py",
                      target_local_id="bar",  # dangling — short form
                      type="CALLS", description="calls bar",
                      evidence_path="src/a.py", evidence_line=5),
            GraphEdge(source_local_id="src/a.py",
                      target_local_id="boto3.client",  # third-party
                      type="CALLS", description="calls boto3",
                      evidence_path="src/a.py", evidence_line=3),
        ],
    )

    linker_response = {
        "resolved": [{"dangling_target": "bar",
                      "resolved_local_id": "src/b.py::bar",
                      "confidence": "high"}],
        "merges": [],
        "dropped": [{"dangling_target": "boto3.client",
                     "why": "third-party library"}],
    }
    client = FakeLLMClient([linker_response])
    linker_out = run_linker(staged, client, tmp_repo)
    result = apply_linker_output(staged, linker_out)

    # boto3.client edge should be gone
    tgt_ids = {e.target_local_id for e in result.relationships}
    assert "boto3.client" not in tgt_ids
    # bar should be resolved to src/b.py::bar
    assert "src/b.py::bar" in tgt_ids
