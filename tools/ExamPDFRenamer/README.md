# ExamPDFRenamer

A desktop Python application that scans a folder of scanned exam / mock PDF
files (English + Traditional Chinese), extracts structured information via OCR,
and renames files using a configurable template such as:

```
[2022-2023][Aristo][Mathematics]Mock Exam Papers[Paper 1].pdf
```

Built with a **PySimpleGUI dark-theme GUI** and includes an **optional
auto-installer** for Tesseract OCR and Poppler on Windows.

---

## Features

| Feature | Details |
|---|---|
| **Smart text extraction** | Tries native PDF text (PyMuPDF) first; falls back to OCR only when needed. |
| **Tesseract OCR** | Configurable languages, defaults to `eng+chi_tra`. |
| **Field extraction** | Year (range), publisher, subject, paper / section / part, ISBN, DOI. |
| **Confidence scores** | Every extracted field includes a 0–1 confidence and evidence snippet. |
| **Multi-paper detection** | Detects combined booklets and suggests separate filenames. |
| **Filename safety** | Cleans illegal characters, normalises whitespace, caps length. |
| **Idempotency** | SHA-256 tracking DB skips already-processed files. |
| **Collision handling** | Appends `(1)`, `(2)`, … for duplicate filenames. |
| **Undo** | JSON reports enable one-click undo of the last rename batch. |
| **Bulk approve** | Auto-select all files above a confidence threshold. |
| **CSV export** | Export reports for spreadsheet review. |
| **Auto-installer** | Optional one-click install for Tesseract and Poppler on Windows. |

---

## Quick Start

### 1. Install Python dependencies

```bash
cd ExamPDFRenamer
pip install -r requirements.txt
```

### 2. Install system dependencies

> **Tesseract OCR** and **Poppler** are required for OCR and PDF-to-image
> conversion. You have three options:

#### Option A: Use the in-app installer (recommended)

Launch the app and click **Install Tesseract** / **Install Poppler** in the
GUI. The app will download from official sources and configure paths
automatically.

#### Option B: winget (Windows 10/11, recommended)

`winget` is built into modern Windows — no extra install needed:

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
```

For Poppler, use the in-app installer or manual install (winget does not
package Poppler).

#### Option C: Chocolatey (Windows)

Requires [Chocolatey](https://chocolatey.org/install) to be installed first:

```powershell
choco install -y tesseract
choco install -y poppler
```

#### Option D: Manual install

See [Manual Installation](#manual-installation) below.

### 3. Run

```bash
python main.py          # GUI mode
python main.py --headless --folder "C:\exams"  # headless dry-run
```

---

## Manual Installation

### Tesseract OCR

1. Download the installer for your architecture:
   - **64-bit:** <https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3/tesseract-ocr-w64-setup-5.3.3.20231005.exe>
   - **32-bit:** <https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3/tesseract-ocr-w32-setup-5.3.3.20231005.exe>
2. Run the installer. During setup, check **Additional language data** and
   select **Chinese - Traditional** (`chi_tra`).
3. After installation, note the install path (default:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`).
4. In the app's **Settings**, paste the path into **Tesseract path**, or add
   `C:\Program Files\Tesseract-OCR` to your system `PATH`.

### Poppler

1. Download the latest release:
   <https://github.com/oschwartz10612/poppler-windows/releases>
2. Extract the ZIP to a permanent location (e.g., `C:\poppler`).
3. In the app's **Settings**, set **Poppler path** to the `bin` folder inside
   the extracted directory (e.g., `C:\poppler\Library\bin`).

### Tesseract Language Packs

If `chi_tra` was not selected during Tesseract setup:

1. Download `chi_tra.traineddata` from
   <https://github.com/tesseract-ocr/tessdata_best/raw/main/chi_tra.traineddata>
