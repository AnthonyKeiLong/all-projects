"""Dry-run integration test.

Demonstrates scanning a ``tests/sample_pdfs/`` folder without OCR
dependencies by relying on PyMuPDF native text extraction.  If no
sample PDFs exist, the test creates a tiny one using PyMuPDF.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config
from db import FileDB
from scanner import scan_folder
from report import generate_report


def _ensure_sample_pdf(folder: Path) -> Path:
    """Create a minimal PDF with embedded text for testing."""
    pdf_path = folder / "sample_aristo_math_2023.pdf"
    if pdf_path.exists():
        return pdf_path
    try:
        import fitz  # type: ignore[import-untyped]  # PyMuPDF

        doc = fitz.open()
        page = doc.new_page()
        text = (
            "Aristo Educational Press\n"
            "2022-2023 HKDSE Mock Examination\n"
            "Mathematics Compulsory Part\n"
            "Paper 1\n"
            "Section A(1)\n"
            "Time allowed: 2 hours 15 minutes\n"
            "ISBN: 978-962-123-456-7\n"
        )
        page.insert_text((72, 72), text, fontsize=12)
        doc.save(str(pdf_path))
        doc.close()
        print(f"Created sample PDF: {pdf_path}")
    except ImportError:
        print("PyMuPDF not installed – cannot create sample PDF.")
        print("Install with: pip install PyMuPDF")
        raise SystemExit(1)
    return pdf_path


def main() -> None:
    # Setup
    sample_dir = Path(__file__).resolve().parent / "sample_pdfs"
    sample_dir.mkdir(exist_ok=True)
    _ensure_sample_pdf(sample_dir)

    cfg = load_config()
    cfg["ocr_languages"] = "eng"  # avoid needing chi_tra for tests

    with tempfile.TemporaryDirectory() as tmp:
        cfg["db_path"] = str(Path(tmp) / "test_db.json")
        cfg["reports_dir"] = str(Path(tmp) / "reports")
        db = FileDB(cfg["db_path"])

        print(f"\n{'='*60}")
        print(f"Dry-run scan of: {sample_dir}")
        print(f"{'='*60}\n")

        results = scan_folder(
            str(sample_dir), cfg, db, force_rescan=True,
            progress_callback=lambda c, t, n: print(f"  [{c}/{t}] {n}"),
        )

        for r in results:
            if r.skipped:
                print(f"\n  SKIP  {Path(r.original_path).name} – {r.skip_reason}")
                continue
            f = r.fields
            print(f"\n  File: {Path(r.original_path).name}")
            print(f"    Method:    {r.text_method}")
            print(f"    Year:      {f.get('year', {}).get('value', '?')} (conf {f.get('year', {}).get('confidence', 0):.2f})")
            print(f"    Publisher: {f.get('publisher', {}).get('value', '?')} (conf {f.get('publisher', {}).get('confidence', 0):.2f})")
            print(f"    Subject:   {f.get('subject', {}).get('value', '?')} (conf {f.get('subject', {}).get('confidence', 0):.2f})")
            print(f"    Part:      {f.get('part', {}).get('value', '?')} (conf {f.get('part', {}).get('confidence', 0):.2f})")
            print(f"    Overall:   {f.get('overall_confidence', 0):.2f}")
            print(f"    ➜ {r.suggested_name}")
            if r.multi_names:
                for mn in r.multi_names:
                    print(f"      (multi) ➜ {mn}")

        report_path = generate_report(results, [], cfg["reports_dir"])
        print(f"\nReport saved: {report_path}")

        with open(report_path, "r", encoding="utf-8") as fp:
            report = json.load(fp)
        print(f"Report contains {report['total_files']} file(s).\n")


if __name__ == "__main__":
    main()
