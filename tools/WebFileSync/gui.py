"""FreeSimpleGUI desktop interface for FolderSync."""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import FreeSimpleGUI as sg

from .backup import BackupManager
from .comparator import (
    ComparisonEntry,
    DiffReason,
    SuggestedAction,
    compare_folders,
)
from .config import Config
from .scanner import ScanResult, scan_folder
from .syncer import SyncResult, sync_selected
from .reporter import build_report_data, save_csv_report, save_json_report
from .utils import fmt_dt, fmt_size, setup_logging

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
sg.theme("DarkBlue3")

FONT = ("Segoe UI", 10)
MONO = ("Consolas", 9)

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def _settings_column() -> list:
    return [
        [sg.Text("Source Folder (reference):", font=FONT),
         sg.Input(key="-SOURCE-", size=(55, 1), font=FONT),
         sg.FolderBrowse("Browse", key="-SRC-BROWSE-", font=FONT)],
        [sg.Text("Target Folder (to update):", font=FONT),
         sg.Input(key="-TARGET-", size=(55, 1), font=FONT),
         sg.FolderBrowse("Browse", key="-TGT-BROWSE-", font=FONT)],
        [sg.Text("File Extensions (comma-sep, empty=all):", font=FONT),
         sg.Input(key="-EXT-", size=(30, 1), font=FONT, default_text=""),
         sg.Text("Regex Filters:", font=FONT),
         sg.Input(key="-REGEX-", size=(25, 1), font=FONT)],
        [sg.Text("Timestamp Tolerance (sec):", font=FONT),
         sg.Spin(list(range(0, 3601, 10)), initial_value=120, key="-TOL-", size=(6, 1), font=FONT),
         sg.Text("Concurrency:", font=FONT),
         sg.Spin(list(range(1, 33)), initial_value=4, key="-CONC-", size=(4, 1), font=FONT)],
        [sg.Checkbox("Recursive", default=True, key="-RECURSIVE-", font=FONT),
         sg.Checkbox("Include Hidden", default=False, key="-HIDDEN-", font=FONT),
         sg.Checkbox("Dry Run", default=False, key="-DRY-", font=FONT),
         sg.Checkbox("Preserve Timestamps", default=True, key="-PRESTS-", font=FONT),
         sg.Checkbox("Verbose Logging", default=False, key="-VERBOSE-", font=FONT),
         sg.Checkbox("Log to File", default=False, key="-LOGFILE-", font=FONT)],
    ]


def _table_headings() -> list[str]:
    return ["Relative Path", "Source Date", "Target Date", "Source Size", "Target Size", "Reason", "Action"]


def _action_bar() -> list:
    return [
        [sg.Button("Scan & Compare", key="-SCAN-", font=FONT, button_color=("white", "#2b6cb0")),
         sg.Button("Select All", key="-SEL-ALL-", font=FONT, disabled=True),
         sg.Button("Deselect All", key="-DESEL-ALL-", font=FONT, disabled=True),
         sg.Button("Sync Selected", key="-SYNC-", font=FONT, disabled=True,
                    button_color=("white", "#38a169")),
         sg.Button("Save Report", key="-SAVE-REPORT-", font=FONT, disabled=True),
         sg.Button("Undo Last", key="-UNDO-", font=FONT),
         sg.Button("Backups", key="-BACKUPS-", font=FONT),
         sg.Button("Settings", key="-SETTINGS-", font=FONT),
         sg.Button("Cancel", key="-CANCEL-", font=FONT, disabled=True,
                    button_color=("white", "#e53e3e")),
         sg.Button("Exit", key="-EXIT-", font=FONT)]
    ]


