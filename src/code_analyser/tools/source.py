"""Source resolution and file walking tools."""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import List

# Only these transports are accepted. git's ext:: and file:: helpers can run
# arbitrary commands, so the clone is restricted to the network protocols.
_GIT_URL_RE = re.compile(r"^(https?://|ssh://|git://|[\w.-]+@[\w.-]+:)", re.I)
_ALLOWED_GIT_PROTOCOLS = "https:http:ssh:git"
_CLONE_TIMEOUT_SECONDS = 300

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
    if _GIT_URL_RE.match(source):
        return _clone(source, workdir)

    p = Path(source)

    if p.is_dir():
        return p

    if p.is_file() and p.suffix.lower() == ".zip":
        return _extract_zip(p, workdir)

    raise ValueError(
        f"Source {source!r} is not a git URL, a directory, or a .zip file."
    )


def _force_rmtree(path: Path) -> None:
    """Git marks objects read-only, which blocks rmtree on Windows."""
    def _on_error(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_on_error)


def _fresh_dir(workdir: Path, key: str, *, create: bool) -> Path:
    """A destination unique to *key* and cleared first, so one run can never
    see files left behind by a previous one."""
    dest = workdir / hashlib.sha1(key.encode()).hexdigest()[:16]
    if dest.exists():
        _force_rmtree(dest)
    if dest.exists():
        raise ValueError(f"Could not clear workspace {dest}; it is still in use.")
    if create:
        dest.mkdir(parents=True, exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _clone(url: str, workdir: Path) -> Path:
    # git refuses a non-empty target, so let it create the directory itself.
    dest = _fresh_dir(workdir, url, create=False)
    env = {**os.environ,
           "GIT_ALLOW_PROTOCOL": _ALLOWED_GIT_PROTOCOLS,
           "GIT_TERMINAL_PROMPT": "0"}  # fail instead of hanging on auth
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", url, str(dest)],
        capture_output=True, text=True, timeout=_CLONE_TIMEOUT_SECONDS, env=env,
    )
    if proc.returncode != 0:
        if dest.exists():
            _force_rmtree(dest)
        raise ValueError(f"git clone failed for {url!r}: {proc.stderr.strip()[:300]}")
    return dest


def _extract_zip(zip_path: Path, workdir: Path) -> Path:
    dest = _fresh_dir(workdir, str(zip_path.resolve()), create=True)
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
