"""
Shared data model for comparison results.
"""
from dataclasses import dataclass, field
from typing import Optional

# ── Status constants ──────────────────────────────────────────────────────────
STATUS_IDENTICAL = "identical"
STATUS_DIFFERENT = "different"
STATUS_ONLY_A    = "only_a"
STATUS_ONLY_B    = "only_b"
STATUS_ERROR     = "error"

# ── Decision constants ────────────────────────────────────────────────────────
DECISION_PENDING  = "pending"
DECISION_REVIEWED = "reviewed"
DECISION_IGNORED  = "ignored"
DECISION_NA       = "n/a"       # used for identical files

# ── Human-readable labels ─────────────────────────────────────────────────────
STATUS_LABELS: dict[str, str] = {
    STATUS_IDENTICAL: "Identical",
    STATUS_DIFFERENT: "Different",
    STATUS_ONLY_A:    "Only in A",
    STATUS_ONLY_B:    "Only in B",
    STATUS_ERROR:     "Error",
}

DECISION_LABELS: dict[str, str] = {
    DECISION_PENDING:  "Pending",
    DECISION_REVIEWED: "Reviewed",
    DECISION_IGNORED:  "Ignored",
    DECISION_NA:       "N/A",
}

# Background colours for status badges (light pastel palette)
STATUS_COLORS: dict[str, str] = {
    STATUS_IDENTICAL: "#d4edda",   # soft green
    STATUS_DIFFERENT: "#fff3cd",   # soft amber
    STATUS_ONLY_A:    "#cce5ff",   # soft blue
    STATUS_ONLY_B:    "#e2d9f3",   # soft lavender
    STATUS_ERROR:     "#f8d7da",   # soft red
}


@dataclass
class ResultItem:
    """Represents one file-pair comparison result."""
    key:       str                   # matching key (filename or relative path)
    path_a:    Optional[str]         # absolute path in Folder A (None if absent)
    path_b:    Optional[str]         # absolute path in Folder B (None if absent)
    status:    str = STATUS_DIFFERENT
    decision:  str = DECISION_PENDING
    error_msg: Optional[str] = None

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "key":       self.key,
            "path_a":    self.path_a,
            "path_b":    self.path_b,
            "status":    self.status,
            "decision":  self.decision,
            "error_msg": self.error_msg,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResultItem":
        return cls(
            key       = d["key"],
            path_a    = d.get("path_a"),
            path_b    = d.get("path_b"),
            status    = d.get("status",    STATUS_DIFFERENT),
            decision  = d.get("decision",  DECISION_PENDING),
            error_msg = d.get("error_msg"),
        )
