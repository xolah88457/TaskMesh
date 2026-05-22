"""
docs_search — grep-based context retrieval for agents.

Agents can issue <search>query terms</search> blocks in their raw output,
and the orchestrator runs this module to inject matching lines back into
the agent's context via a follow-up prompt.

No vector embeddings, no index — straight lowercase AND-gep over text files
in upload_dir + PROJECT_DIR. Skips binaries and files larger than 1 MB.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".doc", ".docx",
    ".ttf", ".woff", ".woff2", ".otf", ".eot",
    ".pyc", ".class", ".exe", ".dll", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".db", ".sqlite", ".sqlite3",
})

# Directory names skipped wholesale — searching these explodes scan time on real
# projects and they contain no useful agent context.
_SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg",
    "node_modules", "bower_components",
    "venv", ".venv", "env", ".env.d",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", ".turbo", ".vite",
    ".taskmesh", ".idea", ".vscode", ".DS_Store",
    "coverage", "htmlcov",
})

_MAX_FILE_BYTES = 1_048_576  # 1 MiB


class Snippet(NamedTuple):
    file: str
    line: int
    text: str


# ── safe path construction ─────────────────────────────────────────────────────

def _safe_open(path: Path, root: Path) -> Path | None:
    """Resolve and validate a path stays under *root*. Returns None if unsafe."""
    resolved = (root / path).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        return None
    if not resolved.is_file():
        return None
    return resolved


# ── public API ─────────────────────────────────────────────────────────────────

def search_docs(
    query: str,
    search_roots: list[Path],
    max_results: int = 10,
) -> list[Snippet]:
    """Return up to *max_results* snippets where ALL query terms appear.

    Each root in *search_roots* is walked recursively. Files matching
    binary extensions or exceeding 1 MiB are skipped silently.
    """
    terms = [t.strip().lower() for t in re.split(r"\s+", query) if t.strip()]
    if not terms:
        return []

    snippets: list[Snippet] = []

    # Walk manually so we can prune _SKIP_DIRS — rglob has no pruning hook.
    import os as _os
    for root in search_roots:
        if not root.is_dir():
            continue
        root_resolved = root.resolve()
        for dirpath, dirnames, filenames in _os.walk(root):
            # Mutate dirnames in place so os.walk skips them
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                file_path = Path(dirpath) / fname
                if file_path.suffix.lower() in _BINARY_EXTENSIONS:
                    continue
                try:
                    if file_path.stat().st_size > _MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue

                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for li, line in enumerate(text.splitlines(), start=1):
                    lower = line.lower()
                    if all(t in lower for t in terms):
                        try:
                            rel = str(file_path.resolve().relative_to(root_resolved))
                        except ValueError:
                            rel = str(file_path.relative_to(root))
                        snippets.append(Snippet(file=rel, line=li, text=line[:300]))
                        if len(snippets) >= max_results:
                            snippets.sort(key=lambda s: (s.file, s.line))
                            return snippets

    snippets.sort(key=lambda s: (s.file, s.line))
    return snippets


async def search_docs_async(
    query: str,
    search_roots: list[Path],
    max_results: int = 10,
) -> list[Snippet]:
    """Async wrapper that runs search_docs in a worker thread so the file walk
    cannot block the event loop. Use this from any async context."""
    import asyncio
    return await asyncio.to_thread(search_docs, query, search_roots, max_results)
