"""
File upload validation, storage, and text preview for design files.

Users upload design files (Figma, images, PDFs, specs, etc.) before a run.
Files are stored in PROJECT_DIR/uploads/<token>/ and a manifest is built
that the manager agent can include in its context.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".fig", ".sketch", ".pdf", ".tex", ".csv", ".xlsx",
    ".env.example", ".gitignore",
})

MAX_TOTAL_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_FILE_SIZE  = 10 * 1024 * 1024   # 10 MB

_MIME_BY_EXT: dict[str, str] = {
    ".md": "text/markdown", ".txt": "text/plain", ".json": "application/json",
    ".yaml": "text/yaml", ".yml": "text/yaml", ".toml": "text/toml",
    ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/typescript",
    ".jsx": "text/jsx", ".tsx": "text/tsx", ".css": "text/css", ".html": "text/html",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".fig": "application/octet-stream", ".sketch": "application/octet-stream",
    ".pdf": "application/pdf", ".tex": "text/x-tex", ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def validate_filename(filename: str) -> str:
    """Reject empty, dotfile, path traversal, invalid characters.
    Returns stripped filename on success."""
    name = filename.strip()
    if not name:
        raise ValueError("Filename cannot be empty")
    if name.startswith("."):
        raise ValueError(f"Dotfiles not allowed: {name}")
    if "/" in name or "\\" in name:
        raise ValueError(f"Path traversal not allowed: {name}")
    for ch in name:
        if not (ch.isalnum() or ch in "-_. ()+"):
            raise ValueError(f"Invalid character in filename: {ch!r}")
    return name


def validate_extension(filename: str) -> str:
    """Check filename suffix or exact name against allowed set."""
    name = filename.lower()
    if name in ALLOWED_EXTENSIONS:  # exact match (.env.example, .gitignore)
        return name
    ext = Path(name).suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return ext
    raise ValueError(f"File type not allowed: {filename}")


def validate_size(content: bytes) -> int:
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({len(content)} bytes, max {MAX_FILE_SIZE})")
    return len(content)


def extract_text_preview(filepath: Path, max_chars: int = 500) -> str:
    """Return a text preview of the file for the manifest."""
    ext = filepath.suffix.lower()
    name = filepath.name.lower()

    # Text files
    if ext in (".md", ".txt", ".json", ".yaml", ".yml", ".toml",
               ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html",
               ".csv", ".tex") or name in (".env.example", ".gitignore"):
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            return content[:max_chars] + ("…" if len(content) > max_chars else "")
        except Exception:
            return "(could not read text)"

    # PDF
    if ext == ".pdf":
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            text = pdf_extract(str(filepath))
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
        except ImportError:
            return "(PDF preview requires pdfminer.six — install it for text extraction)"

    # Excel
    if ext == ".xlsx":
        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(filepath), read_only=True)
            lines: list[str] = []
            for sheet_name in wb.sheetnames[:3]:
                ws = wb[sheet_name]
                lines.append(f"[Sheet: {sheet_name}]")
                for row in ws.iter_rows(max_row=5, values_only=True):
                    lines.append(" | ".join(str(c) if c is not None else "" for c in row))
            text = "\n".join(lines)
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
        except ImportError:
            return "(Excel preview requires openpyxl — install it for content preview)"

    # Design files
    if ext in (".fig", ".sketch"):
        return "(Design file — will be referenced as-is by agents)"

    # Images
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
        size_kb = filepath.stat().st_size // 1024
        return f"(Image: {filepath.name}, {size_kb} KB)"

    return f"(File: {filepath.name}, {filepath.stat().st_size} bytes)"


def store_files(
    upload_dir: Path,
    files: List[Tuple[str, bytes]],
) -> list[dict]:
    """Validate and store uploaded files. Returns metadata for each file."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    total_size = 0
    stored: list[dict] = []

    for filename, content in files:
        name = validate_filename(filename)
        validate_extension(name)
        size = validate_size(content)
        total_size += size
        if total_size > MAX_TOTAL_SIZE:
            raise ValueError(f"Total upload size exceeds {MAX_TOTAL_SIZE // (1024*1024)} MB")

        dest = upload_dir / name
        dest.write_bytes(content)

        name_lower = name.lower()
        if name_lower in (".env.example", ".gitignore"):
            mime = "text/plain"
        else:
            mime = _MIME_BY_EXT.get(Path(name).suffix.lower(), "application/octet-stream")

        preview = extract_text_preview(dest)

        stored.append({
            "filename": name,
            "path": str(dest.relative_to(upload_dir.parent)) if upload_dir.parent != upload_dir else name,
            "size": size,
            "mime_type": mime,
            "preview": preview,
        })

    return stored


def build_file_manifest(files: list[dict]) -> str:
    """Build a formatted text manifest of uploaded files for the manager agent."""
    if not files:
        return ""

    lines = ["## Uploaded Design Files"]
    for i, f in enumerate(files, 1):
        size_kb = f["size"] / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        lines.append(f"{i}. `{f['filename']}` ({f.get('mime_type', 'unknown')}, {size_str})")
        if f.get("preview"):
            lines.append(f"   Preview: {f['preview'][:200]}")
    return "\n".join(lines)
