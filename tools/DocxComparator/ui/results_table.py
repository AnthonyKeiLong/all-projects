"""
Results table widget.

Displays comparison results in a sortable table.  All row-mutation is
key-based so that sorting does not break item lookup.
"""
from typing import List, Optional

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtGui     import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QAction, QHeaderView,
    QMenu, QTableWidget, QTableWidgetItem,
)

from core.models import (
    ResultItem,
    STATUS_LABELS, DECISION_LABELS, STATUS_COLORS,
    STATUS_IDENTICAL, DECISION_NA,
    DECISION_PENDING, DECISION_REVIEWED, DECISION_IGNORED,
)

# ── Column indices ─────────────────────────────────────────────────────────────
COL_KEY      = 0
COL_STATUS   = 1
COL_DECISION = 2
COL_PATH_A   = 3
COL_PATH_B   = 4

_HEADERS = ["Filename / Key", "Status", "Decision", "Path A", "Path B"]

# ── Data roles ─────────────────────────────────────────────────────────────────
_KEY_ROLE = Qt.UserRole           # stores the result key string in every cell


class ResultsTable(QTableWidget):
    """
    Sortable table that shows one ResultItem per row.

    Signals
    -------
    view_diff_requested(ResultItem)
        Emitted when the user wants to open the diff viewer.
    decision_changed(str, str)
        Emitted with (key, new_decision) after the user updates a decision.
    """

    view_diff_requested = pyqtSignal(object)    # ResultItem
    decision_changed    = pyqtSignal(str, str)  # key, decision

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(_HEADERS), parent)
        self._items: List[ResultItem] = []
        self._setup_ui()

    # ── Setup ─────────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        self.setHorizontalHeaderLabels(_HEADERS)

        hh = self.horizontalHeader()
        # All columns are freely resizable by dragging the header dividers.
        # ResizeToContents / Stretch modes both block interactive resizing,
        # so every column uses Interactive instead.
        for col in range(len(_HEADERS)):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)

        # Sensible default widths; user can drag to taste.
        self.setColumnWidth(COL_KEY,      220)
        self.setColumnWidth(COL_STATUS,   100)
        self.setColumnWidth(COL_DECISION, 100)
        self.setColumnWidth(COL_PATH_A,   260)
        self.setColumnWidth(COL_PATH_B,   260)

        # Let the last column absorb any remaining horizontal space.
        hh.setStretchLastSection(True)

        # Double-clicking a header divider auto-fits that column to its content.
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.verticalHeader().setDefaultSectionSize(26)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setSortingEnabled(True)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_click)

    # ── Public API ────────────────────────────────────────────────────────────
    def add_result(self, item: ResultItem) -> None:
        """Append a new result row (safe to call from the main thread)."""
        self._items.append(item)
        self._insert_row(item)

    def update_item(self, key: str, item: ResultItem) -> None:
        """Refresh the row that matches *key*."""
        for idx, existing in enumerate(self._items):
            if existing.key == key:
                self._items[idx] = item
                break
        self._refresh_visual_row(key, item)

    def get_all_items(self) -> List[ResultItem]:
        return list(self._items)

    def set_items(self, items: List[ResultItem]) -> None:
        """Bulk-load items (e.g. after loading a session)."""
        self.clear_all()
        for item in items:
            self.add_result(item)

    def begin_bulk_insert(self) -> None:
        """Call before a batch of add_result() calls (e.g. during a scan).

        Disables sorting and defers visual updates so the table stays
        responsive and doesn't re-sort the entire list on every new row.
        """
        self.setSortingEnabled(False)
        self.setUpdatesEnabled(False)

    def end_bulk_insert(self) -> None:
        """Call after a batch of add_result() calls to restore normal behaviour."""
        self.setUpdatesEnabled(True)
        self.setSortingEnabled(True)

    def clear_all(self) -> None:
        self.setRowCount(0)
        self._items.clear()

    def get_selected_item(self) -> Optional[ResultItem]:
        """Return the ResultItem for the currently selected row, or None."""
        rows = self.selectionModel().selectedRows()
        if not rows:
            return None
        key = self._key_from_visual_row(rows[0].row())
        return self._item_by_key(key) if key else None

    def get_summary(self) -> dict:
        summary: dict = {}
        for item in self._items:
            summary[item.status] = summary.get(item.status, 0) + 1
        return summary

    # ── Row population ────────────────────────────────────────────────────────
    def _insert_row(self, item: ResultItem) -> None:
        # Sorting must already be disabled (via begin_bulk_insert) during a
        # scan.  Toggling setSortingEnabled per-row causes a full re-sort on
        # every insertion — O(n² log n) for a complete scan.
        row = self.rowCount()
        self.insertRow(row)
        self._fill_row(row, item)

    def _fill_row(self, row: int, item: ResultItem) -> None:
        bg   = QColor(STATUS_COLORS.get(item.status, "#ffffff"))
        brush = QBrush(bg)

        def cell(text: str) -> QTableWidgetItem:
            wi = QTableWidgetItem(text)
            wi.setBackground(brush)
            wi.setData(_KEY_ROLE, item.key)
            return wi

        self.setItem(row, COL_KEY,      cell(item.key))
        self.setItem(row, COL_STATUS,   cell(STATUS_LABELS.get(item.status,   item.status)))
        self.setItem(row, COL_DECISION, cell(DECISION_LABELS.get(item.decision, item.decision)))
        self.setItem(row, COL_PATH_A,   cell(item.path_a or "—"))
        self.setItem(row, COL_PATH_B,   cell(item.path_b or "—"))

    def _refresh_visual_row(self, key: str, item: ResultItem) -> None:
        for vrow in range(self.rowCount()):
            if self._key_from_visual_row(vrow) == key:
                self._fill_row(vrow, item)
                return

    def _key_from_visual_row(self, visual_row: int) -> Optional[str]:
        wi = self.item(visual_row, COL_KEY)
        return wi.data(_KEY_ROLE) if wi else None

    def _item_by_key(self, key: str) -> Optional[ResultItem]:
        for item in self._items:
            if item.key == key:
                return item
        return None

    # ── Interactions ──────────────────────────────────────────────────────────
    def _on_double_click(self, index) -> None:
        key  = self._key_from_visual_row(index.row())
        item = self._item_by_key(key) if key else None
        if item and item.status != STATUS_IDENTICAL:
            self.view_diff_requested.emit(item)

    def _show_context_menu(self, pos) -> None:
        row = self.rowAt(pos.y())
        if row < 0:
            return
        key  = self._key_from_visual_row(row)
        item = self._item_by_key(key) if key else None
        if not item:
            return

        menu = QMenu(self)

        if item.status != STATUS_IDENTICAL:
            a = QAction("View Diff", self)
            a.triggered.connect(lambda: self.view_diff_requested.emit(item))
            menu.addAction(a)
            menu.addSeparator()

        if item.decision != DECISION_NA:
            def _make_set(d):
                return lambda: self._apply_decision(item.key, d)

            if item.decision != DECISION_REVIEWED:
                a = QAction("Mark as Reviewed", self)
                a.triggered.connect(_make_set(DECISION_REVIEWED))
                menu.addAction(a)

            if item.decision != DECISION_IGNORED:
                a = QAction("Ignore", self)
                a.triggered.connect(_make_set(DECISION_IGNORED))
                menu.addAction(a)

            if item.decision != DECISION_PENDING:
                a = QAction("Reset to Pending", self)
                a.triggered.connect(_make_set(DECISION_PENDING))
                menu.addAction(a)

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(pos))

    def _apply_decision(self, key: str, decision: str) -> None:
        item = self._item_by_key(key)
        if not item:
            return
        item.decision = decision
        self._refresh_visual_row(key, item)
        self.decision_changed.emit(key, decision)
