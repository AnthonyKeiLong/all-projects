"""
Background worker thread: scans and compares .docx and .doc file pairs without
blocking the main (UI) thread.
"""
import contextlib
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

from core.extractor import extract_text, word_session as _word_session
from core.comparator import compare_texts
from core.models import (
    ResultItem,
    STATUS_IDENTICAL, STATUS_DIFFERENT,
    STATUS_ONLY_A,    STATUS_ONLY_B,
    STATUS_ERROR,
    DECISION_PENDING, DECISION_NA,
)


class ScanWorker(QThread):
    """
    Compares a pre-computed list of file pairs on a worker thread.

    Signals
    -------
    progress(int)
        0–100 completion percentage.
    result_ready(dict)
        Emitted for every file pair; payload is ``ResultItem.to_dict()``.
    status_message(str)
        Short human-readable status line (e.g., currently processed filename).
    finished_scan(int, int)
        Emitted once when done: (total_pairs, different_count).
    scan_error(str)
        Emitted if a *fatal* error prevents the scan from starting.
    """

    progress       = pyqtSignal(int)
    result_ready   = pyqtSignal(dict)
    status_message = pyqtSignal(str)
    finished_scan  = pyqtSignal(int, int)
    scan_error     = pyqtSignal(str)

    def __init__(
        self,
        pairs: List[Tuple[str, Optional[Path], Optional[Path]]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pairs = pairs
        self._abort = False

    def abort(self) -> None:
        """Request a graceful stop after the current file."""
        self._abort = True

    # ── QThread entry point ───────────────────────────────────────────────────
    def run(self) -> None:
        total     = len(self._pairs)
        different = 0

        try:
            # Open a single Word.Application session for the whole scan when any
            # .doc files are present.  Falls back to nullcontext (word_app=None)
            # when pywin32 is not installed or no .doc files are included.
            has_doc = any(
                (pa is not None and str(pa).lower().endswith(".doc")) or
                (pb is not None and str(pb).lower().endswith(".doc"))
                for _, pa, pb in self._pairs
            )
            ctx = _word_session() if has_doc else contextlib.nullcontext(None)

            with ctx as word_app:
                for idx, (key, path_a, path_b) in enumerate(self._pairs):
                    if self._abort:
                        break

                    self.status_message.emit(f"Comparing: {key}")
                    item = self._process_pair(key, path_a, path_b, word_app=word_app)

                    if item.status == STATUS_DIFFERENT:
                        different += 1

                    self.result_ready.emit(item.to_dict())
                    self.progress.emit(int((idx + 1) / total * 100) if total else 100)

        except Exception as exc:
            self.scan_error.emit(f"Unexpected error during scan: {exc}")

        finally:
            # Always emitted — guarantees the UI is never left in a locked state.
            self.finished_scan.emit(total, different)

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _process_pair(
        self,
        key:      str,
        path_a:   Optional[Path],
        path_b:   Optional[Path],
        word_app: object = None,
    ) -> ResultItem:

        # One side missing
        if path_a is None:
            return ResultItem(
                key=key, path_a=None, path_b=str(path_b), status=STATUS_ONLY_B
            )
        if path_b is None:
            return ResultItem(
                key=key, path_a=str(path_a), path_b=None, status=STATUS_ONLY_A
            )

        # Extract text from both files
        try:
            text_a = extract_text(str(path_a), word_app=word_app)
        except Exception as exc:
            return ResultItem(
                key=key, path_a=str(path_a), path_b=str(path_b),
                status=STATUS_ERROR,
                error_msg=f"Folder A read error: {exc}",
            )

        try:
            text_b = extract_text(str(path_b), word_app=word_app)
        except Exception as exc:
            return ResultItem(
                key=key, path_a=str(path_a), path_b=str(path_b),
                status=STATUS_ERROR,
                error_msg=f"Folder B read error: {exc}",
            )

        status   = compare_texts(text_a, text_b)
        decision = DECISION_NA if status == STATUS_IDENTICAL else DECISION_PENDING

        return ResultItem(
            key=key, path_a=str(path_a), path_b=str(path_b),
            status=status, decision=decision,
        )
