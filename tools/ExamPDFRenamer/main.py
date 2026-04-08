#!/usr/bin/env python3
"""ExamPDFRenamer – entry point.

Launch the GUI or run a headless scan from the command line.

Usage
-----
    python main.py              # launch GUI
    python main.py --headless --folder <path>  # headless dry-run scan
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure the package directory is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from db import FileDB
from scanner import scan_folder
from report import generate_report


def _setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def headless(folder: str, force: bool = False) -> None:
    """Run a headless scan and print extracted info."""
    import time

    cfg = load_config()
    _setup_logging(cfg.get("debug_mode", False))
    db = FileDB(cfg["db_path"])

    start_time = time.time()

    def _progress(current: int, total: int, filename: str) -> None:
        pct = current / total * 100 if total else 0
        elapsed = time.time() - start_time
        avg = elapsed / current if current else 0
        remaining = avg * (total - current)
        mins, secs = divmod(int(remaining), 60)
        eta = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
        print(f"  [{current}/{total}] {pct:5.1f}%  ETA {eta}  {filename}", flush=True)

    print(f"Scanning: {folder}")
    results = scan_folder(folder, cfg, db, force_rescan=force,
                          progress_callback=_progress)

    for r in results:
        if r.skipped:
            print(f"  SKIP  {Path(r.original_path).name} – {r.skip_reason}")
            continue
        f = r.fields
        print(
            f"  {Path(r.original_path).name}\n"
            f"    Year:      {f.get('year', {}).get('value', '?')} "
            f"(conf {f.get('year', {}).get('confidence', 0):.2f})\n"
            f"    Publisher: {f.get('publisher', {}).get('value', '?')} "
            f"(conf {f.get('publisher', {}).get('confidence', 0):.2f})\n"
            f"    Subject:   {f.get('subject', {}).get('value', '?')} "
            f"(conf {f.get('subject', {}).get('confidence', 0):.2f})\n"
            f"    Part:      {f.get('part', {}).get('value', '?')} "
            f"(conf {f.get('part', {}).get('confidence', 0):.2f})\n"
            f"    Mock #:   {f.get('mock_number', {}).get('value', '?')} "
            f"(conf {f.get('mock_number', {}).get('confidence', 0):.2f})\n"
            f"    Paper:    {f.get('paper', {}).get('value', '?')} "
            f"(conf {f.get('paper', {}).get('confidence', 0):.2f})\n"
            f"    ➜ {r.suggested_name}"
        )

    report_path = generate_report(results, [], cfg["reports_dir"])
    print(f"\nReport: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ExamPDFRenamer")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--folder", type=str, help="Folder to scan (headless mode)")
    parser.add_argument("--force", action="store_true", help="Force re-scan already-processed files")
    args = parser.parse_args()

    if args.headless:
        if not args.folder:
            parser.error("--headless requires --folder")
        headless(args.folder, args.force)
    else:
        _setup_logging()
        from gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
