"""Tests for tools 1-8."""
from __future__ import annotations
import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from code_analyser.tools.source import resolve_source, walk_files
from code_analyser.tools.fs import list_dir, read_file
from code_analyser.tools.graph_tools import validate_graph, assign_ids
from code_analyser.models import ExtractorOutput


def _minimal_node(local_id="a.py", name="a.py", description="A source file.", t="File"):
    return {
        "local_id": local_id, "type": t, "name": name,
        "description": description, "path": local_id,
        "line_start": 1, "line_end": 10, "properties": {},
    }


def _sample_batch():
    return ExtractorOutput.model_validate({
        "nodes": [
            _minimal_node("src/main.py", "main.py", "Entry point module."),
            {**_minimal_node("src/main.py::hello", "hello", "Returns hello string.", "Function"),
             "parent_local_id": "src/main.py"},
        ],
        "relationships": [{
            "source_local_id": "src/main.py",
            "target_local_id": "src/main.py::hello",
            "type": "CONTAINS",
            "description": "File contains function.",
            "evidence_path": "src/main.py",
            "evidence_line": 1,
        }],
    })


# ── resolve_source ────────────────────────────────────────────────────────────

def test_resolve_local_dir(tmp_path):
    assert resolve_source(str(tmp_path), tmp_path) == tmp_path


def test_resolve_zip(tmp_path):
    zip_path = tmp_path / "t.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("hello.py", "x = 1\n")
    dest = tmp_path / "work"
    dest.mkdir()
    result = resolve_source(str(zip_path), dest)
    assert (result / "hello.py").exists()


def test_zip_slip_rejected(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../../etc/passwd", "evil")
    dest = tmp_path / "work"
    dest.mkdir()
    with pytest.raises(ValueError, match="Zip-slip"):
        resolve_source(str(zip_path), dest)


def test_resolve_bad_source_raises(tmp_path):
    with pytest.raises(ValueError):
        resolve_source("/no/such/path", tmp_path)


# ── walk_files ────────────────────────────────────────────────────────────────

def test_walk_skips_git(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    assert all(".git" not in f for f in walk_files(tmp_path))
    assert "app.py" in walk_files(tmp_path)


def test_walk_skips_binaries(tmp_path):
    (tmp_path / "b.bin").write_bytes(b"\x00\x00binary")
    (tmp_path / "ok.py").write_text("x = 1\n")
    files = walk_files(tmp_path)
    assert "b.bin" not in files
    assert "ok.py" in files


def test_walk_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("exports={}\n")
    (tmp_path / "app.js").write_text("const x=1;\n")
    assert all("node_modules" not in f for f in walk_files(tmp_path))
    assert "app.js" in walk_files(tmp_path)


def test_walk_deterministic(tmp_repo):
    assert walk_files(tmp_repo) == walk_files(tmp_repo)


# ── read_file ─────────────────────────────────────────────────────────────────

def test_read_file_full(tmp_repo):
    assert "Test Repo" in read_file(tmp_repo, "README.md")


def test_read_file_slice(tmp_repo):
    line1 = read_file(tmp_repo, "src/main.py", start=1, end=1)
    assert "def hello" in line1
    assert "def greet" not in line1


def test_read_file_traversal_blocked(tmp_repo):
    with pytest.raises(ValueError, match="traversal"):
        read_file(tmp_repo, "../../etc/passwd")


# ── validate_graph ────────────────────────────────────────────────────────────

def test_validate_drops_blank_desc():
    raw = {"nodes": [{**_minimal_node(), "description": ""}], "relationships": []}
    clean, report = validate_graph(raw, 100)
    assert len(clean.nodes) == 0
    assert report["nodes_dropped_blank"] >= 1


def test_validate_drops_duplicates():
    n = _minimal_node()
    raw = {"nodes": [n, n.copy()], "relationships": []}
    clean, report = validate_graph(raw, 100)
    assert len(clean.nodes) == 1
    assert report["nodes_dropped_duplicate"] == 1


def test_validate_clamps_lines():
    n = {**_minimal_node(), "line_end": 99999}
    raw = {"nodes": [n], "relationships": []}
    clean, _ = validate_graph(raw, 50)
    assert clean.nodes[0].line_end == 50


def test_validate_nulls_self_parent():
    n = {**_minimal_node(), "parent_local_id": "a.py"}
    raw = {"nodes": [n], "relationships": []}
    clean, report = validate_graph(raw, 100)
    assert clean.nodes[0].parent_local_id is None
    assert report["parent_ids_nulled"] >= 1


def test_validate_drops_dangling_edge():
    raw = {
        "nodes": [_minimal_node("a.py", "a.py", "A file.")],
        "relationships": [{
            "source_local_id": "no_such.py",
            "target_local_id": "a.py",
            "type": "CALLS",
            "description": "calls",
            "evidence_path": "no_such.py",
            "evidence_line": 1,
        }],
    }
    clean, report = validate_graph(raw, 100)
    assert len(clean.relationships) == 0
    assert report["edges_dropped_dangling"] >= 1


# ── assign_ids ────────────────────────────────────────────────────────────────

def test_ids_deterministic():
    b = _sample_batch()
    n1, _ = assign_ids(b, "u", "r")
    n2, _ = assign_ids(b, "u", "r")
    assert [n.id for n in n1] == [n.id for n in n2]


def test_ids_tenant_isolation():
    b = _sample_batch()
    na, _ = assign_ids(b, "userA", "run1")
    nb, _ = assign_ids(b, "userB", "run1")
    assert {n.id for n in na}.isdisjoint({n.id for n in nb})


def test_ancestor_chain():
    b = _sample_batch()
    nodes, _ = assign_ids(b, "u", "r")
    file_node = next(n for n in nodes if n.local_id == "src/main.py")
    func_node = next(n for n in nodes if n.local_id == "src/main.py::hello")
    assert file_node.id in func_node.ancestor_ids
