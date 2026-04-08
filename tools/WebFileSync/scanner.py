"""Scan local directories to discover files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .utils import local_file_mtime_utc

logger = logging.getLogger("foldersync.scanner")


@dataclass
class LocalFileInfo:
    """Metadata about a single local file."""

    path: Path
    relative: str  # relative path from the folder root
    size: int = 0
    mtime: Optional[object] = None  # datetime (UTC)


@dataclass
class ScanResult:
    """Aggregate result of a folder scan."""

    files: list[LocalFileInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def _matches_extensions(name: str, extensions: list[str]) -> bool:
    """Return True if filename matches one of the allowed extensions (empty = all)."""
    if not extensions:
        return True
    return any(name.lower().endswith(ext.lower()) for ext in extensions)


def _matches_regex(rel_path: str, patterns: list[str]) -> bool:
    """Return True if relative path matches at least one regex (empty = all pass)."""
    if not patterns:
        return True
    return any(re.search(p, rel_path) for p in patterns)


def scan_folder(
    folder: Path,
    extensions: Optional[list[str]] = None,
    regex_patterns: Optional[list[str]] = None,
    recursive: bool = True,
    include_hidden: bool = False,
    cancel_event: Optional[object] = None,
    progress_callback: Optional[object] = None,
) -> ScanResult:
    """Walk *folder* and collect file metadata.

    Returns a ScanResult with discovered files and any errors.
    """
    result = ScanResult()
    exts = extensions or []
    patterns = regex_patterns or []

    if not folder.exists():
        result.errors.append(f"Folder does not exist: {folder}")
        return result
    if not folder.is_dir():
        result.errors.append(f"Not a directory: {folder}")
        return result

    iterator = folder.rglob("*") if recursive else folder.glob("*")

    for entry in iterator:
        if cancel_event and hasattr(cancel_event, "is_set") and cancel_event.is_set():
            result.cancelled = True
            break

        if not entry.is_file():
            continue

        # Skip hidden files/folders unless requested
        if not include_hidden:
            parts = entry.relative_to(folder).parts
            if any(p.startswith(".") for p in parts):
                continue

        rel = str(entry.relative_to(folder))

        if not _matches_extensions(entry.name, exts):
            continue
        if not _matches_regex(rel, patterns):
            continue

        try:
            stat = entry.stat()
            mtime = local_file_mtime_utc(entry)
            info = LocalFileInfo(
                path=entry,
                relative=rel,
                size=stat.st_size,
                mtime=mtime,
            )
            result.files.append(info)
        except OSError as exc:
            result.errors.append(f"Error reading {entry}: {exc}")

        if progress_callback:
            progress_callback(f"Scanned: {rel}")  # type: ignore[operator]

    return result
