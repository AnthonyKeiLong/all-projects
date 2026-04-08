"""Filename generation, rename operations, and undo."""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from utils import clean_filename, resolve_collision

logger = logging.getLogger(__name__)


def build_filename(
    template: str,
    fields: dict[str, Any],
    original_name: str = "",
    max_length: int = 120,
) -> str:
    """Substitute tokens in *template* using extracted *fields*."""
    tokens = {
        "year": fields.get("year", {}).get("value", ""),
        "publisher": fields.get("publisher", {}).get("value", ""),
        "subject": fields.get("subject", {}).get("value", ""),
        "part": fields.get("part", {}).get("value", ""),
        "mock_number": fields.get("mock_number", {}).get("value", ""),
        "paper": fields.get("paper", {}).get("value", ""),
        "orig": Path(original_name).stem if original_name else "",
    }
    result = template
    for tok, val in tokens.items():
        result = result.replace(f"{{{tok}}}", val)
    # Remove empty bracket groups left over from missing tokens
    result = re.sub(r"\[\s*\]", "", result)
    return clean_filename(result, max_length)


def build_multi_filenames(
    template: str,
    fields: dict[str, Any],
    multi_papers: list[dict[str, str]],
    original_name: str = "",
    max_length: int = 120,
) -> list[str]:
    """Build one suggested filename per detected sub-paper."""
    names: list[str] = []
    for paper in multi_papers:
        mod = dict(fields)
        mod["part"] = {"value": paper["part"], "confidence": 0.85, "snippet": ""}
        names.append(build_filename(template, mod, original_name, max_length))
    return names


def rename_file(
    src: Path,
    dst: Path,
    preserve_timestamps: bool = True,
    resolve_collisions: bool = True,
) -> Path:
    """Rename *src* → *dst*, handling collisions and timestamp preservation."""
    if resolve_collisions:
        dst = resolve_collision(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    stat_before = src.stat() if preserve_timestamps else None
    shutil.move(str(src), str(dst))
    if stat_before:
        os.utime(str(dst), (stat_before.st_atime, stat_before.st_mtime))

    logger.info("Renamed: %s → %s", src, dst)
    return dst


def undo_rename(old_path: str, new_path: str) -> bool:
    """Reverse a single rename.  Returns True on success."""
    src, dst = Path(new_path), Path(old_path)
    if not src.exists():
        logger.error("Undo: source %s missing", new_path)
        return False
    if dst.exists():
        logger.error("Undo: destination %s already exists", old_path)
        return False
    try:
        shutil.move(str(src), str(dst))
        logger.info("Undo: %s → %s", new_path, old_path)
        return True
    except Exception as e:
        logger.error("Undo failed: %s", e)
        return False
