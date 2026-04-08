"""Backup and undo manager."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("webfilesync.backup")


class BackupManager:
    """Manages backup copies of local files before they are replaced.

    Backups are stored under ``<local_root>/<backup_dir_name>/<timestamp>/``
    mirroring the original relative path structure.
    """

    def __init__(self, local_root: Path, backup_dir_name: str = ".foldersync_backups") -> None:
        self.local_root = local_root
        self.backup_base = local_root / backup_dir_name
        # Create a timestamped subfolder for this session
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.backup_base / ts
        self._manifest: list[dict] = []

    @property
    def backup_location(self) -> Path:
        return self.backup_base

    def backup(self, file_path: Path) -> Path:
        """Move *file_path* into the session backup directory.

        Returns the backup destination path.
        """
        try:
            rel = file_path.relative_to(self.local_root)
        except ValueError:
            rel = Path(file_path.name)

        dest = self.session_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)  # copy then we let caller overwrite original
        logger.info("Backed up %s → %s", file_path, dest)

        self._manifest.append({
            "original_path": str(file_path),
            "backup_path": str(dest),
            "backed_up_at": datetime.now(timezone.utc).isoformat(),
        })
        return dest

    def save_manifest(self) -> Path:
        """Write the backup manifest JSON file and return its path."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.session_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._manifest, indent=2, default=str),
            encoding="utf-8",
        )
        return manifest_path

    def restore_single(self, backup_path: Path, original_path: Path) -> None:
        """Restore a single file from backup to its original location."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        original_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, original_path)
        logger.info("Restored %s → %s", backup_path, original_path)

    @classmethod
    def undo_from_report(cls, report_path: Path) -> tuple[int, list[str]]:
        """Restore files listed in a JSON report's backup entries.

        Returns (restored_count, list_of_errors).
        """
        data = json.loads(report_path.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("entries", [])

        restored = 0
        errors: list[str] = []

        for entry in entries:
            backup = entry.get("backup_path")
            original = entry.get("original_path") or entry.get("local_path")
            if not backup or not original:
                continue
            bp = Path(backup)
            op = Path(original)
            if not bp.exists():
                errors.append(f"Backup missing: {backup}")
                continue
            try:
                op.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bp, op)
                restored += 1
            except OSError as exc:
                errors.append(f"Restore failed for {original}: {exc}")

        return restored, errors

    @classmethod
    def list_sessions(cls, local_root: Path, backup_dir_name: str = ".foldersync_backups") -> list[Path]:
        """List available backup session directories (newest first)."""
        base = local_root / backup_dir_name
        if not base.exists():
            return []
        dirs = sorted(base.iterdir(), reverse=True)
        return [d for d in dirs if d.is_dir()]
