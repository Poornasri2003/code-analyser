"""Shared test fixtures."""
from __future__ import annotations
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

# Set env so config loads without real credentials
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("STORE_TYPE", "inmemory")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")


@pytest.fixture
def tmp_repo(tmp_path):
    """A tiny fake Python repo on disk."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        'def hello():\n    """Say hello."""\n    return "hello"\n\n'
        'def greet(name: str) -> str:\n    """Greet a person."""\n    return hello() + name\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Test Repo\n\nThis is a test repository.\n\n## Usage\n\nCall `hello()`.\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("click\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_llm():
    from code_analyser.llm.fake_client import FakeLLMClient
    return FakeLLMClient()


@pytest.fixture
def inmemory_store():
    from code_analyser.store.inmemory import InMemoryStore
    return InMemoryStore()


@pytest.fixture
def fake_embedder():
    from code_analyser.tools.embed import FakeEmbedder
    return FakeEmbedder()


def make_planner_response(manifest_paths):
    """Build a valid PlannerOutput dict for the given paths."""
    routes = []
    for p in manifest_paths:
        if p.endswith(".py"):
            routes.append({"path": p, "route": "code", "priority": 2})
        elif p.endswith(".md"):
            routes.append({"path": p, "route": "doc", "priority": 2})
        else:
            routes.append({"path": p, "route": "skip", "priority": 3, "reason": "not source"})
    return {
        "kind": "code",
        "reasoning": "Python source files and markdown docs detected.",
        "project_summary": "A small Python test project.",
        "routes": routes,
    }


def make_extractor_response():
    """Build a minimal valid ExtractorOutput dict."""
    return {
        "nodes": [
            {
                "local_id": "src/main.py",
                "type": "File",
                "name": "main.py",
                "description": "The main module containing hello and greet functions.",
                "parent_local_id": None,
                "path": "src/main.py",
                "line_start": 1,
                "line_end": 7,
                "properties": {"language": "python"},
            },
            {
                "local_id": "src/main.py::hello",
                "type": "Function",
                "name": "hello",
                "description": "Returns the string 'hello'. A simple greeting function.",
                "parent_local_id": "src/main.py",
                "path": "src/main.py",
                "line_start": 1,
                "line_end": 3,
                "properties": {"signature": "hello()", "outputs": "str"},
            },
        ],
        "relationships": [
            {
                "source_local_id": "src/main.py",
                "target_local_id": "src/main.py::hello",
                "type": "CONTAINS",
                "description": "The file contains the hello function.",
                "evidence_path": "src/main.py",
                "evidence_line": 1,
            }
        ],
    }


def make_linker_response():
    return {"resolved": [], "merges": [], "dropped": []}


def make_answer_response(node_ids=None):
    return {
        "answer": "The hello function in src/main.py returns the string 'hello'. "
                  "It is called by the greet function which concatenates it with a name parameter. "
                  "This creates a simple greeting system with two cooperating functions.",
        "citations": [
            {"node_id": (node_ids or ["dummy_id"])[0], "path": "src/main.py", "line_start": 1, "line_end": 3}
        ],
        "grounded": True,
        "subgraph_node_ids": node_ids or ["dummy_id"],
    }
