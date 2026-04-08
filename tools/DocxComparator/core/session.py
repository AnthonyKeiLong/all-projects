"""
Session persistence – save/load the full application state as JSON.
"""
import json
from typing import Any, Dict, List

from core.models import ResultItem

SESSION_VERSION = "1.0"


def save_session(
    filepath: str,
    folder_a:  str,
    folder_b:  str,
    recursive: bool,
    match_by:  str,
    results:   List[ResultItem],
) -> None:
    """Serialise the current session to *filepath* (UTF-8 JSON)."""
    payload: Dict[str, Any] = {
        "version":   SESSION_VERSION,
        "folder_a":  folder_a,
        "folder_b":  folder_b,
        "recursive": recursive,
        "match_by":  match_by,
        "results":   [r.to_dict() for r in results],
    }
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def load_session(filepath: str) -> Dict[str, Any]:
    """
    Load a session from *filepath*.

    Returns a dict with keys:
        folder_a, folder_b, recursive, match_by, results (List[ResultItem]).

    Raises:
        ValueError: if the file cannot be parsed.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid session file: {exc}") from exc

    return {
        "folder_a":  data.get("folder_a",  ""),
        "folder_b":  data.get("folder_b",  ""),
        "recursive": data.get("recursive", True),
        "match_by":  data.get("match_by",  "filename"),
        "results":   [ResultItem.from_dict(r) for r in data.get("results", [])],
    }
