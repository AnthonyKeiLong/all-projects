"""Unit tests for the renamer module."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from renamer import build_filename, build_multi_filenames
from utils import clean_filename, resolve_collision


# ---------------------------------------------------------------------------
# clean_filename
# ---------------------------------------------------------------------------


def test_clean_unsafe_chars() -> None:
    assert "<" not in clean_filename('test<file>:"name".pdf')


def test_clean_empty_brackets() -> None:
    result = clean_filename("[2023][Aristo][]Mock.pdf")
    assert "[]" not in result


def test_clean_truncation() -> None:
    long_name = "A" * 200 + ".pdf"
    result = clean_filename(long_name, max_length=50)
    assert len(result) <= 50


def test_clean_whitespace() -> None:
    assert "  " not in clean_filename("too   many   spaces.pdf")


# ---------------------------------------------------------------------------
# resolve_collision
# ---------------------------------------------------------------------------


def test_resolve_collision_no_conflict() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.pdf"
        assert resolve_collision(p) == p


def test_resolve_collision_with_conflict() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.pdf"
        p.touch()
        result = resolve_collision(p)
        assert result.name == "test (1).pdf"


def test_resolve_collision_multiple() -> None:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "test.pdf"
        base.touch()
        (Path(d) / "test (1).pdf").touch()
        result = resolve_collision(base)
        assert result.name == "test (2).pdf"


# ---------------------------------------------------------------------------
# build_filename
# ---------------------------------------------------------------------------


def test_build_filename_full() -> None:
    fields = {
        "year": {"value": "2022-2023"},
        "publisher": {"value": "Aristo"},
        "subject": {"value": "Mathematics"},
        "part": {"value": "Paper 1"},
    }
    template = "[{year}][{publisher}][{subject}]Mock Exam Papers[{part}].pdf"
    result = build_filename(template, fields)
    assert "2022-2023" in result
    assert "Aristo" in result
    assert "Mathematics" in result
    assert "Paper 1" in result
    assert result.endswith(".pdf")


def test_build_filename_missing_part() -> None:
    fields = {
        "year": {"value": "2023"},
        "publisher": {"value": "Oxford"},
        "subject": {"value": "English"},
        "part": {"value": ""},
    }
    template = "[{year}][{publisher}][{subject}]Mock Exam Papers[{part}].pdf"
    result = build_filename(template, fields)
    assert "[]" not in result


def test_build_filename_orig_token() -> None:
    fields = {
        "year": {"value": ""},
        "publisher": {"value": ""},
        "subject": {"value": ""},
        "part": {"value": ""},
    }
    template = "{orig}_renamed.pdf"
    result = build_filename(template, fields, original_name="original_file.pdf")
    assert "original_file" in result


# ---------------------------------------------------------------------------
# build_multi_filenames
# ---------------------------------------------------------------------------


def test_multi_filenames() -> None:
    fields = {
        "year": {"value": "2023"},
        "publisher": {"value": "Aristo"},
        "subject": {"value": "English"},
        "part": {"value": "Paper 1"},
    }
    multi = [{"part": "Paper 1"}, {"part": "Paper 2"}, {"part": "Paper 3"}]
    template = "[{year}][{publisher}][{subject}]Mock[{part}].pdf"
    names = build_multi_filenames(template, fields, multi)
    assert len(names) == 3
    assert "Paper 1" in names[0]
    assert "Paper 2" in names[1]
    assert "Paper 3" in names[2]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
    raise SystemExit(failed)