def _build_layout() -> list:
    return [
        [sg.Frame("Folders & Filters", _settings_column(), font=FONT, expand_x=True)],
        *_action_bar(),
        [sg.Table(
            values=[],
            headings=_table_headings(),
            key="-TABLE-",
            font=MONO,
            auto_size_columns=False,
            col_widths=[35, 20, 20, 12, 12, 22, 18],
            num_rows=15,
            justification="left",
            enable_events=True,
            enable_click_events=True,
            select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
            expand_x=True,
            expand_y=True,
        )],
        [sg.ProgressBar(100, orientation="h", key="-PROG-", size=(60, 20), expand_x=True)],
        [sg.Text("Ready", key="-STATUS-", font=FONT, size=(80, 1)),
         sg.Text("", key="-STATS-", font=FONT, justification="right", expand_x=True)],
        [sg.Multiline(
            "", key="-LOG-", font=MONO, size=(100, 8),
            autoscroll=True, disabled=True, expand_x=True, expand_y=True,
        )],
    ]


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------


class AppState:
    """Mutable application state shared between GUI and worker threads."""

    def __init__(self) -> None:
        self.config = Config()
        self.source_scan: Optional[ScanResult] = None
        self.target_scan: Optional[ScanResult] = None
        self.comparison: list[ComparisonEntry] = []
        self.sync_results: list[SyncResult] = []
        self.cancel_event = threading.Event()
        self.last_report_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Main GUI loop
# ---------------------------------------------------------------------------


