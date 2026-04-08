"""Tests for comparator: local folder comparison logic."""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from WebFileSync.comparator import (
    ComparisonEntry,
    DiffReason,
    SuggestedAction,
    compare_folders,
)
from WebFileSync.scanner import scan_folder


class TestCompareFolders(unittest.TestCase):
    """Test local folder comparison."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.source = self.tmpdir / "source"
        self.target = self.tmpdir / "target"
        self.source.mkdir()
        self.target.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_all_new_files(self):
        """Files in source but not in target → NEW_FILE."""
        (self.source / "a.txt").write_text("hello", encoding="utf-8")
        (self.source / "b.txt").write_text("world", encoding="utf-8")

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        self.assertEqual(len(entries), 2)
        for e in entries:
            self.assertEqual(e.diff_reason, DiffReason.NEW_FILE)
            self.assertEqual(e.action, SuggestedAction.COPY_NEW)
            self.assertTrue(e.selected)

    def test_identical_files(self):
        """Same content, same time → UP_TO_DATE."""
        (self.source / "same.txt").write_text("identical", encoding="utf-8")
        shutil.copy2(self.source / "same.txt", self.target / "same.txt")

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].diff_reason, DiffReason.UP_TO_DATE)
        self.assertEqual(entries[0].action, SuggestedAction.SKIP)
        self.assertFalse(entries[0].selected)

    def test_source_newer(self):
        """Source file is newer than target → NEWER_SOURCE."""
        # Create target first
        (self.target / "file.txt").write_text("old", encoding="utf-8")
        time.sleep(0.1)  # ensure different mtime
        # Create source after (it will be newer)
        (self.source / "file.txt").write_text("new content", encoding="utf-8")

        # Make sure source is actually newer by setting future mtime
        import os
        src_stat = (self.source / "file.txt").stat()
        os.utime(self.source / "file.txt", (src_stat.st_atime, src_stat.st_mtime + 300))

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].diff_reason, DiffReason.NEWER_SOURCE)
        self.assertEqual(entries[0].action, SuggestedAction.COPY_REPLACE)
        self.assertTrue(entries[0].selected)

    def test_only_in_target(self):
        """Files only in target get reported with ONLY_IN_TARGET."""
        (self.target / "orphan.txt").write_text("orphan", encoding="utf-8")

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        target_only = [e for e in entries if e.diff_reason == DiffReason.ONLY_IN_TARGET]
        self.assertEqual(len(target_only), 1)
        self.assertEqual(target_only[0].relative_path, "orphan.txt")
        self.assertFalse(target_only[0].selected)

    def test_size_differs_triggers_checksum(self):
        """Same mtime but different size → checksum comparison."""
        (self.source / "data.bin").write_bytes(b"AAAA")
        (self.target / "data.bin").write_bytes(b"BBBBBB")

        # Set same mtime
        import os
        now = time.time()
        os.utime(self.source / "data.bin", (now, now))
        os.utime(self.target / "data.bin", (now, now))

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertIn(e.diff_reason, (DiffReason.CHECKSUM_DIFFERS, DiffReason.SIZE_DIFFERS))
        self.assertTrue(e.selected)

    def test_nested_folders(self):
        """Nested folder structure is handled correctly."""
        (self.source / "sub").mkdir()
        (self.source / "sub" / "deep.txt").write_text("deep", encoding="utf-8")

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(src_scan.files, tgt_scan.files, self.source, self.target)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].diff_reason, DiffReason.NEW_FILE)
        self.assertIn("deep.txt", entries[0].relative_path)

    def test_tolerance(self):
        """Files within tolerance are considered up to date."""
        (self.source / "tol.txt").write_text("same", encoding="utf-8")
        shutil.copy2(self.source / "tol.txt", self.target / "tol.txt")

        # Nudge source mtime slightly
        import os
        src_stat = (self.source / "tol.txt").stat()
        os.utime(self.source / "tol.txt", (src_stat.st_atime, src_stat.st_mtime + 60))

        src_scan = scan_folder(self.source)
        tgt_scan = scan_folder(self.target)
        entries = compare_folders(
            src_scan.files, tgt_scan.files, self.source, self.target,
            tolerance_seconds=120,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].diff_reason, DiffReason.UP_TO_DATE)


if __name__ == "__main__":
    unittest.main()
