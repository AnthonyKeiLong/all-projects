"""Report generation (JSON / CSV) and undo mechanism."""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from renamer import undo_rename

logger = logging.getLogger(__name__)


def generate_report(
    results: list[Any],
    rename_actions: list[dict[str, str]],
    output_dir: str,
) -> str:
    """Write a JSON report and return its path."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"report_{ts}.json"

    report: dict[str, Any] = {
        "timestamp": ts,
        "total_files": len(results),
        "actions": rename_actions,
        "details": [],
    }
    for r in results:
        report["details"].append(
            {
                "original_path": r.original_path,
                "sha256": r.sha256,
                "text_method": r.text_method,
                "fields": r.fields,
                "suggested_name": r.suggested_name,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
            }
        )

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Report saved to %s", path)
    return str(path)


def export_csv(report_path: str, csv_path: str = "") -> str:
    """Convert a JSON report to CSV for spreadsheet use."""
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    if not csv_path:
        csv_path = str(Path(report_path).with_suffix(".csv"))

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "Original Path", "SHA256", "Method",
                "Year", "Year Conf", "Publisher", "Pub Conf",
                "Subject", "Subj Conf", "Part", "Part Conf",
                "Suggested Name", "Skipped", "Skip Reason",
            ]
        )
        for d in report.get("details", []):
            fl = d.get("fields", {})
            w.writerow(
                [
                    d.get("original_path", ""), d.get("sha256", ""),
                    d.get("text_method", ""),
                    fl.get("year", {}).get("value", ""),
                    fl.get("year", {}).get("confidence", ""),
                    fl.get("publisher", {}).get("value", ""),
                    fl.get("publisher", {}).get("confidence", ""),
                    fl.get("subject", {}).get("value", ""),
                    fl.get("subject", {}).get("confidence", ""),
                    fl.get("part", {}).get("value", ""),
                    fl.get("part", {}).get("confidence", ""),
                    d.get("suggested_name", ""),
                    d.get("skipped", False),
                    d.get("skip_reason", ""),
                ]
            )
    logger.info("CSV exported to %s", csv_path)
    return csv_path


def undo_from_report(report_path: str) -> list[dict[str, Any]]:
    """Reverse all renames recorded in a report, newest-first."""
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    out: list[dict[str, Any]] = []
    for act in reversed(report.get("actions", [])):
        old, new = act.get("old_path", ""), act.get("new_path", "")
        if old and new:
            ok = undo_rename(old, new)
            out.append({"old": old, "new": new, "undone": ok})
    return out
