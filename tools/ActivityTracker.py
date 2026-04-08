#!/usr/bin/env python3
"""
Activity Tracker
================
Tracks monitor-on time, keystroke count, and AFK time.
Runs silently in the system tray and auto-starts with Windows.

Data is saved daily to:
    %APPDATA%\\ActivityTracker\\stats_YYYY-MM-DD.json

Auto-installs required packages on first run:
    pynput  pystray  Pillow

To run without a console window, launch with pythonw.exe instead of python.exe.
"""

from __future__ import annotations

import ctypes     # Talks to Windows system APIs: create transparent windows, show message boxes
import json       # Reads and writes JSON (.json) data files — our saved stats format
import os         # Reads environment variables like APPDATA (where data files are stored)
import sys        # Controls the Python interpreter itself (e.g. sys.exit to quit the program)
import threading  # Allows multiple tasks to run at the same time in the background
import time       # sleep() pauses the loop; monotonic() gives a reliable timer for measuring intervals
import tkinter as tk        # Python's built-in GUI toolkit — powers the overlay window
import tkinter.ttk as ttk   # Themed Tkinter widgets — used for the analytics tab bar
import winreg     # Reads and writes the Windows Registry — used for the auto-start feature
import math       # Mathematical functions (used in chart layout calculations)
from datetime import date, datetime  # date = calendar date (2026-03-25); datetime = date + time of day
from pathlib import Path             # A modern, readable way to work with file and folder paths
from types import SimpleNamespace    # Creates a simple container with named fields (e.g. st.keystrokes)


# ─── Auto-install dependencies ────────────────────────────────────────────────
# This function checks whether all required third-party libraries are installed.
# If any are missing, it automatically downloads and installs them using pip
# (Python's built-in package manager). The script is therefore self-contained:
# just run it once and it will set itself up on first launch.

def _ensure_deps() -> None:
    # These two built-in modules let us check what's installed and run commands.
    import importlib.util
    import subprocess

    # APP_LABEL isn't defined yet this early in the script, so we use a plain
    # string here as the title for any pop-up windows.
    _LABEL  = "Activity Tracker"

    # Save a shortcut to the Windows pop-up function so we don't have to retype
    # the long path (ctypes.windll.user32.MessageBoxW) every single time.
    _msgbox = ctypes.windll.user32.MessageBoxW

    # Standard Windows codes that control how a pop-up looks and behaves.
    # Combining them with | (the "OR" operator) mixes their effects together.
    MB_OK           = 0x00   # Show just an OK button
    MB_YESNO        = 0x04   # Show a Yes button and a No button
    MB_ICONERROR    = 0x10   # Show a red X icon (something went wrong)
    MB_ICONQUESTION = 0x20   # Show a question-mark icon (asking for input)
    MB_ICONINFO     = 0x40   # Show a blue information icon (good news)

    # The value Windows returns when the user clicks the "Yes" button.
    IDYES = 6

    # The full list of packages (add-on libraries) this script needs to run.
    # Each entry is two names: the pip install name, and the Python import name.
    # They sometimes differ — e.g. pip calls it "Pillow" but Python calls it "PIL".
    deps = [
        ("pynput",      "pynput"),    # reads keyboard & mouse input
        ("pystray",     "pystray"),   # creates the system-tray icon
        ("Pillow",      "PIL"),       # draws the tray icon image
        ("matplotlib",  "matplotlib"),# draws the analytics charts
        ("pywin32",     "win32gui"),  # talks to Windows APIs
        ("psutil",      "psutil"),    # reads which app is in focus
    ]

    # Go through every package and collect the ones that aren't installed yet.
    # find_spec returns None when a package is missing from this computer.
    missing = [pkg for pkg, imp in deps if importlib.util.find_spec(imp) is None]

    # If every package is already present, leave the function immediately.
    if not missing:
        return

    # Build a bullet-point list of the missing packages for the pop-up message.
    # \u2022 is the Unicode code for a bullet point •
    pkg_list = "\n".join(f"  \u2022 {pkg}" for pkg in missing)

    # Show a Yes / No pop-up asking for the user's permission before installing.
    resp = _msgbox(
        None,
        f"Activity Tracker needs to install the following packages:\n\n{pkg_list}\n\nInstall now?",
        _LABEL,
        MB_YESNO | MB_ICONQUESTION,
    )

    # If the user clicked No (or closed the dialog), show a message and quit.
    if resp != IDYES:
        _msgbox(None, "Required packages were not installed. Exiting.", _LABEL, MB_OK | MB_ICONERROR)
        sys.exit(1)  # sys.exit(1) means "stop the script with an error code"

    # Install all missing packages in one single pip command — faster than
    # running pip once per package.
    # "--user"  → installs for this user only, no administrator rights needed.
    # "--quiet" → hides the noisy download progress lines.
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet"] + missing
        )
    except subprocess.CalledProcessError as e:
        # CalledProcessError means pip ran but reported a failure.
        # e.returncode tells us the numeric error code pip gave back.
        _msgbox(
            None,
            f"Installation failed (exit code {e.returncode}).\nTry running as administrator.",
            _LABEL,
            MB_ICONERROR,
        )
        sys.exit(1)

    # Everything installed successfully — let the user know before the app loads.
    _msgbox(None, "All dependencies installed successfully.", _LABEL, MB_ICONINFO)

_ensure_deps()

from pynput import keyboard, mouse
import pystray
from PIL import Image, ImageDraw


# ─── Configuration ────────────────────────────────────────────────────────────

AFK_THRESHOLD = 5 * 60   # Mark user as AFK after 5 minutes of no keyboard/mouse input
SAVE_INTERVAL = 60        # Save data to disk every 60 seconds (protects against crashes)
SLEEP_DETECT  = 8         # If the loop skips >8 seconds, assume the PC was asleep/hibernated

# Show a "nearly there" countdown on the overlay when approaching end-of-day.
# For example, at 17:01 the overlay will show "Nearly there! (29:00 to go)"
NEAR_TARGET_HOUR = 17     # Target hour in 24-hour format — change to suit your schedule
NEAR_TARGET_MIN  = 30     # Target minute
NEAR_BEFORE_MINUTES = 30  # How many minutes before target to start showing the message

APP_NAME  = "ActivityTracker"
APP_LABEL = "Activity Tracker"

DATA_DIR = Path(os.environ.get("APPDATA", ".")) / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── Mutable state (all access through _lock) ─────────────────────────────────
# All live tracking data is stored here and shared between threads.
# _lock is a "mutex" — it prevents two threads from reading/writing the same
# data simultaneously, which would otherwise cause corrupted or incorrect values.
_lock = threading.Lock()

