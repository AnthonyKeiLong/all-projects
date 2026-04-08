"""OCR engine: native PDF text extraction with Tesseract OCR fallback."""

import logging
from pathlib import Path
from typing import Optional

import fitz  # type: ignore[import-untyped]  # PyMuPDF

logger = logging.getLogger(__name__)


def extract_text_native(pdf_path: str | Path) -> str:
    """Extract embedded text from *pdf_path* using PyMuPDF."""
    parts: list[str] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            parts.append(str(page.get_text()))  # type: ignore[arg-type]
        doc.close()
    except Exception as e:
        logger.warning("Native extraction failed for %s: %s", pdf_path, e)
    return "\n".join(parts)


def extract_text_ocr(
    pdf_path: str | Path,
    lang: str = "eng+chi_tra",
    dpi: int = 300,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    preprocess: Optional[dict] = None,
    debug_dir: Optional[str] = None,
) -> str:
    """Convert PDF pages to images and run Tesseract OCR."""
    from pdf2image import convert_from_path  # type: ignore[import-untyped]
    import pytesseract  # type: ignore[import-untyped]
    from PIL import ImageFilter, ImageEnhance  # type: ignore[import-untyped]

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    pop_kw: dict = {}
    if poppler_path:
        pop_kw["poppler_path"] = poppler_path

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi, **pop_kw)
    except Exception as e:
        logger.error("pdf2image failed for %s: %s", pdf_path, e)
        return ""

    parts: list[str] = []
    preprocess = preprocess or {}
    for i, img in enumerate(images):
        if preprocess.get("contrast"):
            img = ImageEnhance.Contrast(img).enhance(2.0)
        if preprocess.get("binarize"):
            img = img.convert("L").point(lambda x: 0 if x < 128 else 255, "1")  # type: ignore[operator,arg-type]
        if preprocess.get("deskew"):
            img = img.filter(ImageFilter.SHARPEN)

        if debug_dir:
            dbg = Path(debug_dir)
            dbg.mkdir(parents=True, exist_ok=True)
            img.save(dbg / f"page_{i + 1}.png")

        try:
            parts.append(pytesseract.image_to_string(img, lang=lang))
        except Exception as e:
            logger.warning("OCR failed on page %d of %s: %s", i + 1, pdf_path, e)
    return "\n".join(parts)


def extract_text(
    pdf_path: str | Path,
    lang: str = "eng+chi_tra",
    dpi: int = 300,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    preprocess: Optional[dict] = None,
    debug_dir: Optional[str] = None,
    min_native_chars: int = 50,
) -> tuple[str, str]:
    """Try native text first; fall back to OCR.

    Returns ``(text, method)`` where *method* is ``'native'`` or ``'ocr'``.
    """
    native = extract_text_native(pdf_path).strip()
    if len(native) >= min_native_chars:
        logger.info("Native text OK for %s (%d chars)", pdf_path, len(native))
        return native, "native"

    logger.info("Native text too short (%d chars), OCR fallback for %s", len(native), pdf_path)
    ocr = extract_text_ocr(
        pdf_path,
        lang=lang,
        dpi=dpi,
        poppler_path=poppler_path,
        tesseract_cmd=tesseract_cmd,
        preprocess=preprocess,
        debug_dir=debug_dir,
    ).strip()

    if ocr:
        return ocr, "ocr"
    return native or ocr, "native" if native else "ocr"
