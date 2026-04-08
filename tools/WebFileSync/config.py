"""Configuration management for FolderSync."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass
class Config:
    """Application configuration with sensible defaults."""

    source_folder: str = ""   # reference / "newer" folder
    target_folder: str = ""   # folder to update
    file_extensions: list[str] = field(default_factory=list)  # empty = all
    regex_patterns: list[str] = field(default_factory=list)
    timestamp_tolerance_seconds: int = 120  # 2 minutes
    max_concurrency: int = 4
    dry_run: bool = False
    preserve_timestamps: bool = True
    preserve_permissions: bool = True
    mapping_file: str = ""  # path to CSV/JSON mapping file
    log_to_file: bool = False
    log_file: str = "foldersync.log"
    verbose: bool = False
    debug: bool = False
    backup_dir_name: str = ".foldersync_backups"
    include_hidden: bool = False
    recursive: bool = True

    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to a JSON file."""
        target = path or DEFAULT_CONFIG_PATH
        target.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load configuration from a JSON file, falling back to defaults."""
        target = path or DEFAULT_CONFIG_PATH
        if not target.exists():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            known_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known_fields}
            return cls(**filtered)
        except (json.JSONDecodeError, TypeError):
            return cls()

    def to_dict(self) -> dict:
        return asdict(self)
