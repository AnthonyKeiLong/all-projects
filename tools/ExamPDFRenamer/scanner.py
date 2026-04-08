"""Folder scanning orchestrator – ties OCR, extraction, and renaming together."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from config import load_config
from db import FileDB, compute_sha256
from extractor import extract_fields, load_subject_mapping
from ocr_engine import extract_text
from renamer import build_filename, build_multi_filenames

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Container for one scanned PDF's results."""

    original_path: str = ""
    sha256: str = ""
    text_method: str = ""
    raw_text: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    suggested_name: str = ""
    multi_names: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def scan_folder(
    folder: str,
    config: dict[str, Any],
    db: FileDB,
    force_rescan: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
) -> list[ScanResult]:
    """Recursively scan *folder* for PDFs, extract info from each.

    Parameters
    ----------
    progress_callback : callable(current, total, filename)
        Called after each file is processed.
    cancel_flag : callable() -> bool
        When it returns True the scan stops early.
    """
    pdf_files = sorted(Path(folder).rglob("*.pdf"))
    total = len(pdf_files)
    results: list[ScanResult] = []

    subj_map = load_subject_mapping(config.get("subject_mapping_path", ""))
    publishers: list[str] = config.get("custom_publishers", [])
    template: str = config.get(
        "filename_template",
        "[{year}][{publisher}][{subject}]Mock Exam Papers[{part}].pdf",
    )
    max_len: int = config.get("max_filename_length", 120)

    for i, pdf in enumerate(pdf_files):
        if cancel_flag and cancel_flag():
            break
        if progress_callback:
            progress_callback(i + 1, total, pdf.name)

        r = ScanResult(original_path=str(pdf))

        # Hash
        try:
            r.sha256 = compute_sha256(pdf)
        except Exception as e:
            logger.error("Hash error %s: %s", pdf, e)
            r.skipped, r.skip_reason = True, f"Hash error: {e}"
            results.append(r)
            continue

        # Already processed?
        if not force_rescan and db.is_processed(r.sha256):
            r.skipped, r.skip_reason = True, "Already processed"
            results.append(r)
            continue

        # Text extraction
        try:
            text, method = extract_text(
                pdf,
                lang=config.get("ocr_languages", "eng+chi_tra"),
                dpi=config.get("ocr_dpi", 300),
                poppler_path=config.get("poppler_path") or None,
                tesseract_cmd=config.get("tesseract_path") or None,
                preprocess=config.get("preprocessing"),
                debug_dir=(
                    str(Path(config.get("reports_dir", "reports")) / "debug" / pdf.stem)
                    if config.get("debug_mode")
                    else None
                ),
            )
            r.text_method = method
            r.raw_text = text
        except Exception as e:
            logger.error("Extraction failed for %s: %s", pdf, e)
            text = ""
            r.text_method = "failed"

        # Field extraction
        r.fields = extract_fields(text, publishers, subj_map)

        # Suggested name
        r.suggested_name = build_filename(template, r.fields, pdf.name, max_len)

        # Multi-paper detection
        multi = r.fields.get("multi_papers", [])
        if multi:
            r.multi_names = build_multi_filenames(template, r.fields, multi, pdf.name, max_len)

        results.append(r)

    return results
