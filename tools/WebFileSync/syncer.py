"""Copy/sync manager for local folder operations."""

from __future__ import annotations

import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .backup import BackupManager
from .comparator import ComparisonEntry, SuggestedAction

logger = logging.getLogger("foldersync.syncer")


@dataclass
class SyncResult:
    """Outcome of a single file copy/sync."""

    relative_path: str
    source_path: str
    target_path: str
    success: bool
    error: Optional[str] = None
    backup_path: Optional[str] = None
    bytes_copied: int = 0


def copy_file(
    entry: ComparisonEntry,
    backup_mgr: BackupManager,
    preserve_timestamps: bool = True,
    preserve_permissions: bool = True,
) -> SyncResult:
    """Copy a single file from source to target, backing up existing target first."""
    source = Path(entry.source_path)
    target = Path(entry.target_path)
    result = SyncResult(
        relative_path=entry.relative_path,
        source_path=entry.source_path,
        target_path=entry.target_path,
        success=False,
    )

    # Backup existing target file
    if target.exists():
        try:
            bp = backup_mgr.backup(target)
            result.backup_path = str(bp)
        except OSError as exc:
            result.error = f"Backup failed: {exc}"
            return result

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        if preserve_permissions:
            shutil.copy2(source, target)  # preserves metadata
        else:
            shutil.copy(source, target)

        # Explicitly set mtime from source if desired
        if preserve_timestamps:
            src_stat = source.stat()
            os.utime(target, (src_stat.st_atime, src_stat.st_mtime))

        result.bytes_copied = source.stat().st_size
        result.success = True
    except OSError as exc:
        result.error = str(exc)
        # Restore backup on failure
        if result.backup_path and Path(result.backup_path).exists():
            try:
                backup_mgr.restore_single(Path(result.backup_path), target)
            except OSError:
                pass

    return result


def sync_selected(
    entries: list[ComparisonEntry],
    backup_mgr: BackupManager,
    max_concurrency: int = 4,
    preserve_timestamps: bool = True,
    preserve_permissions: bool = True,
    cancel_event: Optional[object] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[SyncResult]:
    """Copy all selected entries from source to target concurrently.

    Returns a list of SyncResult objects.
    """
    selected = [
        e for e in entries
        if e.selected and e.action in (SuggestedAction.COPY_REPLACE, SuggestedAction.COPY_NEW)
    ]

    if not selected:
        return []

    results: list[SyncResult] = []
    completed = 0

    def _do_copy(entry: ComparisonEntry) -> SyncResult:
        return copy_file(
            entry, backup_mgr,
            preserve_timestamps=preserve_timestamps,
            preserve_permissions=preserve_permissions,
        )

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_map = {executor.submit(_do_copy, e): e for e in selected}

        for future in as_completed(future_map):
            if cancel_event and hasattr(cancel_event, "is_set") and cancel_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break

            sr = future.result()
            results.append(sr)
            completed += 1

            if progress_callback:
                status = "OK" if sr.success else f"FAIL: {sr.error}"
                progress_callback(
                    f"[{completed}/{len(selected)}] {sr.relative_path} → {status}"
                )

    return results
