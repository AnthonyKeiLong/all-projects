"""Optional auto-installer for Tesseract OCR and Poppler on Windows.

Every download/install action requires explicit user consent and only
fetches from official / well-known trusted sources.  Checksums are
verified when available.
"""

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)

# ── Trusted download URLs ────────────────────────────────────────────────

TESSERACT_URLS: dict[str, str] = {
    "x64": (
        "https://github.com/UB-Mannheim/tesseract/releases/download/"
        "v5.3.3/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
    ),
    "x86": (
        "https://github.com/UB-Mannheim/tesseract/releases/download/"
        "v5.3.3/tesseract-ocr-w32-setup-5.3.3.20231005.exe"
    ),
}

POPPLER_URL: str = (
    "https://github.com/oschwartz10612/poppler-windows/releases/download/"
    "v24.02.0-0/Release-24.02.0-0.zip"
)

# Checksums – leave empty to skip verification (the GUI warns the user).
TESSERACT_CHECKSUMS: dict[str, str] = {"x64": "", "x86": ""}
POPPLER_CHECKSUM: str = ""

TESSDATA_BEST_BASE = "https://github.com/tesseract-ocr/tessdata_best/raw/main"

# ── Utilities ────────────────────────────────────────────────────────────


def _arch() -> str:
    return "x64" if platform.machine().endswith("64") else "x86"


def _find_tesseract() -> Optional[str]:
    """Locate ``tesseract.exe`` in PATH or common Windows install dirs."""
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.isfile(p):
            return p
    return None


def _tesseract_version(exe: str) -> Optional[str]:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        m = re.search(r"tesseract\s+v?([\d.]+)", r.stdout + r.stderr)
        return m.group(1) if m else None
    except Exception:
        return None


def _has_choco() -> bool:
    return shutil.which("choco") is not None


def _has_winget() -> bool:
    return shutil.which("winget") is not None


def _verify_sha256(filepath: str, expected: str) -> bool:
    if not expected:
        logger.warning("No checksum provided – skipping verification for %s", filepath)
        return True
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    if actual != expected.lower():
        logger.error("Checksum mismatch for %s: expected %s, got %s", filepath, expected, actual)
        return False
    return True


def _download(url: str, dest: str, progress: Optional[Callable] = None) -> bool:
    try:
        def hook(count: int, bs: int, total: int) -> None:
            if progress and total > 0:
                pct = min(100, int(count * bs * 100 / total))
                progress(pct, f"Downloading… {pct}%")

        urlretrieve(url, dest, reporthook=hook)
        return True
    except Exception as e:
        logger.error("Download failed: %s", e)
        return False


# ── Public check functions ───────────────────────────────────────────────


def check_tesseract(saved_path: str = "") -> dict[str, Any]:
    """Return installation status dict for Tesseract."""
    exe = saved_path if saved_path and os.path.isfile(saved_path) else _find_tesseract()
    if exe:
        ver = _tesseract_version(exe)
        if ver:
            return {
                "installed": True,
                "path": exe,
                "version": ver,
                "sufficient": int(ver.split(".")[0]) >= 4,
            }
    return {"installed": False, "path": "", "version": "", "sufficient": False}


def check_poppler(saved_path: str = "") -> dict[str, Any]:
    """Return installation status dict for Poppler."""
    if saved_path and os.path.isdir(saved_path):
        for name in ("pdftoppm.exe", "Library/bin/pdftoppm.exe"):
            if os.path.isfile(os.path.join(saved_path, name)):
                return {"installed": True, "path": saved_path}
    if shutil.which("pdftoppm"):
        return {"installed": True, "path": ""}
    # Check app-local folder
    local = Path(__file__).parent / "poppler"
    if local.exists():
        for hit in local.rglob("pdftoppm.exe"):
            return {"installed": True, "path": str(hit.parent)}
    return {"installed": False, "path": ""}


# ── Tesseract installers ────────────────────────────────────────────────


