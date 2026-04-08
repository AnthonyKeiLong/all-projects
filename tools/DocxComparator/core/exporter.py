"""
Export comparison results to CSV.
"""
import csv
from typing import List

from core.models import ResultItem, STATUS_LABELS, DECISION_LABELS

_FIELDNAMES = [
    "Filename / Key",
    "Status",
    "Decision",
    "Path A",
    "Path B",
    "Error Message",
]


def export_csv(filepath: str, results: List[ResultItem]) -> int:
    """
    Write *results* to a CSV file at *filepath*.

    The file is written with a UTF-8 BOM so that Excel opens it correctly.

    Returns:
        Number of data rows written.
    """
    with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for item in results:
            writer.writerow({
                "Filename / Key": item.key,
                "Status":         STATUS_LABELS.get(item.status,   item.status),
                "Decision":       DECISION_LABELS.get(item.decision, item.decision),
                "Path A":         item.path_a    or "",
                "Path B":         item.path_b    or "",
                "Error Message":  item.error_msg or "",
            })
    return len(results)
