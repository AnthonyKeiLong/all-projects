"""Utility functions for filename cleaning and miscellaneous helpers."""

import re
from pathlib import Path


def clean_filename(name: str, max_length: int = 120) -> str:
    """Clean and normalise a filename string.

    Removes unsafe characters, normalises whitespace, collapses repeated
    bracket separators, and truncates intelligently.
    """
    # Strip characters forbidden on Windows / most filesystems
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    # Normalise whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Collapse repeated brackets and remove empty ones
    name = re.sub(r"\[{2,}", "[", name)
    name = re.sub(r"\]{2,}", "]", name)
    name = re.sub(r"\[\s*\]", "", name)
    # Strip trailing/leading dots and spaces from the stem
    stem = Path(name).stem.strip(". ")
    suffix = Path(name).suffix or ".pdf"
    # Intelligent truncation
    if len(stem) + len(suffix) > max_length:
        stem = stem[: max_length - len(suffix) - 3].rstrip() + "..."
    return stem + suffix


def resolve_collision(filepath: Path) -> Path:
    """Append (1), (2), … to *filepath* until no collision exists."""
    if not filepath.exists():
        return filepath
    stem = filepath.stem
    suffix = filepath.suffix
    parent = filepath.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_cjk_char(char: str) -> bool:
    """Return True when *char* is in a CJK Unified Ideograph block."""
    cp = ord(char)
    return any(
        (
            0x4E00 <= cp <= 0x9FFF,
            0x3400 <= cp <= 0x4DBF,
            0xF900 <= cp <= 0xFAFF,
            0x20000 <= cp <= 0x2A6DF,
        )
    )


def detect_language_hint(text: str) -> str:
    """Rough heuristic: return ``'chi_tra'`` when CJK density is high."""
    if not text:
        return "unknown"
    cjk_count = sum(1 for c in text if is_cjk_char(c))
    alpha_count = sum(1 for c in text if c.isascii() and c.isalpha())
    total = cjk_count + alpha_count
    if total == 0:
        return "unknown"
    return "chi_tra" if cjk_count / total > 0.3 else "eng"