def install_tesseract_winget(progress: Optional[Callable] = None) -> dict[str, Any]:
    """Install Tesseract via winget (built into Windows 10/11)."""
    try:
        if progress:
            progress(10, "Installing Tesseract via winget…")
        r = subprocess.run(
            ["winget", "install", "-e", "--id", "UB-Mannheim.TesseractOCR",
             "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode == 0:
            exe = _find_tesseract()
            if exe:
                if progress:
                    progress(100, "Tesseract installed via winget ✓")
                return {"success": True, "path": exe}
        return {"success": False, "error": r.stderr or "winget install finished but tesseract not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def install_tesseract_choco(progress: Optional[Callable] = None) -> dict[str, Any]:
    """Install Tesseract via Chocolatey (requires admin)."""
    try:
        if progress:
            progress(10, "Installing Tesseract via Chocolatey…")
        r = subprocess.run(
            ["choco", "install", "-y", "tesseract"],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            exe = _find_tesseract()
            if exe:
                if progress:
                    progress(100, "Tesseract installed via Chocolatey ✓")
                return {"success": True, "path": exe}
        return {"success": False, "error": r.stderr or "choco install finished but tesseract not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def install_tesseract_manual(progress: Optional[Callable] = None) -> dict[str, Any]:
    """Download the UB-Mannheim installer and run it silently."""
    arch = _arch()
    url = TESSERACT_URLS.get(arch, TESSERACT_URLS["x64"])
    chk = TESSERACT_CHECKSUMS.get(arch, "")
    tmp = tempfile.mkdtemp(prefix="tess_install_")
    exe_path = os.path.join(tmp, "tesseract_setup.exe")
    try:
        if progress:
            progress(5, f"Downloading Tesseract ({arch})…")
        if not _download(url, exe_path, progress):
            return {"success": False, "error": "Download failed. Check your internet connection."}
        if chk and not _verify_sha256(exe_path, chk):
            os.remove(exe_path)
            return {"success": False, "error": "Checksum verification failed – file may be corrupted."}
        if progress:
            progress(70, "Running installer (may need admin elevation)…")
        subprocess.run([exe_path, "/S"], capture_output=True, text=True, timeout=300)
        found = _find_tesseract()
        if found:
            if progress:
                progress(100, "Tesseract installed ✓")
            return {"success": True, "path": found}
        return {
            "success": False,
            "error": "Installer completed but tesseract.exe not found. You may need to run as Administrator.",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Installer timed out."}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Poppler installer ───────────────────────────────────────────────────


def install_poppler(
    install_dir: Optional[str] = None,
    progress: Optional[Callable] = None,
) -> dict[str, Any]:
    """Download and extract Poppler for Windows."""
    install_dir = install_dir or str(Path(__file__).parent / "poppler")
    tmp = tempfile.mkdtemp(prefix="poppler_install_")
    zp = os.path.join(tmp, "poppler.zip")
    try:
        if progress:
            progress(5, "Downloading Poppler…")
        if not _download(POPPLER_URL, zp, progress):
            return {"success": False, "error": "Download failed."}
        if POPPLER_CHECKSUM and not _verify_sha256(zp, POPPLER_CHECKSUM):
            os.remove(zp)
            return {"success": False, "error": "Checksum verification failed."}
        if progress:
            progress(70, "Extracting Poppler…")
        os.makedirs(install_dir, exist_ok=True)
        with zipfile.ZipFile(zp, "r") as z:
            z.extractall(install_dir)
        # Locate bin folder
        for root, _dirs, files in os.walk(install_dir):
            if "pdftoppm.exe" in files:
                if progress:
                    progress(100, "Poppler installed ✓")
                return {"success": True, "path": root}
        return {"success": False, "error": "Extraction OK but pdftoppm.exe not found."}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Language packs ───────────────────────────────────────────────────────


def install_language_pack(
    lang: str,
    tesseract_path: str = "",
    progress: Optional[Callable] = None,
) -> dict[str, Any]:
    """Download a ``.traineddata`` file for *lang* into tessdata."""
    exe = tesseract_path or _find_tesseract()
    if not exe:
        return {"success": False, "error": "Tesseract not found."}
    tessdata = Path(exe).parent / "tessdata"
    if not tessdata.exists():
        return {"success": False, "error": f"tessdata not found at {tessdata}"}
    dest = tessdata / f"{lang}.traineddata"
    if dest.exists():
        return {"success": True, "message": f"{lang} already installed."}
    url = f"{TESSDATA_BEST_BASE}/{lang}.traineddata"
    try:
        if progress:
            progress(10, f"Downloading {lang} language pack…")
        if _download(url, str(dest), progress):
            if progress:
                progress(100, f"{lang} language pack installed ✓")
            return {"success": True, "path": str(dest)}
        return {"success": False, "error": "Download failed."}
    except Exception as e:
        return {"success": False, "error": str(e)}
