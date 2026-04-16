#!/usr/bin/env python3
"""
sync_site.py — Sync teaching resources from mif2e.ephhk.com

Downloads all Questions and Full Solutions files from resource tables
under Assessment Resources, TSA Kit, DSE Kit, and Worksheets nav items,
compares them with a local folder, and optionally replaces outdated files.

EPH_ID is hardcoded below. Password is prompted at runtime via getpass.
"""

import argparse
import asyncio
import getpass
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

# ── Hardcoded credential ────────────────────────────────────────────────────
# EPH_ID used for login. Password is prompted at runtime (never stored).
EPH_ID = "4201t03"
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://mif2e.ephhk.com"
LOGIN_URL = BASE_URL  # login modal is on the homepage

# Nav items to crawl (English type param → Chinese nav label)
TARGET_NAV_ITEMS = {
    "Assessment Resources": "評估資源",
    "TSA Kit": "TSA 資源套",
    "DSE Kit": "DSE 資源套",
    "Worksheets": "工作紙",
}

# File extensions to download
DOWNLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar"}

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ResourceFile:
    """Represents a single downloadable resource discovered on the site."""
    url: str
    book: str = ""
    chapter: str = ""
    section: str = ""
    filename: str = ""
    resource_type: str = ""   # "Questions" / "Full Solutions" / "Other"
    nav_type: str = ""        # e.g. "Assessment Resources"
    page_name: str = ""       # e.g. "360 Assessment"


@dataclass
class ManifestEntry:
    """One entry in the run manifest."""
    url: str
    book: str
    chapter: str
    section: str
    filename: str
    saved_path: str
    sha256_downloaded: str
    sha256_local: Optional[str]
    action: str  # new / updated / skipped / local_only / failed / would_replace
    timestamp: str
    retries: int
    nav_type: str = ""
    page_name: str = ""
    resource_type: str = ""
    error: str = ""


# ── Utility functions ────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove or replace characters illegal in Windows filenames."""
    # Replace illegal chars with underscore
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    # Truncate to 200 chars to stay within Windows limits
    if len(name) > 200:
        stem, ext = os.path.splitext(name)
        name = stem[:200 - len(ext)] + ext
    return name or "unnamed"


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _match_chapter_folder(parent: Path, book: str, chapter: str) -> str:
    """
    Find the existing chapter subfolder that matches *book* + chapter number.

    The website provides Chinese chapter names (e.g. ``"1 基礎計算"``), but the
    local folders use English names (e.g. ``"1A1 Basic Computation"``).
    We match on the prefix ``{book}{chapter_num}`` (e.g. ``"1A1"``) and verify
    that the next character is not a digit (to avoid ``"1A1"`` matching
    ``"1A10 …"``).

    Falls back to ``{book}{chapter}`` when no existing folder matches.
    """
    m = re.match(r'(\d+(?:&\d+)?)', chapter.strip())
    if not m:
        return sanitize_filename(f"{book}{chapter}")

    chapter_num = m.group(1)              # e.g. "1" or "4&7"
    prefix = f"{book}{chapter_num}"       # e.g. "1A1"

    if parent.exists():
        for d in parent.iterdir():
            if not d.is_dir():
                continue
            name = d.name
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix):]
            # Avoid "1A10 …" matching prefix "1A1"
            if rest and rest[0].isdigit():
                continue
            return name

    # No existing match — create with Chinese name
    return sanitize_filename(f"{prefix} {chapter.strip()[len(chapter_num):].strip()}")


def build_local_path(local_root: Path, nav_type: str, page_name: str,
                     book: str, chapter: str, section: str,
                     original_filename: str) -> Path:
    """
    Build the local save path matching the existing folder layout::

        <local-root>/<NavType>/<PageName>/<Book+ChapterNum EnglishName>/filename

    *PageName* comes from the URL parameter and already matches the local
    folder names.  The chapter folder is resolved by scanning existing folders
    for a ``{book}{chapter_number}`` prefix so that Chinese names from the
    website are mapped to English folder names on disk.

    When neither *book* nor *chapter* is present (e.g. Term Exam Paper), files
    are placed directly under ``<NavType>/<PageName>/``.
    """
    nav_dir = sanitize_filename(nav_type) if nav_type else "_NoType"
    page_dir = sanitize_filename(page_name) if page_name else "_NoPage"
    fname = sanitize_filename(original_filename)

    base = local_root / nav_dir / page_dir

    if book and chapter:
        chapter_dir = _match_chapter_folder(base, book, chapter)
        return base / chapter_dir / fname

    # No book/chapter metadata — file goes directly into the page folder
    return base / fname