# 'st' (short for 'state') holds ALL running statistics for the current session.
# Fields labelled "Persisted" are saved to and loaded from disk (they survive restarts).
# Fields labelled "Runtime-only" are reset each time the program starts.
st = SimpleNamespace(
    # Persisted: loaded from today's JSON file at startup, saved periodically
    keystrokes     = 0,      # total key presses today
    afk_secs       = 0.0,    # committed AFK seconds (does not include ongoing AFK)
    saved_monitor  = 0.0,    # monitor-on seconds from earlier sessions today

    # Runtime-only: reset each process start
    session_awake  = 0.0,    # awake seconds accumulated this session
    is_afk         = False,  # currently AFK?
    afk_t0         = 0.0,    # monotonic time when current AFK began
    last_input     = time.monotonic(),  # monotonic time of last keyboard/mouse event

    running        = True,   # set False to shut down threads
    hourly_active  = {},      # {hour_int: active_seconds} for today
    app_keystrokes = {},      # {"AppName.exe": count} for today
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _today() -> str:
    # Returns today's date as a plain string, like "2026-03-25".
    # Used as a label in saved JSON files and in message boxes.
    return str(date.today())


def _data_file(day: str | None = None) -> Path:
    # Builds the full path to the JSON stats file for a given day.
    # If no day is supplied, it uses today's date automatically.
    # Example result: C:\Users\You\AppData\Roaming\ActivityTracker\stats_2026-03-25.json
    return DATA_DIR / f"stats_{day or _today()}.json"


def _fmt_time(seconds: float) -> str:
    """Convert a raw number of seconds into a readable HH:MM:SS clock string.

    For example, 3723 seconds becomes "01:02:03" (1 hour, 2 minutes, 3 seconds).
    max(0.0, seconds) prevents negative numbers from appearing due to rounding.
    :02d means "print as a 2-digit number, padding with a leading zero if needed".
    """
    s = int(max(0.0, seconds))
    # s // 3600  → number of complete hours (integer division, drops the remainder)
    # s % 3600   → leftover seconds after removing whole hours
    # ÷ 60       → convert those leftover seconds into minutes
    # s % 60     → leftover seconds after removing whole minutes
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _secs_to_target() -> float:
    """Return seconds until today's target time (NEAR_TARGET_HOUR:NEAR_TARGET_MIN).
    Returns -1 if the target time has passed for today.
    """
    now = datetime.now()  # Get the current date and time as a single object
    try:
        # Create a new datetime that is the same day as today, but at the target time.
        # For example: if NEAR_TARGET_HOUR=17 and NEAR_TARGET_MIN=30, this becomes today at 17:30:00.
        target = now.replace(hour=NEAR_TARGET_HOUR, minute=NEAR_TARGET_MIN,
                             second=0, microsecond=0)
    except Exception:
        return -1  # Invalid hour/minute values in the config — silently give up
    # Subtracting two datetimes gives a timedelta; .total_seconds() converts it to a plain number.
    delta = (target - now).total_seconds()
    if delta <= 0:
        return -1  # Target time has already passed today — no countdown needed
    return delta


def _get_foreground_app() -> str:
    """Return the exe name of the currently focused window (e.g. 'chrome.exe').
    Falls back to 'Unknown' if win32 APIs are unavailable or fail.
    """
    try:
        # These Windows-only libraries are imported here (not at the top of the file)
        # so the program still starts on non-Windows systems without crashing.
        import win32gui  # type: ignore
        import win32process  # type: ignore
        hwnd = win32gui.GetForegroundWindow()              # HWND = a handle (ID number) for the focused window
        _, pid = win32process.GetWindowThreadProcessId(hwnd)  # Get the Process ID (PID) that owns that window
        import psutil  # type: ignore                         # Cross-platform process inspector library
        return psutil.Process(pid).name()                     # e.g. "chrome.exe" or "python.exe"
    except Exception:
        return "Unknown"   # Silently fall back if the API failed or we're on a non-Windows system


# ─── Snapshot (thread-safe read of current totals) ────────────────────────────

def _snapshot() -> dict:
    """Return a consistent snapshot of all statistics including ongoing AFK.

    All values are read inside a lock so we never see a partially-updated state
    (e.g. the AFK timer ticking between two separate reads).
    """
    with _lock:
        # If the user is currently idle, count seconds since AFK started as
        # 'extra' AFK that hasn't been committed to st.afk_secs yet.
        extra_afk = (time.monotonic() - st.afk_t0) if st.is_afk else 0.0

        # Total monitor-on time = time already saved to disk + time since last save
        monitor   = st.saved_monitor + st.session_awake

        # Total AFK = all past idle periods + any idle time happening right now
        afk       = st.afk_secs + extra_afk

        # Active time = monitor time minus idle time (clamped to 0, never negative)
        active    = max(0.0, monitor - afk)

        ks        = st.keystrokes   # Total keystrokes recorded today
    return {
        "date":            _today(),        # "YYYY-MM-DD" string for today
        "keystrokes":      ks,
        "monitor_seconds": round(monitor, 1),
        "afk_seconds":     round(afk, 1),
        "active_seconds":  round(active, 1),
    }


# ─── Persistence ──────────────────────────────────────────────────────────────

def _load_today() -> None:
    """Load today's saved stats (if any) so sessions accumulate correctly.

    Data is stored in a JSON file named stats_YYYY-MM-DD.json inside the
    AppData folder. If the file does not exist or is unreadable, the tracker
    simply starts fresh from zero — no error is shown to the user.
    """
    f = _data_file()
    if not f.exists():
        return  # No data saved for today yet — start fresh
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("date") == _today():
            # Restore previously saved values into the live state object
            with _lock:
                st.keystrokes     = int(d.get("keystrokes", 0))
                st.afk_secs       = float(d.get("afk_seconds", 0.0))
                st.saved_monitor  = float(d.get("monitor_seconds", 0.0))
                st.hourly_active  = {int(k): float(v)
                                     for k, v in d.get("hourly_active", {}).items()}
                st.app_keystrokes = {str(k): int(v)
                                     for k, v in d.get("app_keystrokes", {}).items()}
    except Exception:
        pass  # File is corrupt or unreadable — start from zero for this session


def _save_today() -> None:
    """Write current snapshot to today's JSON file."""
    snap = _snapshot()
    with _lock:
        snap["hourly_active"]  = {str(k): round(v, 1)
                                   for k, v in st.hourly_active.items()}
        snap["app_keystrokes"] = dict(st.app_keystrokes)
    try:
        _data_file().write_text(json.dumps(snap, indent=2), encoding="utf-8")
    except Exception:
        pass


# ─── Input listeners (run in pynput threads) ─────────────────────────────────

def _record_activity() -> None:
    """Called on any keyboard or mouse event to reset the idle timer.

    Every time the user types or moves the mouse, we update 'last_input'
    to the current time. If the user was previously marked as AFK (idle),
    we also finalise and save that AFK period before clearing the AFK flag.
    """
    now = time.monotonic()
    with _lock:
        st.last_input = now      # Reset the idle clock
        if st.is_afk:
            # The user just came back from AFK — commit how long they were away
            st.afk_secs += now - st.afk_t0
            st.is_afk    = False


def _on_key(key) -> None:
    # Called every time a key is pressed on the keyboard.
    # Records which application was in focus and increments the keystroke counter.
    app = _get_foreground_app()
    with _lock:
        st.keystrokes += 1                                          # total keys today
        st.app_keystrokes[app] = st.app_keystrokes.get(app, 0) + 1  # keys per app
    _record_activity()  # also resets the AFK/idle timer


def _on_mouse(*_) -> None:
    # Called on any mouse movement, click, or scroll.
    # Mouse events only reset the AFK timer — they are NOT counted as keystrokes.
    _record_activity()


# ─── Background tracker thread ────────────────────────────────────────────────

def _tracker() -> None:
    """
    Runs every ~1 second.
    - Accumulates awake time (skips gaps caused by sleep/hibernate).
    - Detects AFK after AFK_THRESHOLD seconds of no input.
    - Detects midnight rollover and resets daily counters.
    - Periodically flushes stats to disk.
    """
    prev_tick  = time.monotonic()
    last_saved = prev_tick
    today      = _today()

    while st.running:
        time.sleep(1)
        now = time.monotonic()
        gap = now - prev_tick
        prev_tick = now

        with _lock:
            # ── Midnight rollover ─────────────────────────────────────────────
            new_day = _today()
            if new_day != today:
                today             = new_day
                st.session_awake  = 0.0
                st.afk_secs       = 0.0
                st.keystrokes     = 0
                st.saved_monitor  = 0.0
                st.is_afk         = False
                st.hourly_active  = {}
                st.app_keystrokes = {}

            # ── Awake time accumulation (skip sleep/hibernate gaps) ───────────
            if gap <= SLEEP_DETECT:
                st.session_awake += gap
            # else: system was asleep, don't count that time

            # ── AFK detection ─────────────────────────────────────────────────
            idle = now - st.last_input
            if not st.is_afk and idle >= AFK_THRESHOLD:
                st.is_afk = True
                # AFK officially started AFK_THRESHOLD seconds after last input
                st.afk_t0 = st.last_input + AFK_THRESHOLD
            # ── Hourly active tracking ───────────────────────────────────────────────
            if gap <= SLEEP_DETECT and not st.is_afk:
                h = time.localtime().tm_hour
                st.hourly_active[h] = st.hourly_active.get(h, 0.0) + gap
        # ── Periodic save (outside lock) ──────────────────────────────────────
        if now - last_saved >= SAVE_INTERVAL:
            _save_today()
            last_saved = now


# ─── System tray icon ─────────────────────────────────────────────────────────

def _make_icon() -> Image.Image:
    """Draw a simple monitor-shaped 64×64 RGBA icon."""
    sz  = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Monitor body / bezel
    d.rectangle([2, 6, 62, 48], fill=(52, 73, 94))
    # Screen (blue)
    d.rectangle([6, 10, 58, 44], fill=(41, 128, 185))
    # Stand pole
    d.rectangle([29, 48, 35, 56], fill=(52, 73, 94))
    # Stand base
    d.rectangle([18, 56, 46, 61], fill=(52, 73, 94))
    # Green activity indicator dot
    d.ellipse([46, 12, 55, 21], fill=(39, 174, 96))

    return img


# ─── Tray menu actions ────────────────────────────────────────────────────────

def _show_stats(icon=None, item=None) -> None:
    """Show today's stats in a message box.

    Called when the user double-clicks the tray icon or selects
    "Show Today's Stats" from the right-click menu.
    """
    snap = _snapshot()   # Grab a thread-safe copy of all current statistics

    # Calculate AFK as a percentage of monitor-on time.
    # Guard against division-by-zero if the monitor has only just turned on.
    afk_pct = 0
    if snap["monitor_seconds"] > 0:
        afk_pct = round(snap["afk_seconds"] / snap["monitor_seconds"] * 100, 1)

    # Build a multi-line formatted string for the pop-up dialog.
    # f-strings embed live variable values directly in the text.
    # {'─' * 44}  repeats the '─' character 44 times to draw a horizontal rule.
    # {snap['keystrokes']:,}  formats the integer with thousands separators (e.g. 12,345).
    msg = (
        f"Activity Tracker  ─  {snap['date']}\n"
        f"{'─' * 44}\n\n"
        f"  Monitor On Time :  {_fmt_time(snap['monitor_seconds'])}\n"
        f"  Active Time     :  {_fmt_time(snap['active_seconds'])}\n"
        f"  AFK Time        :  {_fmt_time(snap['afk_seconds'])}  ({afk_pct}%)\n\n"
        f"  Keystrokes Today:  {snap['keystrokes']:,}\n\n"
        f"{'─' * 44}\n"
        f"Data folder:\n{DATA_DIR}"
    )
    # 0x40 = MB_ICONINFORMATION flag — shows the blue (ℹ) icon in the dialog box
    ctypes.windll.user32.MessageBoxW(None, msg, APP_LABEL, 0x40)


def _show_history(icon=None, item=None) -> None:
    """Show last 7 days of stats in a message box.

    Reads up to 7 saved JSON files (newest first) and formats them as a
    fixed-width table so the columns line up neatly in the dialog box.
    """
    # Sort all stats_YYYY-MM-DD.json files newest-first; take the top 7
    files = sorted(DATA_DIR.glob("stats_*.json"), reverse=True)[:7]

    # Fixed-width column headers:
    # :<12 means left-align in a 12-character field; :>8 means right-align in 8 chars.
    header  = f"{'Date':<12} {'Monitor':>8} {'Active':>8} {'AFK':>8} {'Keys':>9}"
    divider = "─" * 50
    lines   = [header, divider]

    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            lines.append(
                f"{d.get('date', '?'):<12} "
                f"{_fmt_time(d.get('monitor_seconds', 0)):>8} "
                f"{_fmt_time(d.get('active_seconds', 0)):>8} "
                f"{_fmt_time(d.get('afk_seconds', 0)):>8} "
                f"{d.get('keystrokes', 0):>9,}"   # :>9,  = right-align + thousands separator
            )
        except Exception:
            pass   # Skip any unreadable or malformed files silently

    if len(lines) <= 2:   # Only the header + divider — no actual data rows added
        lines.append("  No history yet.")
    ctypes.windll.user32.MessageBoxW(
        None, "\n".join(lines), f"{APP_LABEL} — Last 7 Days", 0x40
    )


# ─── Analytics ────────────────────────────────────────────────────────────────

def _load_all_records() -> list:
    """Load all saved daily JSON files, merging today's live snapshot.

    Used by the analytics dashboard to plot historical charts.
    Returns a list of dicts, each representing one day, sorted oldest-first.
    Today's entry is always the live in-memory snapshot rather than the last
    flushed-to-disk version, so charts are always up to the current second.
    """
    records = []
    # Read every stats_YYYY-MM-DD.json, oldest file first (glob + sort = alphabetical order)
    for f in sorted(DATA_DIR.glob("stats_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if "date" in d:           # Skip any file that is missing the date key
                records.append(d)
        except Exception:
            pass   # Ignore corrupt or unreadable files

    today_str = _today()
    snap      = _snapshot()   # Live snapshot — more current than the last saved file

    # Add today's per-hour active breakdown into the snapshot dict
    with _lock:
        snap["hourly_active"] = {str(k): round(v, 1)
                                  for k, v in st.hourly_active.items()}

    # Replace the saved entry for today (if any) with the live snapshot so
    # analytics always reflect the current session's running totals.
    if records and records[-1].get("date") == today_str:
        records[-1] = snap   # Overwrite the last entry (it's today's saved file)
    elif not any(r.get("date") == today_str for r in records):
        records.append(snap)  # Today hasn't been saved yet — append the live data
    return records


class AnalyticsDashboard:
    """Tabbed analytics window: Hour / Day / Week / Month / Year."""

    BG    = "#0d0d1a"
    FG    = "#e0e0e0"
    C_ACT = "#27ae60"
    C_AFK = "#e74c3c"
    C_KEY = "#f39c12"
    C_AX  = "#1a1a2e"
    FONT  = "Consolas"

    def __init__(self, parent: tk.Tk) -> None:
        self._win = tk.Toplevel(parent)
        self._win.title("Activity Analytics")
        self._win.configure(bg=self.BG)
        self._win.geometry("960x560")
        self._win.resizable(True, True)
        self._win.lift()
        self._win.focus_force()
        self._win.protocol("WM_DELETE_WINDOW", self._win.destroy)
        self._build()

    def _build(self) -> None:
        # ── Style the tab bar ─────────────────────────────────────────────────
        # ttk.Style lets us override the default look-and-feel for themed widgets.
        # "AT.TNotebook" is a custom style name we invent (AT = ActivityTracker).
        # We must call theme_use("default") first to reset any inherited styles.
        style = ttk.Style(self._win)
        style.theme_use("default")   # Reset to the plain default theme

        # The notebook background (the area visible behind all the tab buttons)
        style.configure("AT.TNotebook",
                        background=self.BG, borderwidth=0)

        # Each individual tab button: dark background, light text, bold Consolas font
        style.configure("AT.TNotebook.Tab",
                        background="#1a1a2e", foreground=self.FG,
                        font=(self.FONT, 9, "bold"), padding=[14, 5])

        # When a tab is selected (active), change its background to bright blue
        style.map("AT.TNotebook.Tab",
                  background=[("selected", "#2563eb")],
                  foreground=[("selected", "#ffffff")])

        # ── Create the tabbed notebook widget ─────────────────────────────────
        # ttk.Notebook is the container that holds the tabs.
        # fill="both", expand=True means it stretches to fill the whole window.
        nb = ttk.Notebook(self._win, style="AT.TNotebook")
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # ── Add each tab ──────────────────────────────────────────────────────
        # For every (tab label, chart-building function) pair:
        #   1. Create a blank dark Frame to hold the chart.
        #   2. Register it with the notebook under that label.
        #   3. Call the builder function to draw the chart INTO that frame.
        #      If the builder crashes, show the error traceback in the tab
        #      instead of crashing the whole analytics window.
        for label, builder in [
            ("  Hour  ", self._tab_hour),
            ("  Day   ", self._tab_day),
            ("  Week  ", self._tab_week),
            ("  Month ", self._tab_month),
            ("  Year  ", self._tab_year),
            (" Keys \u2794 App ", self._tab_apps),
        ]:
            frame = tk.Frame(nb, bg=self.BG)
            nb.add(frame, text=label)
            try:
                builder(frame)   # Draw the chart inside this frame
            except Exception:
                import traceback
                tk.Label(   # If drawing failed, show the error message instead
                    frame,
                    text=traceback.format_exc(),
                    fg="#e74c3c", bg=self.BG,
                    justify="left", font=(self.FONT, 8),
                    wraplength=920,
                ).pack(padx=10, pady=10)

    # ── matplotlib helper ─────────────────────────────────────────────────────

    def _new_fig_ax(self, parent: tk.Frame):
        """Create a matplotlib Figure embedded in the given Tkinter frame.

        Returns (fig, ax, canvas):
          fig    — the Figure object (the whole drawing surface)
          ax     — the Axes object where data is plotted (bars, lines, etc.)
          canvas — the Tkinter canvas widget that wraps the figure
        """
        # matplotlib is imported here (not at the top of the file) so startup
        # is fast — we only pay the import cost when the analytics window opens.
        import matplotlib.figure as mfig  # type: ignore
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # type: ignore

        # figsize is in inches; matplotlib multiplies by screen DPI to get pixels
        fig = mfig.Figure(figsize=(9.4, 4.5), facecolor=self.BG)

        # add_subplot(111) means: 1 row × 1 column grid, subplot #1 — a single chart
        ax  = fig.add_subplot(111)
        ax.set_facecolor(self.C_AX)          # Dark background *inside* the chart area

        # Spines are the four border lines around the chart; style them dark
        for spine in ax.spines.values():
            spine.set_edgecolor("#2c3e50")

        # Apply the light foreground colour to tick labels and axis titles
        ax.tick_params(colors=self.FG, labelsize=7)
        ax.xaxis.label.set_color(self.FG)
        ax.yaxis.label.set_color(self.FG)
        ax.title.set_color(self.FG)  # type: ignore

        # FigureCanvasTkAgg bridges matplotlib ↔ Tkinter:
        # it turns the Figure into a Tkinter widget that can be packed into a Frame.
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        return fig, ax, canvas

    def _add_legend(self, ax) -> None:
        """Add a colour-coded legend box styled to match the dark theme."""
        ax.legend(facecolor="#1a1a2e", edgecolor="#2c3e50",
                  labelcolor=self.FG, fontsize=8)

    # ── Tab: Hour ─────────────────────────────────────────────────────────────

    def _tab_hour(self, frame: tk.Frame) -> None:
        """Bar chart: how many minutes were active in each hour of the current day."""
        fig, ax, canvas = self._new_fig_ax(frame)

        # Read the hourly dictionary inside the lock for a consistent snapshot
        with _lock:
            hourly = dict(st.hourly_active)  # {hour_int: active_seconds_float}

        hours  = list(range(24))   # [0, 1, 2, ..., 23]

        # Convert each hour's seconds to hours for a human-readable y-axis.
        # hourly.get(h, 0.0) returns 0.0 for any hour with no recorded activity.
        active = [hourly.get(h, 0.0) / 3600 for h in hours]

        # Draw a vertical bar for each of the 24 hours; zorder=2 puts bars in front of grid lines
        ax.bar(hours, active, color=self.C_ACT, width=0.75, label="Active", zorder=2)
        ax.set_title("Today — Active Time by Hour", color=self.FG)
        ax.set_xlabel("Hour of Day", color=self.FG)
        ax.set_ylabel("Hours", color=self.FG)

        # Label the x-axis with "00:00", "01:00", ..., "23:00".
        # rotation=60 tilts the labels so they do not overlap each other.
        ax.set_xticks(hours)
        ax.set_xticklabels([f"{h:02d}:00" for h in hours], rotation=60, fontsize=6)
        ax.set_xlim(-0.5, 23.5)   # A small padding on both sides of the chart

        # Draw a vertical dashed line at the current hour so you can see
        # where you are in the day at a glance.
        now_h = datetime.now().hour
        ax.axvline(x=now_h, color=self.C_KEY, linestyle="--",
                   linewidth=1.2, alpha=0.8, label=f"Now ({now_h:02d}:00)")

        self._add_legend(ax)
        fig.tight_layout()   # Automatically shrink margins to fit all labels
        canvas.draw()        # Render the finished chart into the Tkinter widget

    # ── Tab: Day ──────────────────────────────────────────────────────────────

    def _tab_day(self, frame: tk.Frame) -> None:
        """Stacked bar chart of active/AFK time for the last 30 days,
        with an optional overlay line for keystroke counts (right y-axis)."""
        from datetime import timedelta

        fig, ax, canvas = self._new_fig_ax(frame)
        records = _load_all_records()
        today   = date.today()

        # Build a list of the last 30 days as "YYYY-MM-DD" strings, oldest first
        days    = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

        # Index records by date string for fast O(1) lookup per day
        by_date = {r["date"]: r for r in records}

        # Extract values for each day; default to 0 if no saved file exists for that day
        active = [by_date.get(d, {}).get("active_seconds", 0) / 3600 for d in days]
        afk    = [by_date.get(d, {}).get("afk_seconds",    0) / 3600 for d in days]
        keys   = [by_date.get(d, {}).get("keystrokes",     0)         for d in days]
        x      = list(range(len(days)))   # [0, 1, ..., 29] — x-axis positions

        # Stacked bar chart: draw AFK *on top of* active so the total bar height
        # represents monitor-on time, split by colour into active vs. idle portions.
        ax.bar(x, active, color=self.C_ACT, width=0.75, label="Active", zorder=2)
        ax.bar(x, afk,    color=self.C_AFK, width=0.75, label="AFK",
               bottom=active, zorder=2)   # bottom=active stacks AFK on top of active
        ax.set_title("Last 30 Days", color=self.FG)
        ax.set_ylabel("Hours", color=self.FG)

        # Show every 3rd date label to avoid overcrowding; [5:] strips the year prefix
        ax.set_xticks(x[::3])
        ax.set_xticklabels([days[i][5:] for i in range(0, 30, 3)],
                           rotation=45, fontsize=7)

        # Only draw the keystroke line if there is key data to show.
        # twinx() creates a second y-axis sharing the same x-axis —
        # the right spine shows keystroke counts while the left spine shows hours.
        if any(k > 0 for k in keys):
            ax2 = ax.twinx()
            ax2.plot(x, keys, color=self.C_KEY, linewidth=1.5,
                     alpha=0.85, label="Keys", zorder=3)
            ax2.tick_params(colors=self.C_KEY, labelsize=7)
            ax2.set_ylabel("Keystrokes", color=self.C_KEY)
            for side in ("right", "left", "top", "bottom"):
                ax2.spines[side].set_edgecolor(
                    self.C_KEY if side == "right" else "#2c3e50")

        self._add_legend(ax)
        fig.tight_layout()
        canvas.draw()

    # ── Tab: Week ─────────────────────────────────────────────────────────────

    def _tab_week(self, frame: tk.Frame) -> None:
        """Stacked bar chart of active/AFK time per ISO calendar week (last 12 weeks)."""
        fig, ax, canvas = self._new_fig_ax(frame)
        records = _load_all_records()

        # "Bucketing": loop through every daily record and group it into its ISO week.
        # An ISO week key is a (year, week_number) tuple, e.g. (2024, 3).
        # isocalendar() returns (year, week, weekday) per the ISO 8601 standard
        # where Week 1 is the week containing the first Thursday of the year.
        buckets: dict = {}
        for r in records:
            try:
                d   = date.fromisoformat(r["date"])
                iso = d.isocalendar()
                key = (iso.year, iso.week)
                if key not in buckets:
                    buckets[key] = {"active": 0.0, "afk": 0.0, "keys": 0}
                # Accumulate this day's totals into its week bucket
                buckets[key]["active"] += r.get("active_seconds", 0)
                buckets[key]["afk"]    += r.get("afk_seconds",    0)
                buckets[key]["keys"]   += r.get("keystrokes",     0)
            except Exception:
                pass   # Skip any records with unparseable dates

        # Take only the 12 most-recent weeks.
        # sorted() on tuples sorts year first, then week number, so chronological.
        all_keys = sorted(buckets)[-12:]
        labels   = [f"W{k[1]:02d}\n{k[0]}" for k in all_keys]   # e.g. "W03\n2024"
        active   = [buckets[k]["active"] / 3600 for k in all_keys]
        afk      = [buckets[k]["afk"]    / 3600 for k in all_keys]
        x        = list(range(len(all_keys)))

        ax.bar(x, active, color=self.C_ACT, width=0.65, label="Active")
        ax.bar(x, afk,    color=self.C_AFK, width=0.65, label="AFK", bottom=active)
        ax.set_title("Last 12 Weeks", color=self.FG)
        ax.set_ylabel("Hours", color=self.FG)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7)
        self._add_legend(ax)
        fig.tight_layout()
        canvas.draw()

    # ── Tab: Month ────────────────────────────────────────────────────────────

    def _tab_month(self, frame: tk.Frame) -> None:
        """Stacked bar chart of active/AFK time per calendar month (last 12 months)."""
        fig, ax, canvas = self._new_fig_ax(frame)
        records = _load_all_records()

        # Same bucketing pattern as _tab_week but grouped by (year, month) instead
        buckets: dict = {}
        for r in records:
            try:
                d   = date.fromisoformat(r["date"])
                key = (d.year, d.month)
                if key not in buckets:
                    buckets[key] = {"active": 0.0, "afk": 0.0, "keys": 0}
                buckets[key]["active"] += r.get("active_seconds", 0)
                buckets[key]["afk"]    += r.get("afk_seconds",    0)
                buckets[key]["keys"]   += r.get("keystrokes",     0)
            except Exception:
                pass

        all_keys = sorted(buckets)[-12:]
        # strftime("%b\n%Y") formats to short month + year, e.g. "Jan\n2024"
        labels   = [date(k[0], k[1], 1).strftime("%b\n%Y") for k in all_keys]
        active   = [buckets[k]["active"] / 3600 for k in all_keys]
        afk      = [buckets[k]["afk"]    / 3600 for k in all_keys]
        x        = list(range(len(all_keys)))

        ax.bar(x, active, color=self.C_ACT, width=0.65, label="Active")
        ax.bar(x, afk,    color=self.C_AFK, width=0.65, label="AFK", bottom=active)
        ax.set_title("Last 12 Months", color=self.FG)
        ax.set_ylabel("Hours", color=self.FG)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        self._add_legend(ax)
        fig.tight_layout()
        canvas.draw()

    # ── Tab: Year ─────────────────────────────────────────────────────────────

    def _tab_year(self, frame: tk.Frame) -> None:
        """Stacked bar chart of active/AFK time per year (all years with saved data)."""
        fig, ax, canvas = self._new_fig_ax(frame)
        records = _load_all_records()

        # Group every daily record by year — no upper limit, shows the full history
        buckets: dict = {}
        for r in records:
            try:
                y = date.fromisoformat(r["date"]).year
                if y not in buckets:
                    buckets[y] = {"active": 0.0, "afk": 0.0, "keys": 0}
                buckets[y]["active"] += r.get("active_seconds", 0)
                buckets[y]["afk"]    += r.get("afk_seconds",    0)
                buckets[y]["keys"]   += r.get("keystrokes",     0)
            except Exception:
                pass

        all_years = sorted(buckets)   # Ascending: 2023, 2024, 2025, ...
        active    = [buckets[y]["active"] / 3600 for y in all_years]
        afk       = [buckets[y]["afk"]    / 3600 for y in all_years]
        x         = list(range(len(all_years)))

        ax.bar(x, active, color=self.C_ACT, width=0.55, label="Active")
        ax.bar(x, afk,    color=self.C_AFK, width=0.55, label="AFK", bottom=active)
        ax.set_title("All Years", color=self.FG)
        ax.set_ylabel("Hours", color=self.FG)
        ax.set_xticks(x)
        ax.set_xticklabels([str(y) for y in all_years], fontsize=9)
        self._add_legend(ax)
        fig.tight_layout()
        canvas.draw()

    # ── Tab: Keys by App ──────────────────────────────────────────────────────

    def _tab_apps(self, frame: tk.Frame) -> None:
        """Two sub-views: today's pie chart (left) + all-time top-20 bar (right).

        Left panel  — Pie chart: today's keystrokes distributed among apps.
        Right panel — Horizontal bar chart: all-time top 20 apps by keystroke count.
        """
        # Imported here so startup is fast; only loaded when the analytics window opens
        import matplotlib.figure as mfig  # type: ignore
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # type: ignore

        # ── Today's per-app keystroke counts (thread-safe snapshot) ──
        with _lock:
            today_apps = dict(st.app_keystrokes)  # {"chrome.exe": 1234, ...}

        # ── All-time aggregation: sum each app's keystrokes across every saved day ──
        alltime: dict[str, int] = {}
        for r in _load_all_records():
            for app, cnt in r.get("app_keystrokes", {}).items():
                alltime[app] = alltime.get(app, 0) + int(cnt)

        fig = mfig.Figure(figsize=(9.4, 4.6), facecolor=self.BG)
        fig.subplots_adjust(left=0.06, right=0.97, wspace=0.35)

        # ── Left: today pie ───────────────────────────────────────────────────
        ax1 = fig.add_subplot(1, 2, 1)
        ax1.set_facecolor(self.BG)
        ax1.set_title("Today — Keys by App", color=self.FG, fontsize=9)

        if today_apps:
            # Sort apps largest-first; keep top 8 individually, lump the rest as "Other"
            sorted_today = sorted(today_apps.items(), key=lambda x: x[1], reverse=True)
            top_today    = sorted_today[:8]
            other_today  = sum(v for _, v in sorted_today[8:])
            if other_today:
                top_today.append(("Other", other_today))
            labels_t = [a for a, _ in top_today]
            sizes_t  = [c for _, c in top_today]   # keystroke counts = pie slice sizes
            COLORS   = ["#27ae60","#2980b9","#f39c12","#8e44ad","#e74c3c",
                        "#16a085","#d35400","#2c3e50","#7f8c8d"]
            # autopct="%1.1f%%" adds percentage labels inside each wedge
            wedges, texts, autotexts = ax1.pie(
                sizes_t, labels=None, autopct="%1.1f%%",
                colors=COLORS[:len(sizes_t)], startangle=140,
                pctdistance=0.78, textprops={"color": self.FG, "fontsize": 7},
            )
            for at in autotexts:
                at.set_fontsize(6.5)
            # Place the legend below the pie so it doesn't overlap the wedges
            ax1.legend(
                wedges, labels_t,
                loc="lower center", bbox_to_anchor=(0.5, -0.22),
                ncol=2, facecolor="#1a1a2e", edgecolor="#2c3e50",
                labelcolor=self.FG, fontsize=7,
            )
        else:
            ax1.text(0.5, 0.5, "No data yet\nfor today",
                     ha="center", va="center", color=self.FG,
                     fontsize=10, transform=ax1.transAxes)

        # ── Right: all-time top-20 horizontal bar ─────────────────────────────
        ax2 = fig.add_subplot(1, 2, 2)
        ax2.set_facecolor(self.C_AX)
        for spine in ax2.spines.values():
            spine.set_edgecolor("#2c3e50")
        ax2.tick_params(colors=self.FG, labelsize=7)
        ax2.set_title("All-Time — Top 20 Apps by Keys", color=self.FG, fontsize=9)

        if alltime:
            sorted_all = sorted(alltime.items(), key=lambda x: x[1], reverse=True)[:20]
            names = [a for a, _ in reversed(sorted_all)]
            counts = [c for _, c in reversed(sorted_all)]
            y = list(range(len(names)))
            bars = ax2.barh(y, counts, color="#2980b9", height=0.65)
            ax2.set_yticks(y)
            ax2.set_yticklabels(names, fontsize=7)
            ax2.set_xlabel("Keystrokes", color=self.FG)
            # Value labels on bars
            for bar, val in zip(bars, counts):
                ax2.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2,
                         f"{val:,}", va="center", color=self.FG, fontsize=6)
        else:
            ax2.text(0.5, 0.5, "No data yet",
                     ha="center", va="center", color=self.FG,
                     fontsize=10, transform=ax2.transAxes)

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        canvas.draw()


def _show_top_apps(icon=None, item=None) -> None:
    """Show top-5 apps by keystrokes today in a message box."""
    import ctypes
    with _lock:
        apps = dict(st.app_keystrokes)   # Thread-safe copy of {app_name: keystroke_count}
    if not apps:
        ctypes.windll.user32.MessageBoxW(0, "No keystroke data yet today.", "Top Apps Today", 0x40)
        return
    # Sort apps by keystroke count (largest first) and take the top 5
    top5 = sorted(apps.items(), key=lambda x: x[1], reverse=True)[:5]
    # Build a numbered list: rank, app name (left-aligned in 28 chars), count (right-aligned)
    lines = "\n".join(f"  {i+1}. {app:<28} {cnt:>7,}" for i, (app, cnt) in enumerate(top5))
    ctypes.windll.user32.MessageBoxW(0, f"Top Apps by Keystrokes Today\n\n{lines}", "Top Apps Today", 0x40)


def _show_analytics(icon=None, item=None) -> None:
    """Open the analytics dashboard window on the tkinter main thread."""
    if _overlay is not None:
        _overlay._root.after(0, lambda: AnalyticsDashboard(_overlay._root)) # type: ignore


# ─── Auto-start helpers ───────────────────────────────────────────────────────

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_enabled() -> bool:
    """Return True if this app is registered to start automatically with Windows.

    Checks the Windows Registry key that Windows reads on login:
    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    If our app name exists as a value there, auto-start is enabled.
    """
    try:
        # Try to open the Run key and look up our app's entry.
        # If the value doesn't exist, QueryValueEx raises OSError.
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(k, APP_NAME)
        winreg.CloseKey(k)
        return True
    except OSError:
        return False   # Key or value not found — auto-start is not set


def _set_autostart(enable: bool) -> None:
    """Add or remove this script from the Windows startup registry key.

    When enable=True, writes a registry value like:
        ActivityTracker = "C:\\Python\\pythonw.exe" "C:\\path\\to\\ActivityTracker.py"
    Windows reads this key at login and launches every listed program.
    When enable=False, deletes that registry value so the app no longer auto-starts.
    """
    try:
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        )
        if enable:
            exe      = Path(sys.executable)             # Full path to python.exe
            # Prefer pythonw.exe (no console window) over python.exe if it exists
            pythonw  = exe.with_name("pythonw.exe")
            runner   = str(pythonw) if pythonw.exists() else str(exe)
            script   = os.path.abspath(sys.argv[0])     # Full path to this .py script
            # Write: "path\to\pythonw.exe" "path\to\script.py"
            # REG_SZ stores a plain text (string) registry value
            winreg.SetValueEx(
                k, APP_NAME, 0, winreg.REG_SZ, f'"{runner}" "{script}"'
            )
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)   # Remove the startup entry
            except FileNotFoundError:
                pass   # Already gone — nothing to do
        winreg.CloseKey(k)
    except OSError:
        pass   # If we can't write the registry (permissions?), fail silently


