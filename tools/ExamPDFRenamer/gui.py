# pyright: reportOptionalMemberAccess=false
# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
"""PySimpleGUI dark-theme GUI for ExamPDFRenamer.

Uses FreeSimpleGUI (community fork) with fallback to PySimpleGUI 4.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

try:
    import FreeSimpleGUI as sg  # type: ignore[import-untyped]
except ImportError:
    import PySimpleGUI as sg  # type: ignore[no-redef]

from config import load_config, save_config
from db import FileDB
from installer import (
    check_poppler,
    check_tesseract,
    install_language_pack,
    install_poppler,
    install_tesseract_choco,
    install_tesseract_manual,
    install_tesseract_winget,
    _has_choco,
    _has_winget,
)
from renamer import rename_file
from report import export_csv, generate_report, undo_from_report
from scanner import ScanResult, scan_folder

logger = logging.getLogger(__name__)

# ── Theme ────────────────────────────────────────────────────────────────

sg.theme("DarkBlue3")

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)

# ── Layout helpers ───────────────────────────────────────────────────────


def _settings_frame(cfg: dict[str, Any]) -> sg.Frame:
    return sg.Frame(
        "Settings",
        [
            [
                sg.Text("Tesseract path:", size=(15, 1)),
                sg.Input(cfg.get("tesseract_path", ""), key="-TESS-PATH-", size=(45, 1)),
                sg.FileBrowse(file_types=(("Executable", "*.exe"),)),
            ],
            [
                sg.Text("Poppler path:", size=(15, 1)),
                sg.Input(cfg.get("poppler_path", ""), key="-POP-PATH-", size=(45, 1)),
                sg.FolderBrowse(),
            ],
            [
                sg.Text("OCR languages:", size=(15, 1)),
                sg.Input(cfg.get("ocr_languages", "eng+chi_tra"), key="-OCR-LANG-", size=(20, 1)),
                sg.Text("  Template:", size=(9, 1)),
                sg.Input(cfg.get("filename_template", ""), key="-TEMPLATE-", size=(40, 1)),
            ],
            [
                sg.Text("Confidence:", size=(15, 1)),
                sg.Slider(
                    range=(0.0, 1.0),
                    resolution=0.05,
                    default_value=cfg.get("confidence_threshold", 0.9),
                    orientation="h",
                    size=(20, 15),
                    key="-CONF-THRESH-",
                ),
                sg.Checkbox("Preserve timestamps", default=cfg.get("preserve_timestamps", True), key="-PRESERVE-TS-"),
                sg.Checkbox("Debug mode", default=cfg.get("debug_mode", False), key="-DEBUG-"),
            ],
            [
                sg.Text("Preprocessing:", size=(15, 1)),
                sg.Checkbox("Binarize", default=cfg.get("preprocessing", {}).get("binarize", False), key="-PP-BIN-"),
                sg.Checkbox("Deskew", default=cfg.get("preprocessing", {}).get("deskew", False), key="-PP-DESKEW-"),
                sg.Checkbox("Contrast", default=cfg.get("preprocessing", {}).get("contrast", False), key="-PP-CONTRAST-"),
            ],
        ],
        font=FONT_BOLD,
    )


def _build_layout(cfg: dict[str, Any]) -> list:
    return [
        [
            sg.Text("Folder:", font=FONT_BOLD),
            sg.Input("", key="-FOLDER-", size=(55, 1)),
            sg.FolderBrowse(),
            sg.Checkbox("Force re-scan", key="-FORCE-"),
        ],
        [_settings_frame(cfg)],
        [
            sg.Button("Scan", key="-SCAN-", font=FONT_BOLD),
            sg.Button("Preview (dry-run)", key="-PREVIEW-"),
            sg.Button("Bulk Approve ≥ Threshold", key="-BULK-"),
            sg.Button("Rename Selected", key="-RENAME-", button_color=("white", "#28a745")),
            sg.Button("Save Report", key="-REPORT-"),
            sg.Button("Export CSV", key="-CSV-"),
            sg.Button("Undo Last Rename", key="-UNDO-"),
        ],
        [
            sg.Button("Install Tesseract", key="-INST-TESS-", button_color=("white", "#6f42c1")),
            sg.Button("Install Poppler", key="-INST-POP-", button_color=("white", "#6f42c1")),
            sg.Button("Install Language Pack", key="-INST-LANG-", button_color=("white", "#6f42c1")),
            sg.Button("Save Settings", key="-SAVE-CFG-"),
            sg.Button("Exit", key="-EXIT-"),
        ],
        [
            sg.Table(
                values=[],
                headings=[
                    "✓", "Original File", "Year", "Publisher", "Subject",
                    "Part", "Confidence", "Suggested Name",
                ],
                col_widths=[3, 28, 10, 14, 12, 12, 8, 30],
                auto_size_columns=False,
                justification="left",
                num_rows=18,
                key="-TABLE-",
                enable_events=True,
                enable_click_events=True,
                select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
                font=FONT_SMALL,
                right_click_menu=["", ["Edit Suggested Name", "Toggle Selection", "View Snippet"]],
            )
        ],
        [
            sg.ProgressBar(100, orientation="h", size=(60, 18), key="-PROG-"),
            sg.Text("Ready", size=(50, 1), key="-STATUS-", font=FONT_SMALL),
        ],
    ]


# ── Data management ──────────────────────────────────────────────────────

_scan_results: list[ScanResult] = []
_selected: list[bool] = []
_table_data: list[list[str]] = []
_last_report: str = ""


def _results_to_table(results: list[ScanResult]) -> list[list[str]]:
    global _selected
    _selected = [False] * len(results)
    rows: list[list[str]] = []
    for i, r in enumerate(results):
        if r.skipped:
            continue
        f = r.fields
        rows.append(
            [
                "☐",
                Path(r.original_path).name,
                f.get("year", {}).get("value", ""),
                f.get("publisher", {}).get("value", ""),
                f.get("subject", {}).get("value", ""),
                f.get("part", {}).get("value", ""),
                f"{f.get('overall_confidence', 0):.2f}",
                r.suggested_name,
            ]
        )
    return rows


def _refresh_table(window: sg.Window) -> None:
    global _table_data
    _table_data = _results_to_table(_scan_results)
    window["-TABLE-"].update(values=_table_data)


def _current_config(values: dict) -> dict[str, Any]:
    """Read the current GUI values back into a config dict."""
    cfg = load_config()
    cfg["tesseract_path"] = values.get("-TESS-PATH-", cfg["tesseract_path"])
    cfg["poppler_path"] = values.get("-POP-PATH-", cfg["poppler_path"])
    cfg["ocr_languages"] = values.get("-OCR-LANG-", cfg["ocr_languages"])
    cfg["filename_template"] = values.get("-TEMPLATE-", cfg["filename_template"])
    cfg["confidence_threshold"] = values.get("-CONF-THRESH-", cfg["confidence_threshold"])
    cfg["preserve_timestamps"] = values.get("-PRESERVE-TS-", cfg["preserve_timestamps"])
    cfg["debug_mode"] = values.get("-DEBUG-", cfg["debug_mode"])
    cfg["preprocessing"] = {
        "binarize": values.get("-PP-BIN-", False),
        "deskew": values.get("-PP-DESKEW-", False),
        "contrast": values.get("-PP-CONTRAST-", False),
    }
    return cfg


# ── Background scanning ─────────────────────────────────────────────────

_cancel = False


def _scan_thread(folder: str, cfg: dict, db: FileDB, force: bool, window: sg.Window) -> None:
    global _scan_results, _cancel
    _cancel = False
    import time, sys
    _t0 = time.time()

    def prog(cur: int, total: int, name: str) -> None:
        pct = int(cur / total * 100) if total else 0
        window.write_event_value("-SCAN-PROGRESS-", (pct, f"[{cur}/{total}] {name}"))
        # Also print to terminal so the console shows progress
        elapsed = time.time() - _t0
        avg = elapsed / cur if cur else 0
        remaining = avg * (total - cur)
        mins, secs = divmod(int(remaining), 60)
        eta = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
        print(f"  [{cur}/{total}] {pct:3d}%  ETA {eta}  {name}", flush=True)

    _scan_results = scan_folder(
        folder, cfg, db, force_rescan=force,
        progress_callback=prog, cancel_flag=lambda: _cancel,
    )
    window.write_event_value("-SCAN-DONE-", True)


# ── Installer wrappers (threaded) ───────────────────────────────────────


def _installer_thread(kind: str, window: sg.Window, **kwargs: Any) -> None:
    def prog(pct: int, msg: str) -> None:
        window.write_event_value("-INST-PROGRESS-", (pct, msg))

    if kind == "tesseract":
        if _has_winget():
            result = install_tesseract_winget(progress=prog)
        elif _has_choco():
            result = install_tesseract_choco(progress=prog)
        else:
            result = install_tesseract_manual(progress=prog)
    elif kind == "poppler":
        result = install_poppler(progress=prog, **kwargs)
    elif kind == "langpack":
        result = install_language_pack(progress=prog, **kwargs)
    else:
        result = {"success": False, "error": f"Unknown installer kind: {kind}"}
    window.write_event_value("-INST-DONE-", result)


# ── Main loop ────────────────────────────────────────────────────────────

def run_gui() -> None:
    """Create the window and enter the event loop."""
    global _scan_results, _selected, _last_report, _cancel

    cfg = load_config()
    db = FileDB(cfg["db_path"])

    window = sg.Window(
        "ExamPDFRenamer",
        _build_layout(cfg),
        font=FONT,
        finalize=True,
        resizable=True,
    )

    # Check deps on start
    tess_status = check_tesseract(cfg.get("tesseract_path", ""))
    pop_status = check_poppler(cfg.get("poppler_path", ""))
    dep_msgs: list[str] = []
    if not tess_status["installed"]:
        dep_msgs.append("Tesseract OCR not found.")
    if not pop_status["installed"]:
        dep_msgs.append("Poppler not found.")
    if dep_msgs:
        window["-STATUS-"].update(" | ".join(dep_msgs) + " Use Install buttons above.")
    else:
        v = tess_status.get("version", "?")
        window["-STATUS-"].update(f"Tesseract v{v} ✓ | Poppler ✓")
        if tess_status.get("path") and not cfg.get("tesseract_path"):
            window["-TESS-PATH-"].update(tess_status["path"])
        if pop_status.get("path") and not cfg.get("poppler_path"):
            window["-POP-PATH-"].update(pop_status["path"])

    while True:
        result = window.read(timeout=100)
        if result is None:
            break
        event, values = result

        if event in (sg.WIN_CLOSED, "-EXIT-"):
            break

        # ── Scan ─────────────────────────────────────────────────────
        if event == "-SCAN-":
            folder = values["-FOLDER-"]
            if not folder or not os.path.isdir(folder):
                sg.popup_error("Please select a valid folder.", title="Error")
                continue
            cfg = _current_config(values)
            window["-STATUS-"].update("Scanning…")
            window["-PROG-"].update(0)
            threading.Thread(
                target=_scan_thread,
                args=(folder, cfg, db, values.get("-FORCE-", False), window),
                daemon=True,
            ).start()

        elif event == "-SCAN-PROGRESS-":
            pct, msg = values[event]
            window["-PROG-"].update(pct)
            window["-STATUS-"].update(msg)

        elif event == "-SCAN-DONE-":
            _refresh_table(window)
            active = sum(1 for r in _scan_results if not r.skipped)
            skipped = sum(1 for r in _scan_results if r.skipped)
            window["-STATUS-"].update(
                f"Scan complete: {active} files to review, {skipped} skipped."
            )
            window["-PROG-"].update(100)

        # ── Preview (same as scan but does nothing extra) ────────────
        elif event == "-PREVIEW-":
            if not _scan_results:
                sg.popup("Run Scan first.", title="Info")
            else:
                _refresh_table(window)
                sg.popup(
                    f"{len(_table_data)} files previewed. Edit names or Bulk Approve, then Rename.",
                    title="Preview",
                )

        # ── Bulk approve ─────────────────────────────────────────────
        elif event == "-BULK-":
            thresh = float(values.get("-CONF-THRESH-", 0.9))
            count = 0
            idx = 0
            for r in _scan_results:
                if r.skipped:
                    continue
                conf = r.fields.get("overall_confidence", 0)
                if conf >= thresh:
                    _selected[idx] = True
                    if idx < len(_table_data):
                        _table_data[idx][0] = "☑"
                    count += 1
                idx += 1
            window["-TABLE-"].update(values=_table_data)
            window["-STATUS-"].update(f"Bulk approved {count} files with confidence ≥ {thresh:.2f}")

        # ── Table click – toggle selection ───────────────────────────
        elif isinstance(event, tuple) and event[0] == "-TABLE-":
            # Click event: event[2] is (row, col)
            if event[2][0] is not None and event[2][0] >= 0:
                row = event[2][0]
                if row < len(_selected):
                    _selected[row] = not _selected[row]
                    _table_data[row][0] = "☑" if _selected[row] else "☐"
                    window["-TABLE-"].update(values=_table_data)

        # ── Right-click: Edit Suggested Name ─────────────────────────
        elif event == "Edit Suggested Name":
            sel = values["-TABLE-"]
            if sel:
                row = sel[0]
                old_name = _table_data[row][7]
                new_name = sg.popup_get_text(
                    "Edit suggested filename:", title="Edit", default_text=old_name
                )
                if new_name and new_name != old_name:
                    _table_data[row][7] = new_name
                    # Update the scan result too
                    active_idx = 0
                    for r in _scan_results:
                        if r.skipped:
                            continue
                        if active_idx == row:
                            r.suggested_name = new_name
                            break
                        active_idx += 1
                    window["-TABLE-"].update(values=_table_data)

        elif event == "Toggle Selection":
            sel = values["-TABLE-"]
            for row in sel:
                if row < len(_selected):
                    _selected[row] = not _selected[row]
                    _table_data[row][0] = "☑" if _selected[row] else "☐"
            window["-TABLE-"].update(values=_table_data)

        elif event == "View Snippet":
            sel = values["-TABLE-"]
            if sel:
                row = sel[0]
                active_idx = 0
                for r in _scan_results:
                    if r.skipped:
                        continue
                    if active_idx == row:
                        snippets = []
                        for fname in ("year", "publisher", "subject", "part"):
                            fd = r.fields.get(fname, {})
                            snippets.append(
                                f"{fname}: {fd.get('value', '?')} "
                                f"(conf={fd.get('confidence', 0):.2f})\n"
                                f"  snippet: {fd.get('snippet', 'N/A')}"
                            )
                        sg.popup_scrolled(
                            "\n\n".join(snippets),
                            title=f"Snippets – {Path(r.original_path).name}",
                            size=(80, 20),
                        )
                        break
                    active_idx += 1

        # ── Rename Selected ──────────────────────────────────────────
        elif event == "-RENAME-":
            cfg = _current_config(values)
            to_rename: list[tuple[ScanResult, int]] = []
            active_idx = 0
            for r in _scan_results:
                if r.skipped:
                    continue
                if active_idx < len(_selected) and _selected[active_idx]:
                    to_rename.append((r, active_idx))
                active_idx += 1

            if not to_rename:
                sg.popup("No files selected. Click rows or use Bulk Approve.", title="Info")
                continue

            # Confirmation
            if not sg.popup_yes_no(
                f"Rename {len(to_rename)} file(s)?", title="Confirm"
            ) == "Yes":
                continue

            actions: list[dict[str, str]] = []
            errors: list[str] = []
            for r, row_idx in to_rename:
                src = Path(r.original_path)
                dst = src.parent / r.suggested_name
                try:
                    actual = rename_file(
                        src, dst,
                        preserve_timestamps=cfg.get("preserve_timestamps", True),
                    )
                    actions.append({"old_path": str(src), "new_path": str(actual)})
                    db.add_entry(r.sha256, {"renamed_to": str(actual)})
                except Exception as e:
                    errors.append(f"{src.name}: {e}")

            # Save undo report
            if actions:
                _last_report = generate_report(_scan_results, actions, cfg["reports_dir"])

            msg = f"Renamed {len(actions)} file(s)."
            if errors:
                msg += f"\n{len(errors)} error(s):\n" + "\n".join(errors[:10])
            sg.popup(msg, title="Rename Complete")
            _refresh_table(window)

        # ── Save Report ──────────────────────────────────────────────
        elif event == "-REPORT-":
            if not _scan_results:
                sg.popup("Nothing to report. Run Scan first.", title="Info")
                continue
            cfg = _current_config(values)
            path = generate_report(_scan_results, [], cfg["reports_dir"])
            sg.popup(f"Report saved:\n{path}", title="Report")

        elif event == "-CSV-":
            if not _last_report:
                sg.popup("Save a report first.", title="Info")
                continue
            csv_path = export_csv(_last_report)
            sg.popup(f"CSV exported:\n{csv_path}", title="CSV")

        # ── Undo ─────────────────────────────────────────────────────
        elif event == "-UNDO-":
            if not _last_report:
                sg.popup("No recent rename report to undo.", title="Info")
                continue
            if sg.popup_yes_no(
                f"Undo all renames from last report?\n{_last_report}",
                title="Confirm Undo",
            ) != "Yes":
                continue
            results = undo_from_report(_last_report)
            ok = sum(1 for r in results if r["undone"])
            fail = len(results) - ok
            sg.popup(f"Undone: {ok}, Failed: {fail}", title="Undo Complete")

        # ── Installers ───────────────────────────────────────────────
        elif event == "-INST-TESS-":
            if sg.popup_yes_no(
                "This will download and install Tesseract OCR.\n"
                "Administrator elevation may be required.\n\nProceed?",
                title="Install Tesseract",
            ) != "Yes":
                continue
            window["-STATUS-"].update("Installing Tesseract…")
            threading.Thread(
                target=_installer_thread,
                args=("tesseract", window),
                daemon=True,
            ).start()

        elif event == "-INST-POP-":
            if sg.popup_yes_no(
                "This will download and extract Poppler to a local folder.\n\nProceed?",
                title="Install Poppler",
            ) != "Yes":
                continue
            window["-STATUS-"].update("Installing Poppler…")
            threading.Thread(
                target=_installer_thread,
                args=("poppler", window),
                daemon=True,
            ).start()

        elif event == "-INST-LANG-":
            lang = sg.popup_get_text(
                "Enter language code (e.g. chi_tra, chi_sim, jpn):",
                title="Install Language Pack",
                default_text="chi_tra",
            )
            if not lang:
                continue
            tess = values.get("-TESS-PATH-", "")
            window["-STATUS-"].update(f"Installing {lang} language pack…")
            threading.Thread(
                target=_installer_thread,
                args=("langpack", window),
                kwargs={"lang": lang, "tesseract_path": tess},
                daemon=True,
            ).start()

        elif event == "-INST-PROGRESS-":
            pct, msg = values[event]
            window["-PROG-"].update(pct)
            window["-STATUS-"].update(msg)

        elif event == "-INST-DONE-":
            result = values[event]
            if result.get("success"):
                msg = "Installation successful!"
                if result.get("path"):
                    msg += f"\nPath: {result['path']}"
                    # Auto-update settings
                    if "tesseract" in str(result.get("path", "")).lower():
                        window["-TESS-PATH-"].update(result["path"])
                    elif "poppler" in str(result.get("path", "")).lower():
                        window["-POP-PATH-"].update(result["path"])
                sg.popup(msg, title="Success")
            else:
                sg.popup_error(
                    f"Installation failed:\n{result.get('error', 'Unknown error')}\n\n"
                    "See README.md for manual installation steps.",
                    title="Error",
                )
            window["-STATUS-"].update("Ready")
            window["-PROG-"].update(0)

        # ── Save settings ────────────────────────────────────────────
        elif event == "-SAVE-CFG-":
            cfg = _current_config(values)
            save_config(cfg)
            sg.popup("Settings saved.", title="Settings")

    window.close()
