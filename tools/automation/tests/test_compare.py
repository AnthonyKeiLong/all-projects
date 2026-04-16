"""
tests/test_compare.py — Unit tests for sync_site comparison and backup logic.

Uses temporary files and directories (no network, no browser needed).
"""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sync_site import (
    compute_sha256,
    sanitize_filename,
    build_local_path,
    resolve_collision,
    backup_file,
    compare_and_act,
)
import logging


class TestSanitizeFilename(TestCase):
    def test_removes_illegal_chars(self):
        self.assertEqual(sanitize_filename('file<>:"/\\|?*.pdf'), "file_________.pdf")

    def test_strips_dots_and_spaces(self):
        self.assertEqual(sanitize_filename("  ..hello.. "), "hello")

    def test_truncates_long_names(self):
        long_name = "a" * 250 + ".pdf"
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 204)  # 200 + .pdf
        self.assertTrue(result.endswith(".pdf"))

    def test_empty_returns_unnamed(self):
        self.assertEqual(sanitize_filename(""), "unnamed")
        self.assertEqual(sanitize_filename("..."), "unnamed")


class TestComputeSha256(TestCase):
    def test_known_hash(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello world")
            f.flush()
            path = Path(f.name)
        try:
            expected = hashlib.sha256(b"hello world").hexdigest()
            self.assertEqual(compute_sha256(path), expected)
        finally:
            path.unlink()

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            path = Path(f.name)
        try:
            expected = hashlib.sha256(b"").hexdigest()
            self.assertEqual(compute_sha256(path), expected)
        finally:
            path.unlink()


class TestBuildLocalPath(TestCase):
    def test_full_metadata_with_existing_folder(self):
        """When an existing English-named folder matches, use it."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create existing folder structure
            (root / "Assessment Resources" / "Section Quiz" / "1A1 Basic Computation").mkdir(parents=True)
            result = build_local_path(
                root, "Assessment Resources", "Section Quiz",
                "1A", "1 基礎計算", "1.1", "questions.pdf",
            )
            self.assertEqual(
                result,
                root / "Assessment Resources" / "Section Quiz" / "1A1 Basic Computation" / "questions.pdf",
            )

    def test_no_existing_folder_fallback(self):
        """When no folder exists, create one from book + chapter."""
        root = Path("C:/Resources")
        result = build_local_path(
            root, "DSE Kit", "DSE Worksheets",
            "2B", "9 二元一次方程", "", "test.docx",
        )
        self.assertEqual(
            result,
            root / "DSE Kit" / "DSE Worksheets" / "2B9 二元一次方程" / "test.docx",
        )

    def test_no_book_no_chapter(self):
        """Term Exam Paper style — files go directly under PageName."""
        root = Path("C:/Resources")
        result = build_local_path(
            root, "Assessment Resources", "Term Exam Paper",
            "", "", "", "file.xlsx",
        )
        self.assertEqual(
            result,
            root / "Assessment Resources" / "Term Exam Paper" / "file.xlsx",
        )

    def test_prefix_does_not_match_longer_number(self):
        """Folder '1A10 …' must not match when looking for chapter 1."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "Assessment Resources" / "Section Quiz"
            (base / "1A1 Basic Computation").mkdir(parents=True)
            (base / "1A10 Introduction to Coordinates").mkdir(parents=True)
            result = build_local_path(
                root, "Assessment Resources", "Section Quiz",
                "1A", "1 基礎計算", "1.1", "q.pdf",
            )
            self.assertEqual(
                result,
                base / "1A1 Basic Computation" / "q.pdf",
            )


class TestResolveCollision(TestCase):
    def test_no_collision(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file.pdf"
            self.assertEqual(resolve_collision(p), p)

    def test_single_collision(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file.pdf"
            p.write_bytes(b"existing")
            result = resolve_collision(p)
            self.assertEqual(result, Path(td) / "file_1.pdf")

    def test_multiple_collisions(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file.pdf"
            p.write_bytes(b"existing")
            (Path(td) / "file_1.pdf").write_bytes(b"existing2")
            result = resolve_collision(p)
            self.assertEqual(result, Path(td) / "file_2.pdf")


class TestBackupFile(TestCase):
    def test_backup_creates_copy(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "source.pdf"
            src.write_bytes(b"original content")
            backup_root = Path(td) / "backup"

            result = backup_file(src, backup_root, "20260101_120000")

            self.assertTrue(result.exists())
            self.assertEqual(result.read_bytes(), b"original content")
            self.assertIn("20260101_120000", str(result))
            # Original still exists (backup_file uses copy2)
            self.assertTrue(src.exists())

    def test_backup_collision(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "source.pdf"
            src.write_bytes(b"content")
            backup_root = Path(td) / "backup"

            # First backup
            r1 = backup_file(src, backup_root, "20260101_120000")
            # Second backup of same-named file
            r2 = backup_file(src, backup_root, "20260101_120000")

            self.assertNotEqual(r1, r2)
            self.assertTrue(r1.exists())
            self.assertTrue(r2.exists())


class TestCompareAndAct(TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.WARNING)

    def test_new_file_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "downloaded.pdf"
            dl.write_bytes(b"new content")
            local = Path(td) / "local" / "file.pdf"
            backup_root = Path(td) / "backup"

            action, sha_local = compare_and_act(
                dl, local, backup_root, "ts", True, self.logger
            )
            self.assertEqual(action, "would_replace")
            self.assertIsNone(sha_local)
            self.assertFalse(local.exists())  # dry-run: no file created

    def test_new_file_apply(self):
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "downloaded.pdf"
            dl.write_bytes(b"new content")
            local = Path(td) / "local" / "file.pdf"
            backup_root = Path(td) / "backup"

            action, sha_local = compare_and_act(
                dl, local, backup_root, "ts", False, self.logger
            )
            self.assertEqual(action, "new")
            self.assertIsNone(sha_local)
            self.assertTrue(local.exists())
            self.assertEqual(local.read_bytes(), b"new content")

    def test_identical_files_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            content = b"identical content"
            dl = Path(td) / "downloaded.pdf"
            dl.write_bytes(content)
            local_dir = Path(td) / "local"
            local_dir.mkdir()
            local = local_dir / "file.pdf"
            local.write_bytes(content)
            backup_root = Path(td) / "backup"

            action, sha_local = compare_and_act(
                dl, local, backup_root, "ts", False, self.logger
            )
            self.assertEqual(action, "skipped")
            self.assertIsNotNone(sha_local)

    def test_different_files_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "downloaded.pdf"
            dl.write_bytes(b"new version")
            local_dir = Path(td) / "local"
            local_dir.mkdir()
            local = local_dir / "file.pdf"
            local.write_bytes(b"old version")
            backup_root = Path(td) / "backup"

            action, sha_local = compare_and_act(
                dl, local, backup_root, "ts", True, self.logger
            )
            self.assertEqual(action, "would_replace")
            self.assertIsNotNone(sha_local)
            # File unchanged in dry-run
            self.assertEqual(local.read_bytes(), b"old version")

    def test_different_files_apply(self):
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "downloaded.pdf"
            dl.write_bytes(b"new version")
            local_dir = Path(td) / "local"
            local_dir.mkdir()
            local = local_dir / "file.pdf"
            local.write_bytes(b"old version")
            backup_root = Path(td) / "backup"

            action, sha_local = compare_and_act(
                dl, local, backup_root, "ts", False, self.logger
            )
            self.assertEqual(action, "updated")
            self.assertIsNotNone(sha_local)
            # File replaced
            self.assertEqual(local.read_bytes(), b"new version")
            # Backup exists
            backup_files = list(backup_root.rglob("*.pdf"))
            self.assertEqual(len(backup_files), 1)
            self.assertEqual(backup_files[0].read_bytes(), b"old version")


if __name__ == "__main__":
    unittest_main()
