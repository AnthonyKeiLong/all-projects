# Design Notes

Key architectural trade-offs and rationale.

## 1. Local OCR (Tesseract) vs Cloud OCR

**Choice:** Tesseract (local, offline).

- **Privacy:** Exam papers may be copyrighted or contain student data. Uploading
  to cloud APIs introduces data-handling and legal concerns.
- **Cost:** Tesseract is free and open-source (Apache 2.0). Cloud OCR charges per
  page and requires API keys.
- **Offline:** Teachers and students may have limited or restricted internet
  access in school environments.
- **Trade-off:** Tesseract accuracy on scanned documents is lower than
  state-of-the-art cloud models, especially for mixed English / Traditional
  Chinese layouts. We mitigate this with preprocessing options (binarise,
  contrast, deskew) and by always trying native text extraction first.

## 2. Text-first, then OCR fallback

Native PDF text extraction (PyMuPDF) is instantaneous and perfectly accurate
when the PDF has embedded text layers. OCR is expensive (seconds per page) and
lossy. Checking native text first avoids unnecessary OCR on the ~60 % of exam
PDFs that are already digitally generated.

## 3. User-editable subject / publisher mappings

Hard-coding every possible publisher and subject would be brittle and
culturally biased. Instead we ship sensible defaults for Hong Kong DSE exams
but let users extend via `subject_mapping.csv` and the `custom_publishers`
config list. This keeps the software useful across different curricula
(IB, A-Level, local exams) with zero code changes.

## 4. Auto-installer convenience vs admin elevation prompts

The optional Tesseract / Poppler installer improves onboarding for non-technical
users but introduces UX friction (admin prompts, download trust). We handle
this by:

- Always requiring explicit user consent before any download or system change.
- Preferring Chocolatey when available (admin already expected).
- Falling back to user-space extraction for Poppler (no admin needed).
- Providing clear "Manual Install" instructions so users can bypass
  auto-install entirely.
- Verifying SHA-256 checksums when available.

## 5. JSON-based processed-files DB

A full SQL database would be over-engineered for this use case. The SHA-256
keyed JSON file is portable, human-readable, simple to back up, and sufficient
for the expected scale (< 10 000 files).
