"""Compare files between two local folders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from .scanner import LocalFileInfo
from .utils import (
    fmt_dt,
    fmt_size,
    local_file_mtime_utc,
    normalize_to_utc,
    sha256_file,
)

logger = logging.getLogger("foldersync.comparator")


class DiffReason(str, Enum):
    NEWER_SOURCE = "Source is newer"
    CHECKSUM_DIFFERS = "Checksum differs"
    SIZE_DIFFERS = "Size differs"
    NEW_FILE = "New file (not in target)"
    ONLY_IN_TARGET = "Only in target"
    UP_TO_DATE = "Up to date"


class SuggestedAction(str, Enum):
    COPY_REPLACE = "Copy & Replace"
    COPY_NEW = "Copy (new file)"
    SKIP = "Skip"
    DELETE_TARGET = "Delete from target"


@dataclass
class ComparisonEntry:
    """Result of comparing one file between source and target folders."""

    relative_path: str
    source_path: str
    source_timestamp: Optional[datetime]
    source_size: Optional[int]
    target_path: str
    target_timestamp: Optional[datetime]
    target_size: Optional[int]
    diff_reason: DiffReason
    action: SuggestedAction
    source_checksum: Optional[str] = None
    target_checksum: Optional[str] = None
    selected: bool = False  # GUI checkbox state

    def summary_row(self) -> dict[str, str]:
        """Return a dict suitable for table display."""
        return {
            "Relative Path": self.relative_path,
            "Source Date": fmt_dt(self.source_timestamp),
            "Target Date": fmt_dt(self.target_timestamp),
            "Source Size": fmt_size(self.source_size),
            "Target Size": fmt_size(self.target_size),
            "Reason": self.diff_reason.value,
            "Action": self.action.value,
        }


def compare_folders(
    source_files: list[LocalFileInfo],
    target_files: list[LocalFileInfo],
    source_root: Path,
    target_root: Path,
    tolerance_seconds: int = 120,
    cancel_event: Optional[object] = None,
    progress_callback: Optional[object] = None,
) -> list[ComparisonEntry]:
    """Compare source files against target folder counterparts.

    Returns a list of ComparisonEntry objects with diff reasons and suggested actions.
    """
    results: list[ComparisonEntry] = []
    tolerance = timedelta(seconds=tolerance_seconds)

    # Build a lookup of target files by relative path
    target_map: dict[str, LocalFileInfo] = {f.relative: f for f in target_files}
    source_map: dict[str, LocalFileInfo] = {f.relative: f for f in source_files}

    # --- Compare source files against target ---
    for idx, sf in enumerate(source_files):
        if cancel_event and hasattr(cancel_event, "is_set") and cancel_event.is_set():
            break

        if progress_callback:
            progress_callback(f"Comparing {idx + 1}/{len(source_files)}: {sf.relative}")  # type: ignore[operator]

        target_path = target_root / sf.relative
        tf = target_map.get(sf.relative)

        entry = ComparisonEntry(
            relative_path=sf.relative,
            source_path=str(sf.path),
            source_timestamp=sf.mtime,  # type: ignore[arg-type]
            source_size=sf.size,
            target_path=str(target_path),
            target_timestamp=tf.mtime if tf else None,  # type: ignore[arg-type]
            target_size=tf.size if tf else None,
            diff_reason=DiffReason.UP_TO_DATE,
            action=SuggestedAction.SKIP,
        )

        # Case 1: file missing in target
        if tf is None:
            entry.diff_reason = DiffReason.NEW_FILE
            entry.action = SuggestedAction.COPY_NEW
            entry.selected = True
            results.append(entry)
            continue

        # Case 2: compare timestamps
        source_dt = normalize_to_utc(sf.mtime) if sf.mtime else None  # type: ignore[arg-type]
        target_dt = normalize_to_utc(tf.mtime) if tf.mtime else None  # type: ignore[arg-type]

        if source_dt and target_dt:
            if source_dt > target_dt + tolerance:
                entry.diff_reason = DiffReason.NEWER_SOURCE
                entry.action = SuggestedAction.COPY_REPLACE
                entry.selected = True
                results.append(entry)
                continue

            # Timestamps close but sizes differ → checksum
            if abs(source_dt - target_dt) <= tolerance and sf.size != tf.size:
                entry = _checksum_compare(entry, sf.path, tf.path)
                results.append(entry)
                continue

        # Case 3: sizes differ (no reliable timestamps)
        if sf.size != tf.size:
            entry.diff_reason = DiffReason.SIZE_DIFFERS
            entry = _checksum_compare(entry, sf.path, tf.path)
            results.append(entry)
            continue

        # Case 4: same size, same timestamp → up to date
        entry.diff_reason = DiffReason.UP_TO_DATE
        entry.action = SuggestedAction.SKIP
        results.append(entry)

    # --- Files only in target (optional info) ---
    for rel, tf in target_map.items():
        if rel not in source_map:
            entry = ComparisonEntry(
                relative_path=rel,
                source_path="",
                source_timestamp=None,
                source_size=None,
                target_path=str(tf.path),
                target_timestamp=tf.mtime,  # type: ignore[arg-type]
                target_size=tf.size,
                diff_reason=DiffReason.ONLY_IN_TARGET,
                action=SuggestedAction.SKIP,
                selected=False,
            )
            results.append(entry)

    return results


def _checksum_compare(
    entry: ComparisonEntry,
    source_path: Path,
    target_path: Path,
) -> ComparisonEntry:
    """Compare SHA-256 checksums of source and target files."""
    try:
        src_hash = sha256_file(source_path)
        tgt_hash = sha256_file(target_path)
        entry.source_checksum = src_hash
        entry.target_checksum = tgt_hash
        if src_hash != tgt_hash:
            entry.diff_reason = DiffReason.CHECKSUM_DIFFERS
            entry.action = SuggestedAction.COPY_REPLACE
            entry.selected = True
        else:
            entry.diff_reason = DiffReason.UP_TO_DATE
            entry.action = SuggestedAction.SKIP
    except OSError as exc:
        logger.warning("Checksum compare failed: %s", exc)
        entry.diff_reason = DiffReason.SIZE_DIFFERS
        entry.action = SuggestedAction.COPY_REPLACE
        entry.selected = True
    return entry