def _toggle_autostart(icon=None, item=None) -> None:
    enabled = not _autostart_enabled()
    _set_autostart(enabled)
    status = "enabled" if enabled else "disabled"
    ctypes.windll.user32.MessageBoxW(None, f"Auto-start {status}.", APP_LABEL, 0x40)


# ─── Desktop overlay widget ───────────────────────────────────────────────────

# Windows API constants for click-through
_GWL_EXSTYLE       = -20
_WS_EX_LAYERED     = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_LWA_ALPHA         = 0x00000002


def _set_click_through(hwnd: int, enable: bool, alpha_byte: int = 209) -> None:
    """Add or remove WS_EX_TRANSPARENT, then re-apply the alpha value.

    Re-applying SetLayeredWindowAttributes is necessary because SetWindowLongW
    can reset layered window attributes on some Windows versions, making the
    window fully invisible.

    WS_EX_LAYERED   — enables the window to be semi-transparent (layered window).
    WS_EX_TRANSPARENT — makes mouse clicks pass straight through the window to
                         whatever is behind it (click-through mode).
    """
    u32 = ctypes.windll.user32
    # Tell ctypes the return type of these Win32 functions so it reads the value correctly
    u32.GetWindowLongW.restype  = ctypes.c_long
    u32.SetWindowLongW.restype  = ctypes.c_long

    # Read the current extended window style flags (a 32-bit bitmask)
    style = u32.GetWindowLongW(hwnd, _GWL_EXSTYLE)

    if enable:
        # |= sets (adds) both bits: WS_EX_LAYERED and WS_EX_TRANSPARENT
        # The | operator performs bitwise OR: if the bit is already set, it stays set.
        style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
    else:
        # Always keep WS_EX_LAYERED so the alpha still works, but *clear* TRANSPARENT.
        # & ~_WS_EX_TRANSPARENT clears that specific bit while leaving all others intact.
        # ~ (bitwise NOT) flips every bit in the constant, and & keeps only bits that
        # were already set AND are not in the ~_WS_EX_TRANSPARENT mask.
        style = (style | _WS_EX_LAYERED) & ~_WS_EX_TRANSPARENT

    u32.SetWindowLongW(hwnd, _GWL_EXSTYLE, ctypes.c_long(style))
    # Re-apply alpha so the window does not accidentally become fully invisible
    u32.SetLayeredWindowAttributes(hwnd, 0, alpha_byte, _LWA_ALPHA)