def resolve_collision(path: Path) -> Path:
    """If path exists, append an index to make it unique."""
    if not path.exists():
        return path
    stem = path.stem
    ext = path.suffix
    parent = path.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}_{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def backup_file(filepath: Path, backup_root: Path, timestamp_str: str) -> Path:
    """Move an existing file to backup/<timestamp>/ preserving relative structure."""
    backup_dir = backup_root / timestamp_str
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / filepath.name
    dest = resolve_collision(dest)
    shutil.copy2(filepath, dest)
    return dest


def compare_and_act(downloaded_path: Path, local_path: Path,
                    backup_root: Path, timestamp_str: str, dry_run: bool,
                    logger: logging.Logger) -> tuple[str, Optional[str]]:
    """
    Compare downloaded file with local file and decide action.
    Returns (action_string, sha256_local_or_None).
    """
    sha_dl = compute_sha256(downloaded_path)

    if not local_path.exists():
        if dry_run:
            return "would_replace", None
        # New file — copy into place
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(downloaded_path, local_path)
        logger.info("NEW: %s", local_path)
        return "new", None

    sha_local = compute_sha256(local_path)
    if sha_dl == sha_local:
        return "skipped", sha_local

    # Files differ
    if dry_run:
        return "would_replace", sha_local

    # Backup old file, then replace
    backup_file(local_path, backup_root, timestamp_str)
    shutil.copy2(downloaded_path, local_path)
    logger.info("UPDATED: %s", local_path)
    return "updated", sha_local


def unzip_and_remove(archive_path: Path, logger: logging.Logger) -> list[Path]:
    """
    If *archive_path* is a .zip file, extract its contents into the same
    directory and delete the archive.  Returns the list of extracted paths.
    Non-.zip files are returned as-is without modification.
    """
    if archive_path.suffix.lower() != ".zip" or not archive_path.exists():
        return [archive_path]

    dest_dir = archive_path.parent
    extracted: list[Path] = []
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            # Security: reject entries with absolute paths or path traversal
            for info in zf.infolist():
                if info.filename.startswith("/") or ".." in info.filename:
                    logger.warning(
                        "Skipping suspicious zip entry: %s in %s",
                        info.filename, archive_path,
                    )
                    continue
                if info.is_dir():
                    continue
                target = dest_dir / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(target)
        archive_path.unlink()
        logger.info("UNZIPPED: %s → %d file(s)", archive_path.name, len(extracted))
    except zipfile.BadZipFile:
        logger.warning("Not a valid zip file: %s — keeping as-is", archive_path)
        return [archive_path]
    return extracted


# ── Scraping helpers ─────────────────────────────────────────────────────────

async def login(page: Page, eph_id: str, password: str, logger: logging.Logger) -> bool:
    """
    Log in via the top-right Login control. Returns True on success.

    Site behaviour (discovered via live inspection):
      • Homepage has a hidden modal (#login.modal) with form #top_login_form
        containing #username, #password, #btn-login.
      • There is also a visible div #mobile-login-btn ("登入Login") which,
        when clicked, **navigates** to /index.php/teacher/login — a separate
        login page with its own form (#form) containing input.account,
        input.password, and input.mobile-login[type="submit"].
      • We prefer the direct login page because it reliably renders visible
        input fields.
    """
    # ── Strategy 1: Navigate directly to the login page ──────────────────
    login_page_url = BASE_URL + "/index.php/teacher/login"
    logger.info("Navigating directly to login page: %s", login_page_url)
    try:
        await page.goto(login_page_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        logger.warning("Login page load timed out — continuing with partial page")

    # Check for CAPTCHA before attempting login
    page_html = await page.content()
    if any(kw in page_html.lower() for kw in ["captcha", "驗證碼"]):
        logger.error(
            "CAPTCHA detected on login page! Please log in manually in a "
            "browser first, then re-run with --debug --no-headless."
        )
        return False

    # ── Fill EPH ID ──────────────────────────────────────────────────────
    # The login page form uses input.account[name="username"] (visible).
    # The hidden modal also has #username.  We try visible-first selectors.
    id_filled = False
    for id_sel in [
        'input.account[name="username"]',      # login page form
        '#form input[name="username"]',         # login page form by parent
        '#username',                            # modal form
        'input[name="username"]:visible',       # any visible username field
        'input[type="text"]:visible',           # last resort
    ]:
        try:
            el = page.locator(id_sel).first
            if await el.is_visible(timeout=3000):
                await el.fill(eph_id)
                id_filled = True
                logger.info("Filled EPH ID via: %s", id_sel)
                break
        except Exception:
            continue

    if not id_filled:
        logger.error("Could not find EPH ID input field")
        return False

    # ── Fill password ────────────────────────────────────────────────────
    pw_filled = False
    for pw_sel in [
        'input.password[name="password"]',      # login page form
        '#form input[name="password"]',         # login page form by parent
        '#password',                            # modal form
        'input[type="password"]:visible',       # any visible password field
    ]:
        try:
            el = page.locator(pw_sel).first
            if await el.is_visible(timeout=3000):
                await el.fill(password)
                pw_filled = True
                logger.info("Filled password via: %s", pw_sel)
                break
        except Exception:
            continue

    if not pw_filled:
        logger.error("Could not find password input field")
        return False

    # ── Submit ───────────────────────────────────────────────────────────
    submitted = False
    for sub_sel in [
        'input.mobile-login[type="submit"]',    # login page submit
        '#form input[type="submit"]',           # login page by parent
        '#btn-login',                           # modal submit button
        'button[type="submit"]',                # generic
        'input[type="submit"]',                 # generic
    ]:
        try:
            el = page.locator(sub_sel).first
            if await el.is_visible(timeout=2000):
                try:
                    async with page.expect_navigation(timeout=15000):
                        await el.click()
                except PlaywrightTimeout:
                    pass  # form may not trigger full navigation
                submitted = True
                logger.info("Submitted login via: %s", sub_sel)
                break
        except Exception:
            continue

    if not submitted:
        # Fallback: press Enter in the password field
        await page.keyboard.press("Enter")
        logger.info("Submitted login via Enter key")

    # ── Wait for post-login navigation ───────────────────────────────────
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        pass

    # Check for CAPTCHA on the result page
    page_html = await page.content()
    if any(kw in page_html.lower() for kw in ["captcha", "驗證碼"]):
        logger.error("CAPTCHA detected after login attempt! Please log in manually and retry.")
        return False

    # Check for login error messages from the site
    try:
        err_msg = await page.locator("#login_error_message, .login_error_message, .message .error").first.inner_text()
        if err_msg.strip():
            logger.error("Login error from site: %s", err_msg.strip())
            return False
    except Exception:
        pass

    # ── Verify login success ─────────────────────────────────────────────
    current_url = page.url
    body_text = await page.inner_text("body")

    # Check for logged-in indicators
    if any(kw in body_text for kw in ["Welcome", "歡迎", "登出", "Logout"]):
        logger.info("Login successful — detected logged-in indicator in page text.")
        return True

    # If we're redirected away from the login page, likely success
    if "/login" not in current_url:
        logger.info("Login appears successful — redirected to: %s", current_url)
        return True

    # If we're still on the login page, it likely failed
    if "/login" in current_url:
        logger.error(
            "Login may have failed — still on login page. "
            "Check credentials or use --debug --no-headless to inspect."
        )
        return False

    logger.warning("Could not confirm login success — proceeding cautiously")
    return True


async def discover_subpages(page: Page, logger: logging.Logger) -> list[dict]:
    """
    Discover all subpage links under the target nav items.
    Returns list of {type, page_name, url}.
    """
    subpages = []

    # Strategy 1: Extract links from the dropdown menus in the DOM
    logger.info("Discovering subpages from navigation menus...")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_load_state("networkidle", timeout=15000)

    # Try to find all links that match the teacher/detail pattern
    links = await page.evaluate("""() => {
        const results = [];
        const anchors = document.querySelectorAll('a[href]');
        for (const a of anchors) {
            const href = a.getAttribute('href') || '';
            if (href.includes('/teacher/detail') || href.includes('/teacher/inner')) {
                results.push({
                    href: href,
                    text: (a.textContent || '').trim(),
                });
            }
        }
        return results;
    }""")

    seen = set()
    for link in links:
        href = link["href"]
        if not href.startswith("http"):
            href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href

        # Parse type and page from URL
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        nav_type = params.get("type", [""])[0]
        page_name = params.get("page", [""])[0]

        if nav_type in TARGET_NAV_ITEMS and page_name:
            key = (nav_type, page_name)
            if key not in seen:
                seen.add(key)
                subpages.append({
                    "type": nav_type,
                    "page_name": page_name,
                    "url": href,
                })

    # Strategy 2: Hover over menu items to reveal dropdowns
    if not subpages:
        logger.info("No links found statically; trying hover menus...")
        for eng_type, chi_label in TARGET_NAV_ITEMS.items():
            for sel in [f"text={chi_label}", f"a:has-text('{chi_label}')",
                        f"text={eng_type}", f"a:has-text('{eng_type}')"]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.hover()
                        await page.wait_for_timeout(800)
                        # Now grab any newly visible dropdown links
                        dropdown_links = await page.evaluate("""(parentText) => {
                            const results = [];
                            const allLinks = document.querySelectorAll('a[href]');
                            for (const a of allLinks) {
                                const href = a.getAttribute('href') || '';
                                if (href.includes('/teacher/detail')) {
                                    const rect = a.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) {
                                        results.push({
                                            href: href,
                                            text: (a.textContent || '').trim(),
                                        });
                                    }
                                }
                            }
                            return results;
                        }""", chi_label)

                        for dl in dropdown_links:
                            href = dl["href"]
                            if not href.startswith("http"):
                                href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href
                            parsed = urllib.parse.urlparse(href)
                            params = urllib.parse.parse_qs(parsed.query)
                            nav_t = params.get("type", [""])[0]
                            page_n = params.get("page", [""])[0]
                            if nav_t == eng_type and page_n:
                                key = (nav_t, page_n)
                                if key not in seen:
                                    seen.add(key)
                                    subpages.append({
                                        "type": nav_t,
                                        "page_name": page_n,
                                        "url": href,
                                    })
                        break
                except Exception:
                    continue

    # Strategy 3: Try known URL pattern with JS-based menu parsing
    if not subpages:
        logger.info("Trying JS-based menu extraction...")
        all_nav_links = await page.evaluate("""() => {
            const results = [];
            // Look in nav / header containers for nested menus
            const containers = document.querySelectorAll('nav, header, .navbar, .menu, .nav');
            for (const container of containers) {
                const links = container.querySelectorAll('a[href]');
                for (const a of links) {
                    results.push({
                        href: a.getAttribute('href') || '',
                        text: (a.textContent || '').trim(),
                        parent_text: (a.parentElement?.closest('li, div')?.querySelector(':scope > a, :scope > span')?.textContent || '').trim(),
                    });
                }
            }
            return results;
        }""")

        for link in all_nav_links:
            href = link["href"]
            if "/teacher/detail" in href or "/teacher/inner" in href:
                if not href.startswith("http"):
                    href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href
                parsed = urllib.parse.urlparse(href)
                params = urllib.parse.parse_qs(parsed.query)
                nav_type = params.get("type", [""])[0]
                page_name = params.get("page", [""])[0]
                if nav_type in TARGET_NAV_ITEMS and page_name:
                    key = (nav_type, page_name)
                    if key not in seen:
                        seen.add(key)
                        subpages.append({
                            "type": nav_type,
                            "page_name": page_name,
                            "url": href,
                        })

    logger.info("Discovered %d subpages across targeted nav items", len(subpages))
    for sp in subpages:
        logger.debug("  [%s] %s → %s", sp["type"], sp["page_name"], sp["url"])

    return subpages


async def scrape_resource_page(page: Page, subpage: dict,
                                logger: logging.Logger) -> list[ResourceFile]:
    """
    Visit a subpage and extract all downloadable resource links.

    The EPH site uses ``<div class="download" data-url="…">下載</div>``
    inside ``<table>`` rows.  Each ``<td>`` self-identifies via a child
    ``<div class="label">`` (冊次/章/分節/題目/詳解).
    """
    url = subpage["url"]
    nav_type = subpage["type"]
    page_name = subpage["page_name"]
    resources: list[ResourceFile] = []
    seen_urls: set[str] = set()

    logger.info("Scraping: [%s] %s", nav_type, page_name)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        logger.warning("Timeout loading %s — attempting to scrape partial content", url)
    except Exception as e:
        logger.error("Failed to load %s: %s", url, e)
        return resources

    # Strategy 1: Parse div.download[data-url] elements inside table rows.
    # Each data cell has:
    #   <td><div class="label">題目</div>
    #       <div class="download" data-url="cms_upload/…">下載</div></td>
    table_resources = await page.evaluate("""() => {
        const results = [];
        const rows = document.querySelectorAll('table tr');

        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length === 0) continue;

            let book = '', chapter = '', section = '';

            // First pass: extract metadata from non-download cells
            for (const cell of cells) {
                const labelDiv = cell.querySelector('div.label');
                const label = labelDiv ? labelDiv.textContent.trim() : '';
                if (!cell.querySelector('div.download[data-url]')) {
                    const valueDiv = cell.querySelector('div:not(.label)');
                    const value = valueDiv
                        ? valueDiv.textContent.trim()
                        : cell.textContent.trim();
                    if (label.includes('冊') || label.toLowerCase().includes('book'))
                        book = value;
                    else if (label.includes('章') || label.toLowerCase().includes('chapter'))
                        chapter = value;
                    else if (label.includes('節') || label.toLowerCase().includes('section'))
                        section = value;
                }
            }

            // Second pass: collect download divs
            for (const cell of cells) {
                const labelDiv = cell.querySelector('div.label');
                const label = labelDiv ? labelDiv.textContent.trim() : '';
                const dlDiv = cell.querySelector('div.download[data-url]');
                if (dlDiv) {
                    const dataUrl = dlDiv.getAttribute('data-url') || '';
                    if (!dataUrl) continue;
                    let resType = 'Other';
                    if (label.includes('題目') || label.toLowerCase().includes('question'))
                        resType = 'Questions';
                    else if (label.includes('詳解') || label.includes('答案')
                             || label.toLowerCase().includes('solution'))
                        resType = 'Full Solutions';
                    results.push({
                        data_url: dataUrl,
                        book: book,
                        chapter: chapter,
                        section: section,
                        resource_type: resType,
                    });
                }
            }
        }
        return results;
    }""")

    for item in table_resources:
        data_url = item["data_url"]
        # Build absolute URL from relative data-url
        if data_url.startswith("http"):
            href = data_url
        elif data_url.startswith("/"):
            href = BASE_URL + data_url
        else:
            href = BASE_URL + "/" + data_url

        if href in seen_urls:
            continue
        seen_urls.add(href)

        filename = _extract_filename_from_url(href, "")
        resources.append(ResourceFile(
            url=href,
            book=item.get("book", ""),
            chapter=item.get("chapter", ""),
            section=item.get("section", ""),
            filename=filename,
            resource_type=item.get("resource_type", "Other"),
            nav_type=nav_type,
            page_name=page_name,
        ))

    # Strategy 2: Fallback — find div.download[data-url] anywhere on the page
    if not resources:
        logger.info("No table download elements found; scanning entire page…")
        all_downloads = await page.evaluate("""() => {
            return [...document.querySelectorAll('div.download[data-url]')].map(el => ({
                data_url: el.getAttribute('data-url') || '',
            }));
        }""")
        for item in all_downloads:
            data_url = item["data_url"]
            if not data_url:
                continue
            if data_url.startswith("http"):
                href = data_url
            elif data_url.startswith("/"):
                href = BASE_URL + data_url
            else:
                href = BASE_URL + "/" + data_url
            if href in seen_urls:
                continue
            seen_urls.add(href)
            filename = _extract_filename_from_url(href, "")
            resources.append(ResourceFile(
                url=href,
                filename=filename,
                resource_type="Other",
                nav_type=nav_type,
                page_name=page_name,
            ))

    # Strategy 3: Fallback — find classic <a href> download links
    if not resources:
        logger.info("No download elements found; scanning <a> links…")
        all_links = await page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.textContent || '').trim(),
            }));
        }""")
        for link in all_links:
            href = link["href"]
            if not href.startswith("http"):
                href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href
            if href in seen_urls:
                continue
            parsed_path = urllib.parse.urlparse(href).path.lower()
            ext = os.path.splitext(parsed_path)[1]
            if ext in DOWNLOAD_EXTENSIONS or "download" in href.lower():
                seen_urls.add(href)
                filename = _extract_filename_from_url(href, link.get("text", ""))
                resources.append(ResourceFile(
                    url=href,
                    filename=filename,
                    resource_type="Other",
                    nav_type=nav_type,
                    page_name=page_name,
                ))

    logger.info("Found %d downloadable resources on [%s] %s", len(resources), nav_type, page_name)
    return resources


def _extract_filename_from_url(url: str, link_text: str) -> str:
    """Extract a reasonable filename from a URL or link text."""
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path)
    basename = os.path.basename(path)
    if basename and os.path.splitext(basename)[1]:
        return basename
    # Fallback: use link text
    if link_text:
        return sanitize_filename(link_text)
    return "download"


# ── Download logic ───────────────────────────────────────────────────────────

async def download_file(context: BrowserContext, resource: ResourceFile,
                        download_dir: Path, logger: logging.Logger) -> tuple[Optional[Path], int]:
    """
    Download a single file using a new page in the browser context.
    Returns (local_path_or_None, retry_count).

    The EPH site serves files as direct downloads (Content-Disposition),
    so ``page.goto()`` triggers a download event rather than loading a page.
    We handle this in two ways:

    1. **Primary**: wrap ``goto`` inside ``expect_download`` — Playwright
       captures the download even though ``goto`` raises "Download is starting".
    2. **Fallback**: use ``context.request`` (API-level HTTP, no browser tab)
       to fetch the raw bytes directly.
    """
    retries = 0
    last_error = None

    while retries <= MAX_RETRIES:
        if retries > 0:
            delay = RETRY_BASE_DELAY ** retries
            logger.info("Retry %d/%d for %s (waiting %.1fs)", retries, MAX_RETRIES, resource.url, delay)
            await asyncio.sleep(delay)

        # ── Attempt A: Playwright download event ─────────────────────────
        page = None
        try:
            page = await context.new_page()
            async with page.expect_download(timeout=60000) as download_info:
                try:
                    await page.goto(resource.url, wait_until="commit", timeout=30000)
                except Exception:
                    # "Download is starting" is expected — goto throws but
                    # expect_download still captures the download object.
                    pass

            download = download_info.value
            suggested = download.suggested_filename
            if suggested:
                resource.filename = suggested

            save_path = download_dir / sanitize_filename(resource.filename or "download")
            save_path = resolve_collision(save_path)
            await download.save_as(str(save_path))

            if save_path.exists() and save_path.stat().st_size > 0:
                return save_path, retries

        except PlaywrightTimeout:
            last_error = "Download timeout"
            logger.warning("Timeout downloading %s (attempt %d)", resource.url, retries + 1)
        except Exception as e:
            last_error = str(e)
            logger.debug("Primary download failed for %s: %s", resource.url, e)
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

        # ── Attempt B: API-level fetch (no browser tab) ──────────────────
        try:
            api_resp = await context.request.get(resource.url, timeout=60000)
            if api_resp.ok:
                body = await api_resp.body()
                if body and len(body) > 0:
                    # Try to get filename from content-disposition header
                    cd = api_resp.headers.get("content-disposition", "")
                    if "filename" in cd:
                        match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', cd)
                        if match:
                            resource.filename = urllib.parse.unquote(match.group(1).strip())

                    save_path = download_dir / sanitize_filename(resource.filename or "download")
                    save_path = resolve_collision(save_path)
                    save_path.write_bytes(body)
                    if save_path.stat().st_size > 0:
                        return save_path, retries
            else:
                last_error = f"HTTP {api_resp.status}"
                logger.warning("API fetch failed for %s: HTTP %d", resource.url, api_resp.status)
        except Exception as e2:
            last_error = str(e2)
            logger.warning("API fetch failed for %s: %s", resource.url, e2)

        retries += 1

    logger.error("Failed to download %s after %d retries: %s", resource.url, MAX_RETRIES, last_error)
    return None, retries


# ── Main orchestration ───────────────────────────────────────────────────────

async def run_sync(args: argparse.Namespace, password: str, logger: logging.Logger) -> list[ManifestEntry]:
    """Main sync workflow."""
    local_folder = Path(args.local_folder).resolve()
    download_dir = Path(args.download_dir).resolve() if args.download_dir else Path(tempfile.mkdtemp(prefix="sync_dl_"))
    backup_root = local_folder / "backup"
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest: list[ManifestEntry] = []
    concurrency = args.concurrency or 3

    download_dir.mkdir(parents=True, exist_ok=True)
    local_folder.mkdir(parents=True, exist_ok=True)

    logger.info("Local folder: %s", local_folder)
    logger.info("Download dir: %s", download_dir)
    logger.info("Mode: %s", "DRY-RUN" if args.dry_run else "APPLY")
    logger.info("Concurrency: %d", concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
        )
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )

        page = await context.new_page()

        # Step 1: Login
        logger.info("=== Step 1: Login ===")
        logged_in = await login(page, EPH_ID, password, logger)
        if not logged_in:
            logger.error("Login failed. Aborting.")
            await browser.close()
            return manifest

        # Step 2: Discover subpages
        logger.info("=== Step 2: Discover subpages ===")
        subpages = await discover_subpages(page, logger)

        if not subpages:
            logger.warning("No subpages discovered. The site structure may have changed, "
                          "or login may not have succeeded. Check --debug mode.")
            await browser.close()
            return manifest

        # Step 3: Scrape resources from each subpage
        logger.info("=== Step 3: Scrape resources ===")
        all_resources: list[ResourceFile] = []
        for sp in subpages:
            try:
                page_resources = await scrape_resource_page(page, sp, logger)
                all_resources.extend(page_resources)
            except Exception as e:
                logger.error("Error scraping %s: %s", sp["url"], e)

        logger.info("Total resources found: %d", len(all_resources))

        if not all_resources:
            logger.warning("No downloadable resources found.")
            await browser.close()
            return manifest

        # Step 4: Download and compare
        logger.info("=== Step 4: Download and compare ===")
        sem = asyncio.Semaphore(concurrency)

        async def process_resource(res: ResourceFile) -> ManifestEntry:
            async with sem:
                now = datetime.now(timezone.utc).isoformat()
                try:
                    dl_path, retries = await download_file(context, res, download_dir, logger)

                    if dl_path is None:
                        return ManifestEntry(
                            url=res.url, book=res.book, chapter=res.chapter,
                            section=res.section, filename=res.filename,
                            saved_path="", sha256_downloaded="",
                            sha256_local=None, action="failed",
                            timestamp=now, retries=retries,
                            nav_type=res.nav_type, page_name=res.page_name,
                            resource_type=res.resource_type,
                            error="Download failed after retries",
                        )

                    sha_dl = compute_sha256(dl_path)
                    local_path = build_local_path(
                        local_folder, res.nav_type, res.page_name,
                        res.book, res.chapter, res.section,
                        res.filename,
                    )

                    action, sha_local = compare_and_act(
                        dl_path, local_path,
                        backup_root, timestamp_str, args.dry_run, logger,
                    )

                    # Auto-extract .zip files after placing them
                    if not args.dry_run and action in ("new", "updated"):
                        extracted = unzip_and_remove(local_path, logger)
                        if extracted and extracted != [local_path]:
                            # Update saved_path to the extraction directory
                            local_path = extracted[0].parent

                    return ManifestEntry(
                        url=res.url, book=res.book, chapter=res.chapter,
                        section=res.section, filename=res.filename,
                        saved_path=str(local_path), sha256_downloaded=sha_dl,
                        sha256_local=sha_local, action=action,
                        timestamp=now, retries=retries,
                        nav_type=res.nav_type, page_name=res.page_name,
                        resource_type=res.resource_type,
                    )
                except Exception as e:
                    logger.error("Error processing %s: %s", res.url, e)
                    return ManifestEntry(
                        url=res.url, book=res.book, chapter=res.chapter,
                        section=res.section, filename=res.filename,
                        saved_path="", sha256_downloaded="",
                        sha256_local=None, action="failed",
                        timestamp=now, retries=0,
                        nav_type=res.nav_type, page_name=res.page_name,
                        resource_type=res.resource_type,
                        error=str(e),
                    )

        tasks = [process_resource(r) for r in all_resources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, ManifestEntry):
                manifest.append(r)
            elif isinstance(r, Exception):
                logger.error("Task exception: %s", r)

        await browser.close()

    # Step 5: Scan local-only files (present locally but not on site)
    if local_folder.exists():
        downloaded_local_paths = {Path(m.saved_path).resolve() for m in manifest if m.saved_path}
        for local_file in local_folder.rglob("*"):
            if local_file.is_file() and local_file.resolve() not in downloaded_local_paths:
                rel = local_file.relative_to(local_folder)
                # Skip backup directory and manifest files
                if str(rel).startswith("backup") or local_file.suffix == ".json":
                    continue
                ext = local_file.suffix.lower()
                if ext in DOWNLOAD_EXTENSIONS:
                    manifest.append(ManifestEntry(
                        url="", book="", chapter="", section="",
                        filename=local_file.name,
                        saved_path=str(local_file),
                        sha256_downloaded="",
                        sha256_local=compute_sha256(local_file),
                        action="local_only",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        retries=0,
                    ))

    # Summary
    actions = {}
    for m in manifest:
        actions[m.action] = actions.get(m.action, 0) + 1
    logger.info("=== Summary ===")
    for action, count in sorted(actions.items()):
        logger.info("  %s: %d", action, count)

    return manifest


def setup_logging(log_path: Optional[str], debug: bool) -> logging.Logger:
    """Configure logging to file and console."""
    logger = logging.getLogger("sync_site")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if debug else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    if log_path:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync teaching resources from mif2e.ephhk.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_site.py --dry-run
  python sync_site.py --apply --concurrency 5
  python sync_site.py --local-folder "D:\\Other\\Path" --apply
  python sync_site.py --debug --no-headless
        """,
    )
    parser.add_argument("--local-folder",
                        default=r"T:\Subject\math\Question Banks\教育出版社\Junior\Maths in Focus",
                        help="Path to local folder for comparison/replacement "
                             r"(default: T:\Subject\math\Question Banks\教育出版社\Junior\Maths in Focus)")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True,
                        help="Run browser in headless mode (default)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Run browser with visible UI")
    parser.add_argument("--download-dir", default=None,
                        help="Temporary download directory (default: auto temp dir)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                        help="Report actions without making changes (default)")
    parser.add_argument("--apply", dest="dry_run", action="store_false",
                        help="Actually replace/update files")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="Number of parallel downloads (default: 3)")
    parser.add_argument("--manifest", default=None,
                        help="Output manifest JSON path (default: manifest_<timestamp>.json)")
    parser.add_argument("--log", default="sync.log",
                        help="Log file path (default: sync.log)")
    parser.add_argument("--debug", action="store_true", default=False,
                        help="Debug mode: non-headless, verbose logging, pause on errors")
    return parser.parse_args()


def main():
    args = parse_args()

    # Debug mode overrides
    if args.debug:
        args.headless = False

    logger = setup_logging(args.log, args.debug)

    # Prompt for password at runtime — never stored or logged
    password = getpass.getpass(prompt="Enter EPH password (密碼): ")
    if not password:
        logger.error("Password is required.")
        sys.exit(1)

    logger.info("Starting sync_site with EPH_ID=%s", EPH_ID)

    manifest = asyncio.run(run_sync(args, password, logger))

    # Write manifest
    manifest_path = args.manifest or f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    manifest_data = [asdict(m) for m in manifest]
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    logger.info("Manifest written to %s (%d entries)", manifest_path, len(manifest_data))

    # Exit code: 0 if no failures
    failed = sum(1 for m in manifest if m.action == "failed")
    if failed:
        logger.warning("%d files failed to process", failed)
        sys.exit(2)

    logger.info("Done.")


if __name__ == "__main__":
    main()
