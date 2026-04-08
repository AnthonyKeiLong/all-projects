#!/usr/bin/env python3
"""FolderSync – entry point.

Usage:
    python -m WebFileSync          # Launch GUI (default)
    python -m WebFileSync --cli    # Headless dry-run scan (prints preview)

See README.md for full documentation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .utils import setup_logging


def _cli_scan(cfg: Config) -> None:
    """Run a headless scan + comparison and print the preview table."""
    from .comparator import compare_folders
    from .scanner import scan_folder
    from .reporter import build_report_data, save_csv_report, save_json_report

    setup_logging(cfg.verbose, cfg.debug, cfg.log_to_file, cfg.log_file)

    source_root = Path(cfg.source_folder)
    target_root = Path(cfg.target_folder)

    print(f"Scanning source: {source_root}")
    source_scan = scan_folder(
        source_root,
        extensions=cfg.file_extensions,
        regex_patterns=cfg.regex_patterns,
        recursive=cfg.recursive,
        include_hidden=cfg.include_hidden,
    )
    print(f"Found {len(source_scan.files)} source file(s), {len(source_scan.errors)} error(s).")

    print(f"Scanning target: {target_root}")
    target_scan = scan_folder(
        target_root,
        extensions=cfg.file_extensions,
        regex_patterns=cfg.regex_patterns,
        recursive=cfg.recursive,
        include_hidden=cfg.include_hidden,
    )
    print(f"Found {len(target_scan.files)} target file(s), {len(target_scan.errors)} error(s).")

    entries = compare_folders(
        source_files=source_scan.files,
        target_files=target_scan.files,
        source_root=source_root,
        target_root=target_root,
        tolerance_seconds=cfg.timestamp_tolerance_seconds,
    )

    # Print preview
    print(f"\n{'Relative Path':<50} {'Reason':<25} {'Action':<20}")
    print("-" * 95)
    for e in entries:
        print(f"{e.relative_path:<50} {e.diff_reason.value:<25} {e.action.value:<20}")

    # Save report
    report_data = build_report_data(entries)
    report_dir = target_root / ".foldersync_reports"
    jp = save_json_report(report_data, report_dir)
    cp = save_csv_report(report_data, report_dir)
    print(f"\nReports saved:\n  JSON: {jp}\n  CSV:  {cp}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="FolderSync",
        description="Compare and sync files between two local folders.",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in headless CLI mode (scan + preview only).",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config JSON file.",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config) if args.config else None
    cfg = Config.load(cfg_path)

    if args.cli:
        if not cfg.source_folder or not cfg.target_folder:
            print("ERROR: source_folder and target_folder must be set in the config file.", file=sys.stderr)
            sys.exit(1)
        _cli_scan(cfg)
    else:
        from .gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
