"""
Side-by-side diff viewer dialog.

• Two synchronised QTextEdit panes with per-line background highlighting.
• Prev/Next diff hunk navigation.
• Mark Reviewed / Ignore / Reset action buttons.
"""
from typing import List, Optional, Tuple

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtGui     import (
    QBrush, QColor, QFont,
    QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PyQt5.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollBar, QSizePolicy,
    QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from core.comparator  import compute_side_by_side_diff, diff_hunk_positions, DiffLines
from core.extractor   import extract_text
from core.models      import (
    ResultItem,
    STATUS_IDENTICAL, STATUS_ONLY_A, STATUS_ONLY_B, STATUS_ERROR,
    DECISION_PENDING, DECISION_REVIEWED, DECISION_IGNORED, DECISION_NA,
    STATUS_LABELS,
)

# ── Colour palette ─────────────────────────────────────────────────────────────
_COLOURS: dict[str, QColor] = {
    "equal":   QColor("#FFFFFF"),
    "delete":  QColor("#FFE0E0"),   # light red   – line removed
    "insert":  QColor("#E0FFE0"),   # light green – line added
    "replace": QColor("#FFFFC0"),   # light amber – line changed
    "empty":   QColor("#F5F5F5"),   # light grey  – padding
}

_MONO_FONT = QFont("Consolas", 9)


class _SyncedTextEdit(QTextEdit):
    """QTextEdit with read-only enforced and minimum usable size."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(_MONO_FONT)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(300)


class DiffViewerDialog(QDialog):
    """
    Modal dialog showing a side-by-side diff for one ResultItem.

    Signals
    -------
    decision_made(str, str)
        Emitted with (key, decision) when the user changes the decision.
    """

    decision_made = pyqtSignal(str, str)   # key, decision

    def __init__(self, item: ResultItem, parent=None) -> None:
        super().__init__(parent)
        self.item              = item
        self._hunk_positions:  List[int] = []
        self._current_hunk:    int  = -1
        self._syncing:         bool = False

        self.setWindowTitle(f"Diff Viewer — {item.key}")
        self.resize(1100, 680)
        self.setModal(True)

        self._build_ui()
        self._load_diff()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        status_text = STATUS_LABELS.get(self.item.status, self.item.status)
        hdr.addWidget(QLabel(f"<b>{self.item.key}</b>  —  {status_text}"))
        hdr.addStretch()

        self._hunk_label = QLabel("—")
        hdr.addWidget(self._hunk_label)

        self._prev_btn = QPushButton("◀ Prev Diff")
        self._next_btn = QPushButton("Next Diff ▶")
        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._go_prev_hunk)
        self._next_btn.clicked.connect(self._go_next_hunk)
        hdr.addWidget(self._prev_btn)
        hdr.addWidget(self._next_btn)
        root.addLayout(hdr)

        # ── Pane labels ───────────────────────────────────────────────────────
        label_row = QHBoxLayout()
        lbl_a = QLabel(f"<b>Folder A</b>  {self.item.path_a or '(not present)'}")
        lbl_b = QLabel(f"<b>Folder B</b>  {self.item.path_b or '(not present)'}")
        lbl_a.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl_b.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label_row.addWidget(lbl_a)
        label_row.addWidget(lbl_b)
        root.addLayout(label_row)

        # ── Diff panes ────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        self.pane_a = _SyncedTextEdit()
        self.pane_b = _SyncedTextEdit()
        splitter.addWidget(self.pane_a)
        splitter.addWidget(self.pane_b)
        splitter.setSizes([550, 550])
        root.addWidget(splitter, stretch=1)

        # Synchronised vertical scrolling
        self.pane_a.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(v, self.pane_b)
        )
        self.pane_b.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(v, self.pane_a)
        )

        # ── Action + close buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._mark_reviewed_btn = QPushButton("✔ Mark Reviewed")
        self._ignore_btn        = QPushButton("✖ Ignore")
        self._reset_btn         = QPushButton("↩ Reset to Pending")
        close_btn               = QPushButton("Close")

        self._mark_reviewed_btn.clicked.connect(
            lambda: self._emit_decision(DECISION_REVIEWED)
        )
        self._ignore_btn.clicked.connect(
            lambda: self._emit_decision(DECISION_IGNORED)
        )
        self._reset_btn.clicked.connect(
            lambda: self._emit_decision(DECISION_PENDING)
        )
        close_btn.clicked.connect(self.accept)

        for btn in (self._mark_reviewed_btn, self._ignore_btn, self._reset_btn):
            btn_row.addWidget(btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)
        self._update_action_buttons()

    # ── Diff loading ──────────────────────────────────────────────────────────
    def _load_diff(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._do_load()
        except Exception as exc:
            self.pane_a.setPlainText(f"[Error loading diff]\n{exc}")
            self.pane_b.setPlainText("")
        finally:
            QApplication.restoreOverrideCursor()

    def _do_load(self) -> None:
        item = self.item

        if item.status == STATUS_ERROR:
            self.pane_a.setPlainText(f"Error:\n{item.error_msg or 'Unknown error'}")
            self.pane_b.setPlainText(f"Error:\n{item.error_msg or 'Unknown error'}")
            return

        # Build (lines, tags) for each pane
        if item.status == STATUS_ONLY_A:
            text_a = extract_text(item.path_a)
            la: DiffLines = [(ln, "equal") for ln in text_a.splitlines()]
            lb: DiffLines = [("", "empty")] * len(la)
            self._render(self.pane_b, [("(File not present in Folder B)", "empty")])

        elif item.status == STATUS_ONLY_B:
            text_b = extract_text(item.path_b)
            lb = [(ln, "equal") for ln in text_b.splitlines()]
            la = [("", "empty")] * len(lb)
            self._render(self.pane_a, [("(File not present in Folder A)", "empty")])

        else:
            # STATUS_DIFFERENT or STATUS_IDENTICAL
            text_a = extract_text(item.path_a)
            text_b = extract_text(item.path_b)
            la, lb = compute_side_by_side_diff(text_a, text_b)

        self._render(self.pane_a, la)
        self._render(self.pane_b, lb)

        self._hunk_positions = diff_hunk_positions(la)
        self._update_nav()

        if self._hunk_positions:
            self._jump_to_hunk(0)

    # ── Rendering ─────────────────────────────────────────────────────────────
    @staticmethod
    def _render(pane: QTextEdit, lines: DiffLines) -> None:
        """Populate *pane* with coloured lines."""
        pane.clear()
        doc    = pane.document()
        cursor = QTextCursor(doc)

        char_fmt = QTextCharFormat()
        char_fmt.setFont(_MONO_FONT)

        for i, (text, tag) in enumerate(lines):
            blk_fmt = QTextBlockFormat()
            blk_fmt.setBackground(QBrush(_COLOURS.get(tag, QColor("#FFFFFF"))))

            if i == 0:
                cursor.setBlockFormat(blk_fmt)
                cursor.setCharFormat(char_fmt)
            else:
                cursor.insertBlock(blk_fmt, char_fmt)

            cursor.insertText(text)

        pane.moveCursor(QTextCursor.Start)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _go_prev_hunk(self) -> None:
        if self._current_hunk > 0:
            self._jump_to_hunk(self._current_hunk - 1)

    def _go_next_hunk(self) -> None:
        if self._current_hunk < len(self._hunk_positions) - 1:
            self._jump_to_hunk(self._current_hunk + 1)

    def _jump_to_hunk(self, idx: int) -> None:
        self._current_hunk = idx
        line_no = self._hunk_positions[idx]

        for pane in (self.pane_a, self.pane_b):
            block = pane.document().findBlockByNumber(line_no)
            if block.isValid():
                cur = QTextCursor(block)
                pane.setTextCursor(cur)
                pane.ensureCursorVisible()

        self._update_nav()

    def _update_nav(self) -> None:
        n = len(self._hunk_positions)
        if n == 0:
            self._hunk_label.setText("No differences")
        else:
            self._hunk_label.setText(
                f"Diff {self._current_hunk + 1} / {n}"
            )
        self._prev_btn.setEnabled(self._current_hunk > 0)
        self._next_btn.setEnabled(self._current_hunk < n - 1)

    # ── Scroll sync ───────────────────────────────────────────────────────────
    def _sync_scroll(self, value: int, target: QTextEdit) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            target.verticalScrollBar().setValue(value)
        finally:
            self._syncing = False

    # ── Decision buttons ──────────────────────────────────────────────────────
    def _emit_decision(self, decision: str) -> None:
        self.item.decision = decision
        self._update_action_buttons()
        self.decision_made.emit(self.item.key, decision)

    def _update_action_buttons(self) -> None:
        na = self.item.decision == DECISION_NA
        self._mark_reviewed_btn.setEnabled(not na)
        self._ignore_btn.setEnabled(not na)
        self._reset_btn.setEnabled(not na and self.item.decision != DECISION_PENDING)
