"""Tests for scanner: local folder scanning."""

import shutil
import tempfile
import unittest
from pathlib import Path

from WebFileSync.scanner import ScanResult, scan_folder


class TestScanFolder(unittest.TestCase):
    """Test local folder scanning."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Create sample files
        (self.tmpdir / "file1.txt").write_text("hello", encoding="utf-8")
        (self.tmpdir / "file2.csv").write_text("a,b,c", encoding="utf-8")
        (self.tmpdir / "image.png").write_bytes(b"\x89PNG")
        sub = self.tmpdir / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested content", encoding="utf-8")
        (sub / "data.csv").write_text("x,y", encoding="utf-8")
        # Hidden file
        (self.tmpdir / ".hidden").write_text("secret", encoding="utf-8")
        hidden_dir = self.tmpdir / ".hiddendir"
        hidden_dir.mkdir()
        (hidden_dir / "inside.txt").write_text("in hidden dir", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_all_files(self):
        result = scan_folder(self.tmpdir, recursive=True, include_hidden=True)
        names = [f.relative for f in result.files]
        self.assertIn("file1.txt", names)
        self.assertIn("file2.csv", names)
        self.assertIn("image.png", names)
        self.assertTrue(any("nested.txt" in n for n in names))

    def test_scan_non_recursive(self):
        result = scan_folder(self.tmpdir, recursive=False)
        names = [f.relative for f in result.files]
        self.assertIn("file1.txt", names)
        self.assertNotIn("sub\\nested.txt", [n.replace("/", "\\") for n in names])
        # nested files should not appear
        self.assertFalse(any("nested" in n for n in names))

    def test_extension_filter(self):
        result = scan_folder(self.tmpdir, extensions=[".txt"], recursive=True)
        for f in result.files:
            self.assertTrue(f.relative.endswith(".txt"), f"Unexpected: {f.relative}")

    def test_extension_filter_csv(self):
        result = scan_folder(self.tmpdir, extensions=[".csv"], recursive=True)
        self.assertTrue(len(result.files) >= 2)
        for f in result.files:
            self.assertTrue(f.relative.endswith(".csv"))

    def test_exclude_hidden(self):
        result = scan_folder(self.tmpdir, include_hidden=False, recursive=True)
        names = [f.relative for f in result.files]
        for n in names:
            parts = Path(n).parts
            self.assertFalse(any(p.startswith(".") for p in parts),
                             f"Hidden file included: {n}")

    def test_include_hidden(self):
        result = scan_folder(self.tmpdir, include_hidden=True, recursive=True)
        names = [f.relative for f in result.files]
        hidden_found = any(".hidden" in n for n in names)
        self.assertTrue(hidden_found, f"Expected hidden file in {names}")

    def test_regex_filter(self):
        result = scan_folder(self.tmpdir, regex_patterns=[r"file\d"], recursive=True)
        for f in result.files:
            self.assertRegex(f.relative, r"file\d")

    def test_nonexistent_folder(self):
        result = scan_folder(Path("/nonexistent/path/xyz"))
        self.assertEqual(len(result.files), 0)
        self.assertGreater(len(result.errors), 0)

    def test_file_metadata(self):
        result = scan_folder(self.tmpdir, recursive=False)
        found = [f for f in result.files if f.relative == "file1.txt"]
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual(f.size, 5)  # "hello" = 5 bytes
        self.assertIsNotNone(f.mtime)


if __name__ == "__main__":
    unittest.main()
