"""Unit tests for the extractor module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractor import (
    ExtractionResult,
    extract_fields,
    extract_part,
    extract_publisher,
    extract_subject,
    extract_year,
    detect_multi_paper,
)

# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------


def test_year_range() -> None:
    text = "HKDSE 2022-2023 Mock Examination Paper"
    r = extract_year(text)
    assert r.value == "2022-2023", f"Expected 2022-2023, got {r.value}"
    assert r.confidence >= 0.9


def test_year_single() -> None:
    text = "Practice Paper Published 2024"
    r = extract_year(text)
    assert r.value == "2024"
    assert r.confidence >= 0.5


def test_year_slash() -> None:
    text = "Academic Year 2023/2024 Final Examination"
    r = extract_year(text)
    assert r.value == "2023-2024"


def test_year_missing() -> None:
    text = "No year information here."
    r = extract_year(text)
    assert r.value == ""
    assert r.confidence == 0.0


# ---------------------------------------------------------------------------
# Publisher extraction
# ---------------------------------------------------------------------------


def test_publisher_keyword() -> None:
    publishers = ["Aristo", "Oxford", "Longman"]
    r = extract_publisher("Published by Aristo Educational Press", publishers)
    assert r.value == "Aristo"
    assert r.confidence >= 0.9


def test_publisher_chinese() -> None:
    publishers = ["牛津", "培生"]
    r = extract_publisher("牛津大學出版社 模擬試題", publishers)
    assert r.value == "牛津"


def test_publisher_heuristic() -> None:
    r = extract_publisher("Published by Acme Learning Ltd.", [])
    assert "Acme" in r.value
    assert r.confidence >= 0.5


def test_publisher_unknown() -> None:
    r = extract_publisher("Nothing helpful here", [])
    assert r.value == "Unknown"


# ---------------------------------------------------------------------------
# Subject extraction
# ---------------------------------------------------------------------------


def test_subject_mapping() -> None:
    mapping = {"algebra": "Mathematics", "calculus": "Mathematics"}
    r = extract_subject("Chapter 5: Algebra Review", mapping)
    assert r.value == "Mathematics"


def test_subject_builtin() -> None:
    r = extract_subject("Physics Paper 1 Section A", {})
    assert r.value == "Physics"


def test_subject_chinese() -> None:
    r = extract_subject("化學科模擬試題", {})
    assert r.value == "Chemistry"


# ---------------------------------------------------------------------------
# Part extraction
# ---------------------------------------------------------------------------


def test_part_paper() -> None:
    r = extract_part("HKDSE Chemistry Paper 2")
    assert r.value == "Paper 2"
    assert r.confidence >= 0.85


def test_part_section() -> None:
    r = extract_part("Section A: Multiple Choice Questions")
    assert r.value == "Section A"


def test_part_chinese() -> None:
    r = extract_part("卷一 閱讀能力")
    assert "卷" in r.value


# ---------------------------------------------------------------------------
# Multi-paper detection
# ---------------------------------------------------------------------------


def test_multi_paper() -> None:
    text = "Paper 1 Listening\n...\nPaper 2 Reading\n...\nPaper 3 Writing"
    multi = detect_multi_paper(text)
    assert len(multi) == 3


def test_single_paper() -> None:
    text = "Paper 1 Section A"
    multi = detect_multi_paper(text)
    assert len(multi) == 0


# ---------------------------------------------------------------------------
# Aggregate extraction
# ---------------------------------------------------------------------------


def test_extract_fields_full() -> None:
    text = (
        "Aristo Educational 2022-2023 HKDSE\n"
        "Mathematics Mock Examination\n"
        "Paper 1 Section A\n"
        "ISBN: 978-962-123-456-7"
    )
    result = extract_fields(text, ["Aristo"], {"mathematics": "Mathematics"})
    assert result["year"]["value"] == "2022-2023"
    assert result["publisher"]["value"] == "Aristo"
    assert result["subject"]["value"] == "Mathematics"
    assert result["part"]["value"] == "Paper 1"
    assert "isbn" in result
    assert result["overall_confidence"] > 0.5


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