class OverlayWidget:
    """Semi-transparent always-on-top stats widget anchored to the top-left.

    Click-through by default — clicks pass straight through to whatever is
    underneath.  Use 'Unlock Overlay' from the tray menu to enable drag-to-
    move, then 'Lock Overlay' (or the same menu item) to make it click-through
    again.
    """

    UPDATE_MS = 1000  # refresh interval

    # Visual style
    BG          = "#1a1a2e"
    FG_TITLE    = "#7ec8e3"
    FG_TITLE_UL = "#f39c12"  # orange title bar when unlocked / draggable
    FG_LABEL    = "#aaaaaa"
    FG_VALUE    = "#ffffff"
    FG_AFK      = "#e74c3c"
    FONT        = ("Consolas", 9)
    ALPHA       = 0.82

    def __init__(self) -> None:
        self._visible       = True   # Whether the overlay window is currently shown
        self._locked        = True   # True = click-through mode; False = draggable
        self._always_on_top = True   # Whether the window always floats above other windows
        self._alpha_byte    = int(self.ALPHA * 255)  # Opacity as a 0–255 byte value
        self._root          = tk.Tk()  # The main Tkinter window object
        self._drag_x        = 0      # Used to track drag start X position
        self._drag_y        = 0      # Used to track drag start Y position
        self._hwnd          = None   # Windows window handle (set after window appears)
        self._build()                # Create all the visual widgets
        self._apply_click_through()  # Apply the click-through window style
        # Schedule the first stat refresh to run as soon as the event loop starts
        self._root.after(0, self._schedule_update)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        r = self._root
        r.overrideredirect(True)          # Remove the title bar and window borders
        r.attributes("-topmost", True)    # Keep the window on top of all other windows by default
        r.attributes("-alpha", self.ALPHA)  # Set window transparency (0.0 = invisible, 1.0 = solid)
        r.configure(bg=self.BG)           # Set the background colour
        r.geometry("+8+8")                # Position the window 8 pixels from the top-left corner

        # Title row (stores reference so colour can change when locked/unlocked)
        self._title_lbl = tk.Label(
            r, text="Activity Tracker",
            fg=self.FG_TITLE, bg=self.BG,
            font=(self.FONT[0], self.FONT[1], "bold"),
            padx=10, pady=4,
        )
        self._title_lbl.pack(fill="x")

        self._sep = tk.Frame(r, bg=self.FG_TITLE, height=1)
        self._sep.pack(fill="x", padx=8)

        # Stat rows
        self._vals: dict[str, tk.Label] = {}
        rows = [
            ("monitor", "Monitor "),
            ("active",  "Active  "),
            ("afk",     "AFK     "),
            ("keys",    "Keys    "),
        ]
        for key, label in rows:
            frame = tk.Frame(r, bg=self.BG)
            frame.pack(fill="x", padx=10, pady=1)
            tk.Label(
                frame, text=label,
                fg=self.FG_LABEL, bg=self.BG,
                font=self.FONT, anchor="w", width=8,
            ).pack(side="left")
            val = tk.Label(
                frame, text="--:--:--",
                fg=self.FG_VALUE, bg=self.BG,
                font=(self.FONT[0], self.FONT[1], "bold"), anchor="w",
            )
            val.pack(side="left")
            self._vals[key] = val

        tk.Frame(r, bg=self.BG, height=4).pack()
        # Message label for "nearly there"
        self._msg_lbl = tk.Label(
            r, text="",
            fg=self.FG_TITLE_UL, bg=self.BG,
            font=(self.FONT[0], self.FONT[1], "bold"), anchor="w"
        )
        self._msg_lbl.pack(fill="x", padx=10, pady=(2, 6))

        # Drag bindings (only active while unlocked)
        self._bind_drag(r) # type: ignore

    def _bind_drag(self, widget: tk.Widget) -> None:
        """Attach drag-start and drag-move event listeners to a widget and all its children.

        Tkinter events only fire on the exact widget the mouse is over, so we
        must bind every child widget recursively — otherwise clicking on a Label
        inside the overlay would not trigger the drag because the Label 'catches'
        the event before the parent Frame sees it.
        """
        widget.bind("<ButtonPress-1>", self._on_drag_start)  # Mouse button pressed
        widget.bind("<B1-Motion>",     self._on_drag_move)   # Mouse moved while button held
        # Recursively apply the same bindings to every child widget
        for child in widget.winfo_children():
            self._bind_drag(child)  # type: ignore

    def _apply_click_through(self) -> None:
        """Read HWND and apply click-through extended style."""
        self._root.update()   # ensure the window is fully realized and has an HWND
        self._hwnd = self._root.winfo_id()
        _set_click_through(self._hwnd, self._locked, self._alpha_byte)

    # ── Drag handlers ─────────────────────────────────────────────────────────

    def _on_drag_start(self, event: tk.Event) -> None:
        """Record the cursor's offset from the window's top-left corner when dragging starts.

        We save offset = cursor_position - window_position rather than an
        absolute coordinate so the window does not 'jump' to the cursor on the
        first drag move.
        """
        if self._locked:
            return   # Click-through mode is active — ignore drag attempts
        # event.x_root / event.y_root = cursor position relative to the screen
        # winfo_x() / winfo_y()       = window's top-left corner on the screen
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _on_drag_move(self, event: tk.Event) -> None:
        """Move the window to follow the cursor while the mouse button is held."""
        if self._locked:
            return
        # New window position = current cursor pos minus the saved offset,
        # so the point the user grabbed stays under the cursor throughout the drag.
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._root.geometry(f"+{x}+{y}")   # "+x+y" sets the window's screen position

    # ── Live update ───────────────────────────────────────────────────────────

    def _schedule_update(self) -> None:
        """Run _refresh() and then re-schedule itself to run again after UPDATE_MS.

        This creates a self-perpetuating timer loop inside Tkinter's event queue:
          _schedule_update → calls _refresh → schedules _schedule_update again
        Because _root.after() is non-blocking, this never stalls the UI.
        """
        try:
            self._refresh()
        except Exception:
            # If _refresh() crashes, write the traceback to a log file
            # so errors are not silently swallowed.
            try:
                log = DATA_DIR / "overlay_error.log"
                with log.open("a", encoding="utf-8") as f:
                    import traceback
                    f.write(traceback.format_exc())
            except Exception:
                pass
        # Schedule the next call; after() is safe to call from the main thread
        self._root.after(self.UPDATE_MS, self._schedule_update)

    def _refresh(self) -> None:
        """Pull the latest stats and push them into the on-screen label widgets."""
        if not st.running:
            # The user has clicked Exit — shut down the Tkinter window
            self._root.destroy()
            return
        snap = _snapshot()   # Get a thread-safe snapshot of all current stats

        # Update each label's text with the freshly formatted value
        self._vals["monitor"].config(text=_fmt_time(snap["monitor_seconds"]))
        self._vals["active"].config( text=_fmt_time(snap["active_seconds"]))

        # Highlight the AFK row in red while the user is currently idle
        afk_color = self.FG_AFK if snap["afk_seconds"] > 0 and st.is_afk else self.FG_VALUE
        self._vals["afk"].config(
            text=_fmt_time(snap["afk_seconds"]), fg=afk_color
        )
        self._vals["keys"].config(text=f"{snap['keystrokes']:,}")

        # Always show a countdown to 17:30; prefix "Nearly there!" in the last NEAR_BEFORE_MINUTES
        secs = _secs_to_target()
        if secs > 0:
            # Format remaining seconds as HH:MM:SS
            h, rem = divmod(int(secs), 3600)
            m, s   = divmod(rem, 60)
            countdown = f"{h:02d}:{m:02d}:{s:02d}"
            if secs <= NEAR_BEFORE_MINUTES * 60:
                # Within the final 30 minutes — add the encouragement prefix
                self._msg_lbl.config(text=f"Nearly there! {countdown} to go", fg=self.FG_TITLE_UL)
            else:
                # More than 30 minutes away — show the plain countdown in a neutral colour
                self._msg_lbl.config(text=f"{countdown} to 17:30", fg=self.FG_LABEL)
        else:
            self._msg_lbl.config(text="Yay, go home now!!!", fg=self.FG_TITLE_UL)

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle(self) -> None:
        # Show or hide the overlay window
        if self._visible:
            self._root.withdraw()   # Hide the window (keeps running in background)
        else:
            self._root.deiconify()  # Make the window visible again
            # Only re-apply always-on-top if that setting is currently active
            if self._always_on_top:
                self._root.attributes("-topmost", True)
        self._visible = not self._visible

    def set_locked(self, locked: bool) -> None:
        """True = click-through (default).  False = draggable."""
        self._locked = locked
        _set_click_through(self._hwnd, locked, self._alpha_byte) # type: ignore
        colour = self.FG_TITLE if locked else self.FG_TITLE_UL
        self._title_lbl.config(fg=colour)
        self._sep.config(bg=colour)

    def set_always_on_top(self, enabled: bool) -> None:
        """Enable or disable the overlay floating above all other windows.

        When enabled (default), the overlay stays visible even when other
        applications are maximised or brought to the foreground.
        When disabled, the overlay can be hidden behind other windows like
        any normal application window.
        """
        self._always_on_top = enabled
        # Apply the change to the live window immediately
        self._root.attributes("-topmost", enabled) # type: ignore

    def run(self) -> None:
        # Start the Tkinter event loop — this blocks until the window is closed
        self._root.mainloop()


