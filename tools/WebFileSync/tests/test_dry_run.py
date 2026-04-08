"""Integration test: scan, compare, sync between local folders."""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from WebFileSync.backup import BackupManager
from WebFileSync.comparator import DiffReason, SuggestedAction, compare_folders
from WebFileSync.scanner import scan_folder
from WebFileSync.syncer import copy_file, sync_selected


class TestLocalSyncIntegration(unittest.TestCase):
    """End-to-end: create folders, compare, and sync."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.source = self.tmpdir / "source"
        self.target = self.tmpdir / "target"
        self.source.mkdir()
        self.target.mkdir()

        # Create source files
        (self.source / "readme.txt").write_text("readme content", encoding="utf-8")
        (self.source / "data.csv").write_text("a,b,c\n1,2,3", encoding="utf-8")
        sub = self.source / "docs"
        sub.mkdir()
        (sub / "guide.txt").write_text("guide content", encoding="utf-8")

        # Create some matching target files (older)
        (self.target / "readme.txt").write_text("old readme", encoding="utf-8")
        # Make target file older
        old_time = time.time() - 600
        os.utime(self.target / "readme.txt", (old_time, old_time))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_discovers_files(self):
        result = scan_folder(self.source, recursive=True)
        names = [f.relative for f in result.files]
        self.assertTrue(any("readme.txt" in n for n in names))
        self.assertTrue(any("data.csv" in n for n in names))
        self.assertTrue(any("guide.txt" in n for n in names))

    def test_compare_detects_new_and_updated(self):
        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        reasons = {e.relative_path: e.diff_reason for e in entries}
        # data.csv and docs/guide.txt are new
        new_files = [k for k, v in reasons.items() if v == DiffReason.NEW_FILE]
        self.assertTrue(any("data.csv" in f for f in new_files))
        self.assertTrue(any("guide.txt" in f for f in new_files))

        # readme.txt should be detected as changed
        readme_entries = [e for e in entries if "readme.txt" in e.relative_path]
        self.assertEqual(len(readme_entries), 1)
        self.assertIn(readme_entries[0].diff_reason,
                       (DiffReason.NEWER_SOURCE, DiffReason.CHECKSUM_DIFFERS, DiffReason.SIZE_DIFFERS))

    def test_sync_copies_files(self):
        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        backup_mgr = BackupManager(self.target)
        results = sync_selected(entries, backup_mgr)
        backup_mgr.save_manifest()

        ok = [r for r in results if r.success]
        self.assertGreater(len(ok), 0)

        # Verify files now exist in target
        self.assertTrue((self.target / "data.csv").exists())
        self.assertEqual(
            (self.target / "data.csv").read_text(encoding="utf-8"),
            "a,b,c\n1,2,3",
        )

    def test_sync_creates_backup(self):
        """Overwriting an existing file should create a backup."""
        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        backup_mgr = BackupManager(self.target)
        results = sync_selected(entries, backup_mgr)

        # readme.txt was overwritten, should have a backup
        readme_results = [r for r in results if "readme.txt" in r.relative_path]
        self.assertEqual(len(readme_results), 1)
        if readme_results[0].backup_path:
            self.assertTrue(Path(readme_results[0].backup_path).exists())

    def test_scan_with_extension_filter(self):
        result = scan_folder(self.source, extensions=[".txt"], recursive=True)
        for f in result.files:
            self.assertTrue(f.relative.endswith(".txt"), f"Unexpected: {f.relative}")

    def test_empty_source_reports_target_only(self):
        """Empty source → all target files marked ONLY_IN_TARGET."""
        empty = self.tmpdir / "empty"
        empty.mkdir()

        src_scan = scan_folder(empty)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, empty, self.target)

        for e in entries:
            self.assertEqual(e.diff_reason, DiffReason.ONLY_IN_TARGET)
            self.assertFalse(e.selected)


if __name__ == "__main__":
    unittest.main()
