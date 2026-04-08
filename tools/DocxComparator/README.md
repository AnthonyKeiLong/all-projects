# DocxComparator

A Windows desktop application that compares Word (`.docx`) documents between two folders and flags differing files for manual review.

---

## Features

| Feature | Details |
|---|---|
| **File support** | `.docx` via `python-docx`; temporary lock files (`~$`) skipped |
| **Matching** | By bare filename or by relative path; optional recursive scan |
| **Comparison** | SHA-256 hash shortcut for speed; full SequenceMatcher diff for changed files |
| **Content only** | Metadata, styles, headers/footers, and revision marks are ignored |
| **UI** | PyQt5 desktop app with folder selectors, progress bar, sortable results table |
| **Diff viewer** | Side-by-side panes with colour-highlighted hunks and Prev/Next navigation |
| **Decisions** | Mark Reviewed / Ignore / Reset per file — persisted in the session |
| **Export** | CSV export (UTF-8 BOM for Excel compatibility) |
| **Session** | Save and reload full state as JSON (folders, options, all decisions) |
| **Threading** | Scanning runs on a `QThread`; UI stays responsive throughout |

---

## Requirements

- Python 3.10+
- Windows (tested on Windows 10/11; cross-platform in principle)

---

## Setup

```bash
# 1. Clone or download the repository
cd DocxComparator

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# or
.venv\Scripts\activate.bat      # Windows CMD

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running

```bash
python main.py
```

---

## Usage walkthrough

1. **Select folders** — Click *Browse…* for Folder A (the reference) and Folder B (the revision).
2. **Configure options** — Toggle *Recursive* and choose whether to match by filename or relative path.
3. **Scan** — Click *▶ Scan*.  A progress bar tracks completion; results appear as each pair is processed.
4. **Review results** — The table shows each file with its status:
   - **Identical** — content matches exactly; no action needed.
   - **Different** — content differs; flagged as *Pending*.
   - **Only in A / Only in B** — file exists on only one side.
   - **Error** — file could not be read (corrupted, encrypted, etc.).
5. **View diff** — Double-click a **Different** row (or select it and click *View Diff*) to open the side-by-side diff viewer.
   - Lines highlighted in **red** are removed, **green** added, **amber** changed.
   - Use *◀ Prev Diff* / *Next Diff ▶* to jump between changed hunks.
   - Click *✔ Mark Reviewed* or *✖ Ignore* to record your decision.
6. **Filter** — Use the status drop-down and the search box to focus on specific files.
7. **Export** — Click *Export CSV…* to save a full report (opens directly in Excel).
8. **Save / Load session** — Click *Save Session…* to preserve folders, options, and all decisions as a `.json` file; reload later with *Load Session…*.

---

## Project structure

```
DocxComparator/
├── main.py                 Entry point
├── requirements.txt
├── README.md
├── core/
│   ├── models.py           ResultItem dataclass + status/decision constants
│   ├── extractor.py        Text extraction from .docx (normalised)
│   ├── scanner.py          Folder scanning & file-pair matching
│   ├── comparator.py       Hash comparison & side-by-side diff computation
│   ├── session.py          JSON session save/load
│   └── exporter.py         CSV export
├── ui/
│   ├── scan_worker.py      QThread worker (non-blocking scan)
│   ├── results_table.py    Sortable results QTableWidget
│   ├── diff_viewer.py      Side-by-side diff QDialog
│   └── main_window.py      Main QMainWindow
└── tests/
    └── test_comparison.py  Unit tests (no GUI required)
```

---

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Packaging with PyInstaller

```bash
pip install pyinstaller

pyinstaller --onefile --windowed ^
    --name DocxComparator ^
    --add-data "core;core" ^
    --add-data "ui;ui" ^
    main.py
```

The standalone `.exe` will appear in `dist\DocxComparator.exe`.

> **Tip:** Add `--icon your_icon.ico` to set a custom application icon.

---

## Colour legend (diff viewer)

| Colour | Meaning |
|--------|---------|
| White  | Lines are identical |
| 🔴 Light red | Line removed (exists in A, not in B) |
| 🟢 Light green | Line added (exists in B, not in A) |
| 🟡 Light amber | Line changed (present on both sides but different) |
| Light grey | Padding (no corresponding line on this side) |
