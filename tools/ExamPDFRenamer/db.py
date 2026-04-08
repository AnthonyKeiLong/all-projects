"""SHA-256-based file tracking database (JSON-backed)."""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


def compute_sha256(filepath: str | Path) -> str:
    """Return the hex SHA-256 digest of *filepath*."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


class FileDB:
    """Thin JSON store keyed by SHA-256, tracking which files have been processed."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._load()

    # -- persistence ----------------------------------------------------------

    def _load(self) -> None:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def save(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # -- public API -----------------------------------------------------------

    def is_processed(self, sha256: str) -> bool:
        return sha256 in self._data

    def get_entry(self, sha256: str) -> Optional[dict]:
        return self._data.get(sha256)

    def add_entry(self, sha256: str, entry: dict) -> None:
        self._data[sha256] = entry
        self.save()

    def remove_entry(self, sha256: str) -> None:
        self._data.pop(sha256, None)
        self.save()
