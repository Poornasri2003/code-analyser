"""Tool 5: search  Tool 6: find_references"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def _ripgrep_search(
    root: Path,
    pattern: str,
    glob: Optional[str] = None,
) -> List[Tuple[str, int, str]]:
    cmd = ["rg", "--line-number", "--no-heading", "--with-filename", pattern, str(root)]
    if glob:
        cmd += ["--glob", glob]
    result = subprocess.run(cmd, capture_output=True, text=True)
    hits = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            path_str, lineno_str, text = parts
            try:
                rel = Path(path_str).relative_to(root).as_posix()
                hits.append((rel, int(lineno_str), text))
            except (ValueError, TypeError):
                pass
    return hits


def _python_search(
    root: Path,
    pattern: str,
    glob: Optional[str] = None,
) -> List[Tuple[str, int, str]]:
    import fnmatch

    rx = re.compile(pattern)
    hits = []
    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue
        if glob and not fnmatch.fnmatch(filepath.name, glob):
            continue
        try:
            for i, line in enumerate(
                filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if rx.search(line):
                    rel = filepath.relative_to(root).as_posix()
                    hits.append((rel, i, line))
        except OSError:
            pass
    return hits


def search(
    root: Path,
    pattern: str,
    glob: Optional[str] = None,
) -> List[Tuple[str, int, str]]:
    """
    Tool 5 — search(root, pattern, glob=None) -> [(path, line, text)]

    Uses ripgrep if available, falls back to pure Python.
    """
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return _ripgrep_search(root, pattern, glob)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _python_search(root, pattern, glob)


def find_references(root: Path, symbol: str) -> List[Tuple[str, int, str]]:
    """
    Tool 6 — find_references(root, symbol) -> [(path, line, text)]

    Word-boundary search for symbol across the repository.
    """
    pattern = rf"\b{re.escape(symbol)}\b"
    return search(root, pattern)