_overlay: OverlayWidget | None = None


def _toggle_overlay(icon=None, item=None) -> None:
    """Show or hide the overlay widget.

    This is called from pystray's background thread.
    We use _root.after(0, ...) to hand the actual Tkinter call
    over to the main thread, because Tkinter is NOT thread-safe and
    all window operations must happen on the thread that created them.
    """
    if _overlay is not None:
        _overlay._root.after(0, _overlay.toggle)


def _toggle_overlay_lock(icon=None, item=None) -> None:
    """Toggle between click-through (locked) and draggable (unlocked).

    Called from pystray's background thread.  All UI work is moved into the
    inner _do() closure and posted to the Tkinter main thread via after(0, _do).
    This is necessary because Windows routes mouse input for MessageBoxW through
    the thread that owns the topmost window (our Tkinter overlay), so the dialog
    would be unresponsive if MessageBoxW ran on the pystray background thread.
    """
    overlay = _overlay
    if overlay is None:
        return
    def _do() -> None:
        new_locked = not overlay._locked
        overlay.set_locked(new_locked)
        state = "locked (click-through)" if new_locked else "unlocked (drag to move)"
        ctypes.windll.user32.MessageBoxW(None, f"Overlay {state}.", APP_LABEL, 0x40)
    overlay._root.after(0, _do)   # Run _do() on the Tkinter main thread


