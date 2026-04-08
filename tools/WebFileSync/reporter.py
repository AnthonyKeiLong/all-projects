"""Report generation in JSON and CSV formats."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .comparator import ComparisonEntry
from .syncer import SyncResult

logger = logging.getLogger("foldersync.reporter")


def build_report_data(
    entries: list[ComparisonEntry],
    sync_results: Optional[list[SyncResult]] = None,
) -> dict:
    """Build a structured report dict from comparison entries and sync results."""
    sr_map: dict[str, SyncResult] = {}
    if sync_results:
        for sr in sync_results:
            sr_map[sr.relative_path] = sr

    report_entries = []
    for e in entries:
        row: dict = {
            "relative_path": e.relative_path,
            "source_path": e.source_path,
            "source_timestamp": e.source_timestamp.isoformat() if e.source_timestamp else None,
            "source_size": e.source_size,
            "source_checksum": e.source_checksum,
            "target_path": e.target_path,
            "target_timestamp": e.target_timestamp.isoformat() if e.target_timestamp else None,
            "target_size": e.target_size,
            "target_checksum": e.target_checksum,
            "diff_reason": e.diff_reason.value,
            "suggested_action": e.action.value,
            "selected": e.selected,
        }

        sr = sr_map.get(e.relative_path)
        if sr:
            row["action_taken"] = "copied" if sr.success else "failed"
            row["backup_path"] = sr.backup_path
            row["error"] = sr.error
            row["bytes_copied"] = sr.bytes_copied
        else:
            row["action_taken"] = "skipped"
            row["backup_path"] = None
            row["error"] = None
            row["bytes_copied"] = 0

        report_entries.append(row)

    total = len(entries)
    selected = sum(1 for e in entries if e.selected)
    copied = sum(1 for sr in (sync_results or []) if sr.success)
    failed = sum(1 for sr in (sync_results or []) if not sr.success)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_files": total,
            "selected": selected,
            "copied": copied,
            "failed": failed,
            "skipped": total - selected,
        },
        "entries": report_entries,
    }


def save_json_report(
    report_data: dict,
    output_dir: Path,
    filename_prefix: str = "report",
) -> Path:
    """Save a detailed JSON report and return the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{filename_prefix}_{ts}.json"
    path.write_text(json.dumps(report_data, indent=2, default=str), encoding="utf-8")
    logger.info("JSON report saved: %s", path)
    return path


def save_csv_report(
    report_data: dict,
    output_dir: Path,
    filename_prefix: str = "report",
) -> Path:
    """Save a CSV summary report and return the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{filename_prefix}_{ts}.csv"

    entries = report_data.get("entries", [])
    if not entries:
        path.write_text("No entries.\n", encoding="utf-8")
        return path

    fieldnames = list(entries[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)

    logger.info("CSV report saved: %s", path)
    return path