2. Copy it to `<Tesseract install>\tessdata\`.
3. Or use the **Install Language Pack** button in the app GUI.

---

## Configuration

On first run the app uses built-in defaults. Click **Save Settings** to
persist your configuration to `config.json`.

| Setting | Default | Description |
|---|---|---|
| `tesseract_path` | (auto-detect) | Path to `tesseract.exe` |
| `poppler_path` | (auto-detect) | Path to Poppler `bin` folder |
| `ocr_languages` | `eng+chi_tra` | Tesseract language string |
| `filename_template` | `[{year}][{publisher}][{subject}]Mock Exam Papers[{part}].pdf` | Supported tokens: `{year}`, `{publisher}`, `{subject}`, `{part}`, `{orig}` |
| `confidence_threshold` | `0.9` | Minimum overall confidence for bulk-approve |
| `preserve_timestamps` | `true` | Keep original file modification time |
| `max_filename_length` | `120` | Hard cap for generated filenames |
| `ocr_dpi` | `300` | DPI for PDF→image conversion |
| `debug_mode` | `false` | Save OCR images and intermediate text |
| `preprocessing` | binarize/deskew/contrast off | Image preprocessing before OCR |
| `custom_publishers` | (HK DSE defaults) | Keyword list for publisher detection |

### Subject Mapping

Copy `subject_mapping.sample.csv` to `subject_mapping.csv` and edit to match
your curriculum. Each row maps a keyword (case-insensitive) to a canonical
subject name.

---

## Workflow

1. **Select folder** – choose the root folder containing your exam PDFs.
2. **Scan** – the app recursively finds `.pdf` files, extracts text, and
   detects fields. A progress bar shows status; the GUI stays responsive.
3. **Preview** – review the table of extracted fields, confidence scores,
   and suggested filenames.
4. **Edit** – right-click a row → **Edit Suggested Name** to override.
   Right-click → **View Snippet** to see the evidence for each field.
5. **Select** – click rows to toggle selection, or use **Bulk Approve ≥
   Threshold** to auto-select high-confidence matches.
6. **Rename** – click **Rename Selected**. A JSON report is saved first
   for undo capability.
7. **Undo** – click **Undo Last Rename** to reverse the most recent batch
   using the saved report.

---

## Undo Instructions

Every rename batch saves a JSON report in the `reports/` directory. To undo:

1. Click **Undo Last Rename** in the GUI.  The app reads the most recent
   report and moves every renamed file back to its original path.

2. **Manual undo:** open the report JSON, find the `"actions"` array, and
   move each file from `"new_path"` back to `"old_path"`.

---

## Why Tesseract?

- **Offline:** No internet required after installation. Works in air-gapped
  school environments.
- **Privacy:** Exam papers never leave the local machine. No cloud uploads.
- **Free & open-source:** Apache 2.0 license. No API keys, no per-page fees.
- **Traditional Chinese:** Official `chi_tra` language pack with reasonable
  accuracy for printed text.
- **Limitations:** Accuracy depends on scan quality. Hand-written content is
  poorly supported. Mixed-layout pages (tables, columns) may produce garbled
  text. Use preprocessing (binarise, contrast) and higher DPI to improve
  results.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `TesseractNotFoundError` | Set **Tesseract path** in Settings, or add Tesseract to PATH. |
| `PDFInfoNotInstalledError` | Set **Poppler path** in Settings to the `bin` folder. |
| Poor OCR accuracy | Increase **OCR DPI** to 400+. Enable **Binarize** and **Contrast** preprocessing. |
| Missing `chi_tra` | Click **Install Language Pack** or download `chi_tra.traineddata` manually. |
| Filename too long | Reduce `max_filename_length` in Settings. |
| Admin elevation prompt | The Tesseract installer requires admin rights. Use Chocolatey or manual install if you cannot elevate. |
| `ModuleNotFoundError: FreeSimpleGUI` | `pip install FreeSimpleGUI` or `pip install PySimpleGUI==4.60.5`. |

---

## Running Tests

```bash
# Unit tests (no OCR dependencies needed)
python tests/test_extractor.py
python tests/test_renamer.py

# Integration dry-run (needs PyMuPDF)
python tests/test_dry_run.py
```

---

## Project Structure

```
ExamPDFRenamer/
├── main.py                # Entry point (GUI or headless)
├── gui.py                 # PySimpleGUI dark-theme interface
├── scanner.py             # Folder scanning orchestrator
├── ocr_engine.py          # Native text + Tesseract OCR pipeline
├── extractor.py           # Field extraction (year, publisher, subject, part)
├── renamer.py             # Filename building and rename operations
├── installer.py           # Auto-installer for Tesseract & Poppler
├── config.py              # Configuration management
├── db.py                  # SHA-256 file tracking database
├── report.py              # JSON/CSV reporting and undo
├── utils.py               # Filename cleaning and helpers
├── requirements.txt       # Python dependencies
├── config.sample.json     # Sample configuration
├── subject_mapping.sample.csv  # Sample keyword→subject mapping
├── sample_report.json     # Example output report
├── DESIGN_NOTES.md        # Architecture trade-off notes
├── LICENSE                # MIT License
├── README.md              # This file
└── tests/
    ├── test_extractor.py  # Extractor unit tests
    ├── test_renamer.py    # Renamer unit tests
    ├── test_dry_run.py    # Integration dry-run
    └── sample_pdfs/       # Place test PDFs here
```

---

## License

MIT — see [LICENSE](LICENSE).
