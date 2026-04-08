# FolderSync

**Compare files between two local folders and sync newer/missing files from source to target.**

FolderSync scans two local directories, compares file timestamps and checksums, and lets you selectively copy newer or missing files — all from a FreeSimpleGUI desktop interface.

---

## Features

- **Local folder comparison** — scans two folders recursively, compares timestamps, sizes, and SHA-256 checksums.
- **Dry-run preview** — always shows a diff table before copying anything.
- **Per-file selection** — checkboxes, bulk-select, and deselect controls.
- **Backup & undo** — existing files are copied to a timestamped backup folder before replacement; one-click undo from saved reports.
- **Concurrent file copies** — configurable thread pool for fast sync.
- **JSON & CSV reports** — detailed reports with original/backup paths, timestamps, checksums, and action taken.
- **Extension & regex filtering** — limit comparison to specific file types or name patterns.
- **Hidden file support** — optionally include hidden files and folders.
- **CLI mode** — headless scan + preview for power users and automation.

---

## Installation

```bash
# 1. Clone or copy the WebFileSync folder
# 2. Install dependencies
pip install -r requirements.txt
```

### Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| `FreeSimpleGUI` | ≥ 5.0 | Desktop GUI |
| `python-dateutil` | ≥ 2.8 | Robust date parsing fallback |

Python 3.10+ recommended.

---

## Quick Start

### GUI (default)

```bash
python -m WebFileSync
```

1. Select the **Source Folder** (the reference/newer folder).
2. Select the **Target Folder** (the folder to update).
3. Click **Scan & Compare** — scans both folders and shows differences.
4. Review the table, toggle checkboxes, then click **Sync Selected**.
5. Click **Save Report** to export JSON/CSV.

### CLI (headless)

```bash
# Create a config file first (copy config.sample.json → config.json, edit values)
python -m WebFileSync --cli --config config.json
```

This prints a preview table and saves a report without launching the GUI.

---

## Configuration

Copy `config.sample.json` to `config.json` and edit:

| Key | Default | Description |
|---|---|---|
| `source_folder` | `""` | Reference folder (newer files) |
| `target_folder` | `""` | Folder to update |
| `file_extensions` | `[]` | Filter by extension (empty = all) |
| `regex_patterns` | `[]` | Additional regex path filters |
| `timestamp_tolerance_seconds` | `120` | Tolerance for "close enough" timestamps |
| `max_concurrency` | `4` | Parallel copy threads |
| `dry_run` | `false` | Preview only, no copies |
| `preserve_timestamps` | `true` | Copy source mtime to target |
| `recursive` | `true` | Scan subfolders recursively |
| `include_hidden` | `false` | Include hidden files/folders |

---

## Comparison Logic

1. **Target file missing** → `Copy (new file)`.
2. **Source newer** → compare timestamps ± tolerance.
   - Source newer → `Copy & Replace`.
   - Timestamps close, different size → SHA-256 checksum comparison.
3. **Sizes differ** → SHA-256 comparison, copy if different.
4. **Same size, same timestamp** → `Skip (up to date)`.
5. **Only in target** → reported but not selected for action.

All timestamps are normalized to UTC before comparison.

---

## Backup & Undo

- Before replacing any file, the original is copied to:
  ```
  <target_folder>/.foldersync_backups/<YYYYMMDD_HHMMSS>/
  ```
- A `manifest.json` records every backup.
- Click **Undo Last** in the GUI to restore files from any previous report.
- Click **Backups** to open the backup folder in your file manager.

---

## Reports

Reports are saved to `<target_folder>/.foldersync_reports/`:

- **JSON** (detailed): timestamps, checksums, backup paths, actions.
- **CSV** (summary): one row per file with key columns.

---

## Tests

```bash
# Run all tests from the workspace root
python -m pytest WebFileSync/tests/ -v

# Or with unittest
python -m unittest discover -s WebFileSync/tests -v
```

Tests include:
- **test_timestamp.py** — date parsing (RFC 2822, ISO 8601, timezone abbreviations, edge cases).
- **test_mapper.py** — local folder scanning (extensions, regex, hidden files, recursion).
- **test_crawler.py** — folder comparison logic (new files, newer source, checksums, tolerance).
- **test_backup.py** — backup creation, restore, manifest, undo-from-report.
- **test_dry_run.py** — full integration: create temp folders, scan, compare, sync, and verify.

---

## Project Structure

```
WebFileSync/
├── __init__.py
├── __main__.py          # python -m WebFileSync entry
├── main.py              # CLI + GUI launcher
├── gui.py               # FreeSimpleGUI interface
├── scanner.py           # Local directory scanner
├── comparator.py        # Timestamp/checksum comparison engine
├── syncer.py            # Concurrent file copy manager
├── backup.py            # Backup & undo logic
├── reporter.py          # JSON/CSV report generation
├── config.py            # Configuration dataclass & persistence
├── utils.py             # Timestamps, hashing, formatting helpers
├── config.sample.json   # Example configuration
├── requirements.txt
├── LICENSE
├── README.md
└── tests/
    ├── __init__.py
    ├── test_timestamp.py
    ├── test_mapper.py     # Scanner tests
    ├── test_crawler.py    # Comparator tests
    ├── test_backup.py
    └── test_dry_run.py    # Integration tests (sync)
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: PySimpleGUI` | Run `pip install PySimpleGUI` |
| Remote site blocks scraping | Try setting a browser-like User-Agent, or provide an index file manually |
| Non-standard date format not parsed | File an issue — the parser handles most common formats and falls back to `python-dateutil` |
| Downloads fail with SSL errors | Ensure your Python has up-to-date CA certificates; or configure a proxy in settings |
| GUI freezes | Should not happen — all I/O runs in background threads. If it does, increase timeout values |

---

## Security & Privacy

- **No uploads** — local file contents are never sent to external services.
- **Consent required** — a confirmation dialog appears before any file replacement.
- **Domain-locked** — crawling stays within the specified domain unless you explicitly whitelist cross-origin hosts.
- **TLS verified** — HTTPS certificate validation is enabled by default.

---

## License

MIT — see [LICENSE](LICENSE).
