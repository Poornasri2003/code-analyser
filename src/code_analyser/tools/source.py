"""Source resolution and file walking tools."""
from __future__ import annotations
import os
import zipfile
from pathlib import Path
from typing import List

# Directories to skip entirely
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".venv", "venv", "env", ".env", "node_modules", "bower_components",
    "dist", "build", ".next", ".nuxt", "target", "out",
}

# Extensions treated as binary / not worth extracting
_BINARY_EXTS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".obj",
    ".o", ".a", ".lib", ".class", ".jar", ".war", ".ear",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tiff", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".sqlite3",
}

# Max file size to read (4 MB)
_MAX_BYTES = 4 * 1024 * 1024


def resolve_source(source: str, workdir: Path) -> Path:
    """Resolve *source* to a local directory.

    - If *source* is an existing directory, return its Path.
    - If *source* is a ``.zip`` file, extract it into *workdir* and return
      the extraction root.

    Raises ``ValueError`` for invalid inputs or zip-slip attempts.
    """
    p = Path(source)

    if p.is_dir():
        return p

    if p.is_file() and p.suffix.lower() == ".zip":
        return _extract_zip(p, workdir)

    raise ValueError(
        f"Source {source!r} is not a directory or a .zip file, or does not exist."
    )


def _extract_zip(zip_path: Path, workdir: Path) -> Path:
    dest = workdir / zip_path.stem
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest_resolved)):
                raise ValueError(
                    f"Zip-slip detected: member {member!r} would escape extraction root."
                )
            zf.extract(member, dest)

    return dest


def walk_files(root: Path) -> List[str]:
    """Return a sorted list of relative file paths under *root*.

    Skips:
    - Hidden/build directories (``_SKIP_DIRS``)
    - Binary files (``_BINARY_EXTS``)
    - Files larger than ``_MAX_BYTES``
    """
    root = Path(root)
    results: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place (affects os.walk recursion)
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )

        for fname in sorted(filenames):
            ext = Path(fname).suffix.lower()
            if ext in _BINARY_EXTS:
                continue
            full = Path(dirpath) / fname
            if full.stat().st_size > _MAX_BYTES:
                continue
            rel = full.relative_to(root)
            results.append(str(rel).replace(os.sep, "/"))

    return results