def _toggle_always_on_top(icon=None, item=None) -> None:
    """Toggle whether the overlay window always stays on top of other windows.

    When 'Always on Top' is ON  — the overlay floats above every other app,
                                   even when you switch to another program.
    When 'Always on Top' is OFF — the overlay can be covered by other windows,
                                   just like a normal application window.
    """
    overlay = _overlay
    if overlay is None:
        return
    def _do() -> None:
        new_state = not overlay._always_on_top
        overlay.set_always_on_top(new_state)
        status = "enabled" if new_state else "disabled"
        ctypes.windll.user32.MessageBoxW(
            None, f"Always on top {status}.", APP_LABEL, 0x40
        )
    overlay._root.after(0, _do)


# ─── Exit ─────────────────────────────────────────────────────────────────────

def _exit_app(icon, item) -> None:
    st.running = False
    # Commit any ongoing AFK before saving
    with _lock:
        if st.is_afk:
            st.afk_secs += time.monotonic() - st.afk_t0
            st.is_afk    = False
    _save_today()
    icon.stop()
    # _refresh() will detect st.running == False and destroy the tk window


# ─── Single-instance guard ────────────────────────────────────────────────────

# We keep a module-level reference to the mutex handle so Python's garbage
# collector never closes it while the program is still running.
_single_instance_mutex = None

