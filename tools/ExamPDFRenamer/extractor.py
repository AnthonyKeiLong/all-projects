"""Extract structured fields (year, publisher, subject, part, …) from PDF text."""

import csv
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

class ExtractionResult:
    """Single extracted field with a confidence score and evidence snippet."""

    __slots__ = ("value", "confidence", "snippet")

    def __init__(self, value: str = "", confidence: float = 0.0, snippet: str = "") -> None:
        self.value = value
        self.confidence = confidence
        self.snippet = snippet

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": self.confidence, "snippet": self.snippet}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(text: str, start: int, end: int, margin: int = 30) -> str:
    """Return a snippet of *text* around [start, end) with *margin* chars."""
    return text[max(0, start - margin) : end + margin].strip()


def load_subject_mapping(path: str | Path) -> dict[str, str]:
    """Load keyword → subject mapping from a CSV with columns *keyword*, *subject*."""
    mapping: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return mapping
    try:
        with open(p, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                kw = row.get("keyword", "").strip().lower()
                subj = row.get("subject", "").strip()
                if kw and subj:
                    mapping[kw] = subj
    except Exception as e:
        logger.warning("Failed to load subject mapping from %s: %s", p, e)
    return mapping


# ---------------------------------------------------------------------------
# Individual field extractors
# ---------------------------------------------------------------------------

def extract_year(text: str) -> ExtractionResult:
    """Extract an academic-year or single year from *text*."""
    patterns: list[tuple[str, float]] = [
        (r"(20\d{2})\s*[-–/]\s*(20\d{2})", 0.95),
        (r"(19\d{2})\s*[-–/]\s*(20\d{2})", 0.90),
        (r"(19\d{2})\s*[-–/]\s*(19\d{2})", 0.90),
        (r"\b(20[1-3]\d)\b", 0.70),
        (r"\b(19[89]\d)\b", 0.60),
    ]
    for pat, conf in patterns:
        m = re.search(pat, text)
        if m:
            snip = _ctx(text, m.start(), m.end())
            val = f"{m.group(1)}-{m.group(2)}" if m.lastindex and m.lastindex >= 2 else m.group(1)
            return ExtractionResult(val, conf, snip)
    return ExtractionResult()


def extract_publisher(text: str, publishers: list[str]) -> ExtractionResult:
    """Match publisher by keyword list then layout heuristics."""
    low = text.lower()
    # Pass 1 – exact keyword
    for pub in publishers:
        idx = low.find(pub.lower())
        if idx != -1:
            return ExtractionResult(pub, 0.95, _ctx(text, idx, idx + len(pub)))
    # Pass 2 – heuristic patterns
    heuristics: list[tuple[str, float]] = [
        (r"(?:published\s+by|publisher[:\s]+)([A-Za-z\s&]+)", 0.75),
        (r"([\u4e00-\u9fff]+)出版", 0.75),
        (r"©\s*\d{4}\s+([A-Za-z\s&]+)", 0.60),
    ]
    for pat, conf in heuristics:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return ExtractionResult(m.group(1).strip(), conf, _ctx(text, m.start(), m.end()))
    return ExtractionResult("Unknown", 0.2, "")


_SUBJECT_KW: dict[str, str] = {
    "mathematics": "Mathematics", "math": "Mathematics", "maths": "Mathematics",
    "數學": "Mathematics",
    "english": "English", "英文": "English", "英語": "English",
    "chinese": "Chinese", "中文": "Chinese", "中國語文": "Chinese",
    "physics": "Physics", "物理": "Physics",
    "chemistry": "Chemistry", "化學": "Chemistry",
    "biology": "Biology", "生物": "Biology",
    "economics": "Economics", "經濟": "Economics",
    "geography": "Geography", "地理": "Geography",
    "history": "History", "歷史": "History",
    "liberal studies": "Liberal Studies", "通識": "Liberal Studies",
    "ict": "ICT", "資訊及通訊科技": "ICT",
    "bafs": "BAFS", "企業、會計與財務概論": "BAFS",
    "science": "Science", "科學": "Science",
    "general studies": "General Studies", "常識": "General Studies",
}


def extract_subject(text: str, subject_mapping: dict[str, str]) -> ExtractionResult:
    """Extract subject using mapping file first, then built-in keywords."""
    low = text.lower()
    # User mapping has priority
    for kw, subj in subject_mapping.items():
        idx = low.find(kw)
        if idx != -1:
            return ExtractionResult(subj, 0.90, _ctx(text, idx, idx + len(kw)))
    # Built-in keywords
    for kw, subj in _SUBJECT_KW.items():
        idx = low.find(kw)
        if idx != -1:
            return ExtractionResult(subj, 0.80, _ctx(text, idx, idx + len(kw)))
    return ExtractionResult("Unknown", 0.1, "")


def extract_part(text: str) -> ExtractionResult:
    """Extract paper/section/part designator."""
    patterns: list[tuple[str, float]] = [
        (r"(Paper\s+[1-9A-Z])", 0.90),
        (r"(卷\s*[一二三四五六\d])", 0.90),
        (r"(Section\s+[A-Z])", 0.85),
        (r"(Part\s+[A-Z1-9])", 0.85),
        (r"(Module\s+[A-Z1-9])", 0.80),
        (r"(Reading|Writing|Listening|Speaking)", 0.75),
        (r"(閱讀|寫作|聆聽|說話)", 0.75),
        (r"(Question\s+\d+)", 0.70),
    ]
    for pat, conf in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return ExtractionResult(m.group(1).strip(), conf, _ctx(text, m.start(), m.end()))
    return ExtractionResult()


def extract_mock_number(text: str) -> ExtractionResult:
    """Extract mock exam number (e.g. Mock Exam 1, 模擬試卷二)."""
    patterns: list[tuple[str, float]] = [
        (r"Mock\s*(?:Exam(?:ination)?|Test|Paper)\s*#?\s*(\d+)", 0.90),
        (r"模擬試卷\s*([一二三四五六七八九十\d]+)", 0.90),
        (r"模擬考試\s*([一二三四五六七八九十\d]+)", 0.90),
        (r"Mock\s+(\d+)", 0.80),
        (r"(?:Exam|Test)\s*#?\s*(\d+)", 0.70),
    ]
    cn_num_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                  "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
    for pat, conf in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            val = cn_num_map.get(val, val)
            return ExtractionResult(val, conf, _ctx(text, m.start(), m.end()))
    return ExtractionResult()


def extract_paper_number(text: str) -> ExtractionResult:
    """Extract Paper 1 / Paper 2 style designators.

    This is distinct from the generic *part* extractor – it specifically
    looks for the paper number (1, 2, …) and normalises the value to
    ``Paper 1``, ``Paper 2``, etc.
    """
    patterns: list[tuple[str, float]] = [
        (r"Paper\s*(\d)", 0.95),
        (r"卷\s*([一二三\d])", 0.95),
        (r"PAPER\s*(\d)", 0.95),
        (r"P\.?\s*(\d)\b", 0.75),
    ]
    cn_num_map = {"一": "1", "二": "2", "三": "3"}
    for pat, conf in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = cn_num_map.get(m.group(1), m.group(1))
            return ExtractionResult(f"Paper {val}", conf, _ctx(text, m.start(), m.end()))
    return ExtractionResult()


def extract_optional_fields(text: str) -> dict[str, ExtractionResult]:
    """Extract ISBN, DOI, and similar metadata when present."""
    out: dict[str, ExtractionResult] = {}
    isbn = re.search(r"ISBN[:\s-]*([\d-]{10,17})", text, re.IGNORECASE)
    if isbn:
        out["isbn"] = ExtractionResult(isbn.group(1), 0.90, _ctx(text, isbn.start(), isbn.end()))
    doi = re.search(r"(10\.\d{4,}/[^\s]+)", text)
    if doi:
        out["doi"] = ExtractionResult(doi.group(1), 0.90, _ctx(text, doi.start(), doi.end()))
    return out


def detect_multi_paper(text: str) -> list[dict[str, str]]:
    """Detect when a PDF contains more than one distinct paper."""
    seen: dict[str, int] = {}
    for m in re.finditer(r"(Paper\s+[1-9A-Z]|卷\s*[一二三四五六\d])", text, re.IGNORECASE):
        key = m.group(1).strip().lower()
        if key not in seen:
            seen[key] = m.start()
    if len(seen) > 1:
        return [{"part": k.title(), "offset": str(v)} for k, v in seen.items()]
    return []


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def extract_fields(
    text: str,
    publishers: list[str],
    subject_mapping: dict[str, str],
) -> dict[str, Any]:
    """Run all extractors and return a unified result dict."""
    year = extract_year(text)
    publisher = extract_publisher(text, publishers)
    subject = extract_subject(text, subject_mapping)
    part = extract_part(text)
    mock_number = extract_mock_number(text)
    paper = extract_paper_number(text)
    optional = extract_optional_fields(text)
    multi = detect_multi_paper(text)

    lang = "chi_tra" if any("\u4e00" <= c <= "\u9fff" for c in text[:500]) else "eng"

    result: dict[str, Any] = {
        "year": year.to_dict(),
        "publisher": publisher.to_dict(),
        "subject": subject.to_dict(),
        "part": part.to_dict(),
        "mock_number": mock_number.to_dict(),
        "paper": paper.to_dict(),
        "language": lang,
        "multi_papers": multi,
    }
    for k, v in optional.items():
        result[k] = v.to_dict()

    confs = [year.confidence, publisher.confidence, subject.confidence]
    if part.confidence > 0:
        confs.append(part.confidence)
    if mock_number.confidence > 0:
        confs.append(mock_number.confidence)
    if paper.confidence > 0:
        confs.append(paper.confidence)
    result["overall_confidence"] = round(sum(confs) / len(confs), 3) if confs else 0.0
    return result
