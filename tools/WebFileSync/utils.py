"""Shared utilities: timestamp parsing, hashing, logging setup."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional


logger = logging.getLogger("webfilesync")


def setup_logging(
    verbose: bool = False,
    debug: bool = False,
    log_to_file: bool = False,
    log_file: str = "webfilesync.log",
) -> None:
    """Configure the root logger for the application."""
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_to_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

_COMMON_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",       # RFC 2822 / HTTP-date
    "%A, %d-%b-%y %H:%M:%S %Z",        # RFC 850
    "%a %b %d %H:%M:%S %Y",            # asctime()
    "%Y-%m-%dT%H:%M:%S%z",             # ISO 8601 with tz
    "%Y-%m-%dT%H:%M:%SZ",              # ISO 8601 UTC
    "%Y-%m-%d %H:%M:%S",               # common fallback
    "%d/%b/%Y %H:%M:%S",               # Apache-style
    "%d-%b-%Y %H:%M:%S",               # variation
    "%Y-%m-%d %H:%M",                  # minute precision
    "%d %b %Y %H:%M",                  # "26 Mar 2026 12:00"
]

# Timezone abbreviations that email.utils may not handle
_TZ_MAP = {
    "EST": "-0500", "EDT": "-0400",
    "CST": "-0600", "CDT": "-0500",
    "MST": "-0700", "MDT": "-0600",
    "PST": "-0800", "PDT": "-0700",
    "CET": "+0100", "CEST": "+0200",
    "JST": "+0900", "KST": "+0900",
    "IST": "+0530", "AEST": "+1000",
    "NZST": "+1200",
}


def parse_http_date(date_str: str) -> Optional[datetime]:
    """Parse a date string from HTTP headers into a timezone-aware UTC datetime.

    Tries email.utils first (covers RFC 2822), then a battery of common formats.
    Always returns UTC or None.
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # 1. Try email.utils (handles most HTTP-date formats)
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, IndexError):
        pass

    # 2. Replace known timezone abbreviations with numeric offsets
    cleaned = date_str
    for abbr, offset in _TZ_MAP.items():
        cleaned = re.sub(rf"\b{abbr}\b", offset, cleaned)

    # 3. Try common formats
    for fmt in _COMMON_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    # 4. Last resort: try dateutil if available
    try:
        from dateutil import parser as du_parser  # type: ignore[import-untyped]
        dt = du_parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    logger.warning("Could not parse date: %s", date_str)
    return None


def normalize_to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is in UTC. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_file_mtime_utc(path: Path) -> Optional[datetime]:
    """Return the local file's modification time as UTC datetime, or None."""
    if not path.exists():
        return None
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of in-memory bytes."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_size(n: Optional[int]) -> str:
    """Human-friendly file size string."""
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0  # type: ignore[assignment]
    return f"{n:.1f} PB"


def fmt_dt(dt: Optional[datetime]) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