def _ensure_single_instance() -> None:
    """Prevent two copies of Activity Tracker from running at the same time.

    Windows named mutexes are the standard mechanism for this:
      - CreateMutexW creates (or opens) a system-wide named mutex.
      - If another instance already owns it, GetLastError() returns
        ERROR_ALREADY_EXISTS (183), meaning we are the second copy.
      - We show a message, then exit immediately.
      - The winning instance keeps the handle open for its whole lifetime;
        Windows automatically releases the mutex when the process exits.
    """
    global _single_instance_mutex
    ERROR_ALREADY_EXISTS = 183

    # Create a mutex named after the app.  The name is arbitrary but must be
    # unique enough not to clash with unrelated programs.
    handle = ctypes.windll.kernel32.CreateMutexW(
        None,               # default security attributes
        False,              # we don't need to own it immediately
        f"Global\\{APP_NAME}_SingleInstance",  # unique system-wide name
    )

    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        # Another instance is already running — tell the user and quit.
        ctypes.windll.user32.MessageBoxW(
            None,
            "Activity Tracker is already running.\n\n"
            "Check the system tray (bottom-right of the taskbar).",
            APP_LABEL,
            0x40 | 0x1000,  # MB_ICONINFORMATION | MB_SYSTEMMODAL
        )
        sys.exit(0)

    # Store the handle so it stays open (and the mutex stays owned) until exit
    _single_instance_mutex = handle


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    # ── Startup sequence ──────────────────────────────────────────────────────
    # Step 0: Abort immediately if another copy is already running.
    _ensure_single_instance()

    # Step 1: Load any data already saved for today so the session continues
    #         rather than starting from zero if the script is restarted mid-day.
    _load_today()

    # Step 2: Register in the Windows startup registry so the tracker launches
    #         automatically when you log in. The user can disable this via the
    #         tray menu ("Toggle Auto-start") at any time.
    _set_autostart(True)

    # Step 3: Start a background thread that listens for keyboard presses.
    #         "daemon=True" means this thread automatically stops when the
    #         main program exits — no zombie processes are left behind.
    kb = keyboard.Listener(on_press=_on_key)
    kb.daemon = True
    kb.start()

    # Step 4: Start a background thread that listens for mouse activity
    #         (movement, clicks, scrolls). This only resets the idle timer —
    #         mouse events do NOT increment the keystroke count.
    ms = mouse.Listener(
        on_move=_on_mouse, on_click=_on_mouse, on_scroll=_on_mouse
    )
    ms.daemon = True
    ms.start()

    # Step 5: Start the main background tracker thread.
    #         This runs every second to accumulate awake time, detect AFK,
    #         handle midnight rollovers, and periodically flush data to disk.
    threading.Thread(target=_tracker, daemon=True, name="tracker").start()

    # Step 6: Start the system tray icon in a separate thread ("detached") so
    #         the main thread is free to run the Tkinter UI (required by Windows).
    # Build the right-click menu for the system tray icon.
    # Each MenuItem maps a label to a function that runs when clicked.
    menu = pystray.Menu(
        pystray.MenuItem("Show Today's Stats",       _show_stats,            default=True),
        pystray.MenuItem("Show Last 7 Days",         _show_history),
        pystray.MenuItem("Analytics Dashboard",      _show_analytics),
        pystray.MenuItem("Top Apps Today",           _show_top_apps),
        pystray.Menu.SEPARATOR,
        # Overlay display controls
        pystray.MenuItem("Toggle Overlay",           _toggle_overlay),        # Show/hide the floating widget
        pystray.MenuItem("Always on Top",            _toggle_always_on_top),  # Keep overlay above all windows
        pystray.MenuItem("Unlock/Lock Overlay",      _toggle_overlay_lock),   # Allow/prevent dragging
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Toggle Auto-start",        _toggle_autostart),      # Start with Windows
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit",                     _exit_app),
    )
    icon = pystray.Icon(APP_NAME, _make_icon(), APP_LABEL, menu)
    icon.run_detached()

    # Step 7: Create and show the desktop overlay widget.
    # This MUST run on the main thread — Tkinter (the Python GUI library) requires
    # all window operations to happen on the thread that created the window.
    # _overlay.run() starts the Tkinter event loop and blocks here until
    # the program exits (i.e. the user clicks "Exit" in the tray menu).
    global _overlay
    _overlay = OverlayWidget()
    _overlay.run()


if __name__ == "__main__":
    main()
