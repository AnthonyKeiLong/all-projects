"""Tests for backup and undo logic."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from WebFileSync.backup import BackupManager


class TestBackupManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.local_root = self.tmpdir / "local"
        self.local_root.mkdir()
        # Create a sample file
        self.sample = self.local_root / "test.txt"
        self.sample.write_text("original content", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_backup_creates_copy(self):
        mgr = BackupManager(self.local_root)
        dest = mgr.backup(self.sample)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(encoding="utf-8"), "original content")
        # Original should still exist (backup is a copy)
        self.assertTrue(self.sample.exists())

    def test_restore_single(self):
        mgr = BackupManager(self.local_root)
        dest = mgr.backup(self.sample)
        # Overwrite original
        self.sample.write_text("modified", encoding="utf-8")
        mgr.restore_single(dest, self.sample)
        self.assertEqual(self.sample.read_text(encoding="utf-8"), "original content")

    def test_save_manifest(self):
        mgr = BackupManager(self.local_root)
        mgr.backup(self.sample)
        manifest_path = mgr.save_manifest()
        self.assertTrue(manifest_path.exists())
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)
        self.assertIn("original_path", data[0])
        self.assertIn("backup_path", data[0])

    def test_undo_from_report(self):
        mgr = BackupManager(self.local_root)
        dest = mgr.backup(self.sample)

        # Create a report-like JSON
        report = [
            {"original_path": str(self.sample), "backup_path": str(dest)},
        ]
        report_path = self.tmpdir / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        # Modify the original
        self.sample.write_text("replaced", encoding="utf-8")

        restored, errors = BackupManager.undo_from_report(report_path)
        self.assertEqual(restored, 1)
        self.assertEqual(errors, [])
        self.assertEqual(self.sample.read_text(encoding="utf-8"), "original content")

    def test_list_sessions(self):
        mgr = BackupManager(self.local_root)
        mgr.backup(self.sample)
        mgr.save_manifest()
        sessions = BackupManager.list_sessions(self.local_root)
        self.assertGreaterEqual(len(sessions), 1)

    def test_backup_nested_file(self):
        subdir = self.local_root / "sub" / "dir"
        subdir.mkdir(parents=True)
        nested = subdir / "nested.txt"
        nested.write_text("nested", encoding="utf-8")

        mgr = BackupManager(self.local_root)
        dest = mgr.backup(nested)
        self.assertTrue(dest.exists())
        self.assertIn("sub", str(dest))


if __name__ == "__main__":
    unittest.main()