def run_gui() -> None:  # noqa: C901
    """Launch the FolderSync GUI."""
    window = sg.Window(
        "FolderSync – Local Folder Comparison & Sync",
        _build_layout(),
        resizable=True,
        finalize=True,
        font=FONT,
    )

    state = AppState()

    def _log(msg: str) -> None:
        window["-LOG-"].print(msg)

    def _status(msg: str) -> None:
        window["-STATUS-"].update(msg)

    def _update_stats() -> None:
        total = len(state.comparison)
        sel = sum(1 for e in state.comparison if e.selected)
        window["-STATS-"].update(f"Total: {total}  |  Selected: {sel}")

    def _populate_table() -> None:
        rows = []
        for e in state.comparison:
            mark = "\u2713 " if e.selected else "  "
            rows.append([
                mark + e.relative_path,
                fmt_dt(e.source_timestamp),
                fmt_dt(e.target_timestamp),
                fmt_size(e.source_size),
                fmt_size(e.target_size),
                e.diff_reason.value,
                e.action.value,
            ])
        window["-TABLE-"].update(values=rows)
        _update_stats()

    def _read_config_from_gui(values: dict) -> Config:
        exts_raw = values.get("-EXT-", "")
        exts = [x.strip() for x in exts_raw.split(",") if x.strip()] if exts_raw else []
        regex_raw = values.get("-REGEX-", "")
        regexes = [x.strip() for x in regex_raw.split(",") if x.strip()] if regex_raw else []

        return Config(
            source_folder=values.get("-SOURCE-", "").strip(),
            target_folder=values.get("-TARGET-", "").strip(),
            file_extensions=exts,
            regex_patterns=regexes,
            timestamp_tolerance_seconds=int(values.get("-TOL-", 120)),
            max_concurrency=int(values.get("-CONC-", 4)),
            dry_run=values.get("-DRY-", False),
            preserve_timestamps=values.get("-PRESTS-", True),
            recursive=values.get("-RECURSIVE-", True),
            include_hidden=values.get("-HIDDEN-", False),
            verbose=values.get("-VERBOSE-", False),
            log_to_file=values.get("-LOGFILE-", False),
        )

    def _apply_config_to_gui(cfg: Config) -> None:
        window["-SOURCE-"].update(cfg.source_folder)
        window["-TARGET-"].update(cfg.target_folder)
        window["-EXT-"].update(", ".join(cfg.file_extensions))
        window["-REGEX-"].update(", ".join(cfg.regex_patterns))
        window["-TOL-"].update(cfg.timestamp_tolerance_seconds)
        window["-CONC-"].update(cfg.max_concurrency)
        window["-DRY-"].update(cfg.dry_run)
        window["-PRESTS-"].update(cfg.preserve_timestamps)
        window["-RECURSIVE-"].update(cfg.recursive)
        window["-HIDDEN-"].update(cfg.include_hidden)
        window["-VERBOSE-"].update(cfg.verbose)
        window["-LOGFILE-"].update(cfg.log_to_file)

    # Load persisted config if available
    try:
        saved = Config.load()
        state.config = saved
        _apply_config_to_gui(saved)
    except Exception:
        pass

    # Thread helper ---------------------------------------------------------

    def _run_in_thread(target, *args, after_event: str = "-THREAD-DONE-", **kwargs):
        state.cancel_event.clear()
        window["-CANCEL-"].update(disabled=False)

        def wrapper():
            try:
                target(*args, **kwargs)
            except Exception as exc:
                window.write_event_value("-THREAD-ERROR-", str(exc))
            finally:
                window.write_event_value(after_event, "")

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()

    # Worker functions ------------------------------------------------------

    def _worker_scan_and_compare(cfg: Config) -> None:
        setup_logging(cfg.verbose, cfg.debug, cfg.log_to_file, cfg.log_file)

        source_root = Path(cfg.source_folder)
        target_root = Path(cfg.target_folder)

        def prog(msg: str) -> None:
            window.write_event_value("-PROG-MSG-", msg)

        prog("Scanning source folder\u2026")
        state.source_scan = scan_folder(
            source_root,
            extensions=cfg.file_extensions,
            regex_patterns=cfg.regex_patterns,
            recursive=cfg.recursive,
            include_hidden=cfg.include_hidden,
            cancel_event=state.cancel_event,
            progress_callback=prog,
        )

        if state.cancel_event.is_set():
            return

        prog("Scanning target folder\u2026")
        state.target_scan = scan_folder(
            target_root,
            extensions=cfg.file_extensions,
            regex_patterns=cfg.regex_patterns,
            recursive=cfg.recursive,
            include_hidden=cfg.include_hidden,
            cancel_event=state.cancel_event,
            progress_callback=prog,
        )

        if state.cancel_event.is_set():
            return

        prog("Comparing files\u2026")
        state.comparison = compare_folders(
            source_files=state.source_scan.files,
            target_files=state.target_scan.files,
            source_root=source_root,
            target_root=target_root,
            tolerance_seconds=cfg.timestamp_tolerance_seconds,
            cancel_event=state.cancel_event,
            progress_callback=prog,
        )

    def _worker_sync(cfg: Config) -> None:
        if not state.comparison:
            return
        target_root = Path(cfg.target_folder)
        backup_mgr = BackupManager(target_root, cfg.backup_dir_name)

        def prog(msg: str) -> None:
            window.write_event_value("-PROG-MSG-", msg)

        results = sync_selected(
            entries=state.comparison,
            backup_mgr=backup_mgr,
            max_concurrency=cfg.max_concurrency,
            preserve_timestamps=cfg.preserve_timestamps,
            preserve_permissions=cfg.preserve_permissions,
            cancel_event=state.cancel_event,
            progress_callback=prog,
        )
        state.sync_results = results
        backup_mgr.save_manifest()

    # Event loop ------------------------------------------------------------

    while True:
        event, values = window.read(timeout=100)

        if event in (sg.WIN_CLOSED, "-EXIT-"):
            break

        # ---- Scan & Compare ----
        if event == "-SCAN-":
            cfg = _read_config_from_gui(values)
            if not cfg.source_folder or not cfg.target_folder:
                sg.popup("Please provide both Source and Target folders.", title="Missing Input", font=FONT)
                continue
            state.config = cfg
            cfg.save()
            _status("Scanning folders\u2026")
            _log("Starting scan & compare\u2026")
            window["-SCAN-"].update(disabled=True)
            _run_in_thread(_worker_scan_and_compare, cfg, after_event="-SCAN-DONE-")

        elif event == "-SCAN-DONE-":
            window["-SCAN-"].update(disabled=False)
            window["-CANCEL-"].update(disabled=True)
            _populate_table()

            src_n = len(state.source_scan.files) if state.source_scan else 0
            tgt_n = len(state.target_scan.files) if state.target_scan else 0
            sel = sum(1 for e in state.comparison if e.selected)
            total = len(state.comparison)

            # Log scan errors
            for scan in (state.source_scan, state.target_scan):
                if scan:
                    for err in scan.errors:
                        _log(f"  ERROR: {err}")

            _log(f"Source: {src_n} file(s), Target: {tgt_n} file(s), Differences: {sel}/{total}")
            _status(f"Comparison done \u2014 {sel} file(s) selected for sync.")
            window["-SYNC-"].update(disabled=False)
            window["-SEL-ALL-"].update(disabled=False)
            window["-DESEL-ALL-"].update(disabled=False)
            window["-SAVE-REPORT-"].update(disabled=False)

        # ---- Table click (toggle selection) ----
        elif event == "-TABLE-":
            selected_rows = values.get("-TABLE-", [])
            for idx in selected_rows:
                if 0 <= idx < len(state.comparison):
                    state.comparison[idx].selected = not state.comparison[idx].selected
            _populate_table()
            window["-TABLE-"].update(select_rows=selected_rows)

        # ---- Select / Deselect All ----
        elif event == "-SEL-ALL-":
            for e in state.comparison:
                if e.action != SuggestedAction.SKIP:
                    e.selected = True
            _populate_table()

        elif event == "-DESEL-ALL-":
            for e in state.comparison:
                e.selected = False
            _populate_table()

        # ---- Sync ----
        elif event == "-SYNC-":
            cfg = _read_config_from_gui(values)
            state.config = cfg
            sel_count = sum(1 for e in state.comparison if e.selected)
            if sel_count == 0:
                sg.popup("No files selected.", title="Sync", font=FONT)
                continue

            if cfg.dry_run:
                sg.popup(f"Dry-run mode: {sel_count} file(s) would be copied.",
                         title="Dry Run", font=FONT)
                continue

            confirm = sg.popup_yes_no(
                f"Copy {sel_count} file(s) from source to target?\n\n"
                "Existing target files will be backed up before replacement.",
                title="Confirm Sync", font=FONT,
            )
            if confirm != "Yes":
                continue

            _status("Syncing\u2026")
            _log(f"Syncing {sel_count} file(s)\u2026")
            window["-SYNC-"].update(disabled=True)
            _run_in_thread(_worker_sync, cfg, after_event="-SYNC-DONE-")

        elif event == "-SYNC-DONE-":
            window["-SYNC-"].update(disabled=False)
            window["-CANCEL-"].update(disabled=True)
            ok = sum(1 for sr in state.sync_results if sr.success)
            fail = sum(1 for sr in state.sync_results if not sr.success)
            _log(f"Sync complete. Success: {ok}, Failed: {fail}")
            for sr in state.sync_results:
                if not sr.success:
                    _log(f"  FAILED: {sr.relative_path} \u2014 {sr.error}")
            _status(f"Sync done \u2014 {ok} succeeded, {fail} failed.")

        # ---- Save Report ----
        elif event == "-SAVE-REPORT-":
            report_data = build_report_data(state.comparison, state.sync_results or None)
            target_root = Path(values.get("-TARGET-", "."))
            report_dir = target_root / ".foldersync_reports"
            jp = save_json_report(report_data, report_dir)
            cp = save_csv_report(report_data, report_dir)
            state.last_report_path = jp
            _log(f"Reports saved:\n  JSON: {jp}\n  CSV:  {cp}")
            sg.popup(f"Reports saved to:\n{report_dir}", title="Report Saved", font=FONT)

        # ---- Undo ----
        elif event == "-UNDO-":
            target_str = values.get("-TARGET-", "").strip()
            if not target_str:
                sg.popup("Set a Target Folder first.", font=FONT)
                continue
            target_root = Path(target_str)
            report_dir = target_root / ".foldersync_reports"
            if not report_dir.exists():
                sg.popup("No reports found to undo from.", font=FONT)
                continue
            reports = sorted(report_dir.glob("report_*.json"), reverse=True)
            if not reports:
                sg.popup("No report files found.", font=FONT)
                continue

            choices = [r.name for r in reports]
            layout_undo = [
                [sg.Text("Select report to undo:", font=FONT)],
                [sg.Listbox(choices, size=(50, 10), key="-UREPORT-", font=MONO)],
                [sg.Button("Undo", font=FONT), sg.Button("Cancel", font=FONT)],
            ]
            w2 = sg.Window("Undo", layout_undo, modal=True, font=FONT)
            while True:
                ev2, val2 = w2.read()
                if ev2 in (sg.WIN_CLOSED, "Cancel"):
                    break
                if ev2 == "Undo":
                    sel = val2.get("-UREPORT-", [])
                    if not sel:
                        continue
                    rp = report_dir / sel[0]
                    confirm = sg.popup_yes_no(
                        f"Restore files from:\n{rp.name}\n\nThis will overwrite current target files with backups.",
                        title="Confirm Undo", font=FONT,
                    )
                    if confirm != "Yes":
                        continue
                    restored, errors = BackupManager.undo_from_report(rp)
                    msg = f"Restored {restored} file(s)."
                    if errors:
                        msg += f"\nErrors: {len(errors)}"
                        for e in errors:
                            msg += f"\n  {e}"
                    sg.popup(msg, title="Undo Result", font=FONT)
                    _log(msg)
                    break
            w2.close()

        # ---- Backups ----
        elif event == "-BACKUPS-":
            target_str = values.get("-TARGET-", "").strip()
            if not target_str:
                sg.popup("Set a Target Folder first.", font=FONT)
                continue
            backup_loc = Path(target_str) / state.config.backup_dir_name
            if backup_loc.exists():
                if sys.platform == "win32":
                    os.startfile(str(backup_loc))  # noqa: S606
                else:
                    webbrowser.open(str(backup_loc))
            else:
                sg.popup(f"No backups yet.\nBackup location:\n{backup_loc}", font=FONT)

        # ---- Settings (load/save config) ----
        elif event == "-SETTINGS-":
            layout_set = [
                [sg.Text("Config file:", font=FONT),
                 sg.Input(str(Path.cwd() / "config.json"), key="-CFG-PATH-", size=(50, 1), font=FONT),
                 sg.FileBrowse(font=FONT)],
                [sg.Button("Load", font=FONT), sg.Button("Save Current", font=FONT),
                 sg.Button("Close", font=FONT)],
            ]
            ws = sg.Window("Settings", layout_set, modal=True, font=FONT)
            while True:
                evs, vals = ws.read()
                if evs in (sg.WIN_CLOSED, "Close"):
                    break
                if evs == "Load":
                    cp = Path(vals["-CFG-PATH-"])
                    cfg = Config.load(cp)
                    state.config = cfg
                    _apply_config_to_gui(cfg)
                    _log(f"Config loaded from {cp}")
                    break
                if evs == "Save Current":
                    cfg = _read_config_from_gui(values)
                    cp = Path(vals["-CFG-PATH-"])
                    cfg.save(cp)
                    _log(f"Config saved to {cp}")
                    sg.popup_quick_message("Config saved!", font=FONT)
            ws.close()

        # ---- Cancel ----
        elif event == "-CANCEL-":
            state.cancel_event.set()
            _status("Cancelling\u2026")
            _log("Cancel requested.")

        # ---- Thread progress messages ----
        elif event == "-PROG-MSG-":
            msg = values.get("-PROG-MSG-", "")
            _status(msg)
            _log(msg)

        elif event == "-THREAD-ERROR-":
            err = values.get("-THREAD-ERROR-", "Unknown error")
            _status(f"Error: {err}")
            _log(f"ERROR: {err}")
            sg.popup_error(f"An error occurred:\n{err}", title="Error", font=FONT)
            window["-SCAN-"].update(disabled=False)
            window["-SYNC-"].update(disabled=False)
            window["-CANCEL-"].update(disabled=True)

    window.close()
