"""Filesystem tools: list_dir and read_file."""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional


def list_dir(root: Path, rel_path: str = ".") -> List[str]:
    """List entries in *root/rel_path*, returning relative paths."""
    target = (Path(root) / rel_path).resolve()
    _check_traversal(root, target)
    return sorted(str(e.relative_to(root)).replace("\\", "/") for e in target.iterdir())


def read_file(
    root: Path,
    rel_path: str,
    *,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> str:
    """Read *root/rel_path* and return its contents.

    Parameters
    ----------
    root:
        The repository root (used for traversal checks).
    rel_path:
        Path relative to *root*.
    start:
        First line to return (1-based, inclusive). ``None`` means start of file.
    end:
        Last line to return (1-based, inclusive). ``None`` means end of file.

    Raises ``ValueError`` if *rel_path* traverses outside *root*.
    """
    target = (Path(root) / rel_path).resolve()
    _check_traversal(root, target)

    text = target.read_text(encoding="utf-8", errors="replace")

    if start is None and end is None:
        return text

    lines = text.splitlines(keepends=True)
    s = (start - 1) if start is not None else 0
    e = end if end is not None else len(lines)
    return "".join(lines[s:e])


def _check_traversal(root: Path, target: Path) -> None:
    root_resolved = Path(root).resolve()
    if not str(target).startswith(str(root_resolved)):
        raise ValueError(
            f"Path traversal detected: {target!r} is outside root {root_resolved!r}"
        )
