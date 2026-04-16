# sync_site — EPH Teaching Resource Sync

Automates downloading and syncing teaching resources from `mif2e.ephhk.com` (Assessment Resources, TSA Kit, DSE Kit, Worksheets) using Playwright for Python.

## Setup (Windows)

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers (required once)
playwright install chromium
```

## Usage

### Dry-run (default — reports actions, changes nothing)

```powershell
python sync_site.py --local-folder "C:\Users\You\Resources" --dry-run
```

### Apply changes (downloads and replaces outdated files)

```powershell
python sync_site.py --local-folder "C:\Users\You\Resources" --apply
```

### Debug mode (visible browser, verbose logging)

```powershell
python sync_site.py --local-folder "C:\Users\You\Resources" --debug --no-headless
```

### All flags

| Flag | Default | Description |
|------|---------|-------------|
| `--local-folder PATH` | **(required)** | Local folder to compare/replace files |
| `--headless` | ON | Run browser headless |
| `--no-headless` | — | Show browser UI |
| `--dry-run` | ON | Report only, no changes |
| `--apply` | — | Actually replace/update files |
| `--concurrency N` | 3 | Parallel downloads |
| `--download-dir PATH` | auto temp | Temporary download location |
| `--manifest PATH` | `manifest_<ts>.json` | Output manifest path |
| `--log PATH` | `sync.log` | Log file path |
| `--debug` | OFF | Non-headless + verbose logging |

## How It Works

1. **Login** — Opens `mif2e.ephhk.com`, clicks the login control, fills EPH ID (`4201t03`, hardcoded in `sync_site.py` line ~20) and password (prompted at runtime via `getpass`).
2. **Discover** — Navigates the site's dropdown menus (Assessment Resources / TSA Kit / DSE Kit / Worksheets) and collects all subpage URLs.
3. **Scrape** — Visits each subpage, parses resource tables (Book / Chapter / Section / Questions / Full Solutions columns), and extracts download links.
4. **Download** — Downloads every `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx` file with configurable concurrency.
5. **Compare** — SHA256 compares each download with the corresponding local file.
6. **Replace** (`--apply` only) — Backs up the old file to `backup/YYYYMMDD_HHMMSS/` then replaces it atomically.
7. **Manifest** — Writes a JSON manifest recording every file's URL, metadata, checksums, and action taken.

## File Organization

Downloaded files are saved as:
```
<local-root>/<Book>/<Chapter>/Section <Section> - <original_filename.ext>
```

## Manifest Actions

| Action | Meaning |
|--------|---------|
| `new` | File not present locally; copied in |
| `updated` | Local file differs; backed up and replaced |
| `skipped` | SHA256 match; no changes needed |
| `would_replace` | Dry-run: would have been new or updated |
| `local_only` | Present locally but not found on site |
| `failed` | Download failed after retries |

## Running Tests

```powershell
python -m pytest tests/ -v
```

Tests cover checksum computation, filename sanitization, path building, collision resolution, backup logic, and the compare-and-act workflow — all using temp files (no network needed).

## Troubleshooting

- **CAPTCHA detected**: The site may show a CAPTCHA. Log in manually in a regular browser first, then retry. Use `--debug --no-headless` to watch the login flow.
- **Timeout errors**: The site may be slow. Retry the script; transient errors are retried automatically (3 attempts with exponential backoff).
- **Login button not found**: The site UI may have changed. Use `--debug` to inspect, then update the login selectors in `sync_site.py`.
- **No subpages found**: Ensure login succeeded. The nav menus may require authentication. Check `sync.log` for details.
- **`playwright install` fails**: Ensure you have a working internet connection and run the command in an elevated terminal if needed.

## Selector Assumptions

- Login trigger: Looks for elements with text "登入" / "Login" or class `.login` / `#login` in the top-right area.
- Nav items: Chinese labels 評估資源, TSA 資源套, DSE 資源套, 工作紙 with hover dropdowns.
- Resource tables: `<table>` elements with headers containing "Book", "Chapter", "Section", "Questions", "Full Solutions" (or Chinese equivalents 冊/章/節/題目/答案).
- Download links: `<a>` tags with `href` pointing to files with extensions `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.zip`, `.rar`.

If the site structure changes, these heuristics may need tuning — the code includes multi-strategy fallbacks for each step.
