"""
Main application window.

Layout
------
  ┌────────────────────────────────────────────────────┐
  │  MenuBar                                           │
  ├────────────────────────────────────────────────────┤
  │  Folder A: [__________________] [Browse]           │
  │  Folder B: [__________________] [Browse]           │
  │  [✓] Recursive    Match by: [Filename ▾]           │
  ├────────────────────────────────────────────────────┤
  │  [Scan]  [Stop]    ████████░░░░  42%               │
  ├────────────────────────────────────────────────────┤
  │  Filter: [All ▾]  [___search___]  [View Diff]      │
  │  ┌────────┬────────────┬──────────┬───┬───┐        │
  │  │Filename│ Status     │ Decision │ A │ B │        │
  │  ├────────┼────────────┼──────────┼───┼───┤        │
  │  │  ...   │  ...       │  ...     │   │   │        │
  │  └────────┴────────────┴──────────┴───┴───┘        │
  ├────────────────────────────────────────────────────┤
  │  [Export CSV]  [Save Session]  [Load Session]      │
  ├────────────────────────────────────────────────────┤
  │  Status bar                                        │
  └────────────────────────────────────────────────────┘
"""
from typing import List, Optional

from PyQt5.QtCore    import Qt
from PyQt5.QtWidgets import (
    QAction, QApplication, QComboBox, QCheckBox,
    QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenuBar, QMessageBox,
    QProgressBar, QPushButton, QSizePolicy,
    QStatusBar, QVBoxLayout, QWidget,
)

from core.exporter import export_csv
from core.models   import (
    ResultItem,
    STATUS_IDENTICAL, STATUS_DIFFERENT,
    STATUS_ONLY_A, STATUS_ONLY_B, STATUS_ERROR,
    STATUS_LABELS,
    DECISION_PENDING, DECISION_REVIEWED, DECISION_IGNORED,
)
from core.scanner  import match_files
from core.session  import load_session, save_session

from ui.diff_viewer    import DiffViewerDialog
from ui.results_table  import ResultsTable
from ui.scan_worker    import ScanWorker


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        self._worker:  Optional[ScanWorker] = None
        self._results: List[ResultItem] = []

        self.setWindowTitle("DocxComparator")
        self.resize(1000, 660)

        self._build_ui()
        self._build_menus()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 6)

        root.addWidget(self._build_folder_group())
        root.addWidget(self._build_scan_group())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_bottom_bar())

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

    def _build_folder_group(self) -> QGroupBox:
        box = QGroupBox("Folders")
        lay = QVBoxLayout(box)
        lay.setSpacing(4)

        def _row(label: str) -> tuple:
            h = QHBoxLayout()
            h.addWidget(QLabel(f"{label}:"), stretch=0)
            edit = QLineEdit()
            edit.setPlaceholderText("Select folder…")
            h.addWidget(edit, stretch=1)
            btn = QPushButton("Browse…")
            btn.setFixedWidth(80)
            h.addWidget(btn)
            lay.addLayout(h)
            return edit, btn

        self._folder_a_edit, btn_a = _row("Folder A")
        self._folder_b_edit, btn_b = _row("Folder B")

        btn_a.clicked.connect(lambda: self._browse_folder(self._folder_a_edit))
        btn_b.clicked.connect(lambda: self._browse_folder(self._folder_b_edit))

        # Options row
        opt = QHBoxLayout()
        self._recursive_chk = QCheckBox("Recursive (include sub-folders)")
        self._recursive_chk.setChecked(True)
        opt.addWidget(self._recursive_chk)
        opt.addSpacing(20)
        opt.addWidget(QLabel("Match by:"))
        self._match_combo = QComboBox()
        self._match_combo.addItems(["Filename", "Relative path"])
        self._match_combo.setFixedWidth(140)
        opt.addWidget(self._match_combo)
        opt.addStretch()
        lay.addLayout(opt)

        return box

    def _build_scan_group(self) -> QGroupBox:
        box = QGroupBox("Scan")
        h   = QHBoxLayout(box)

        self._scan_btn = QPushButton("▶  Scan")
        self._scan_btn.setFixedWidth(90)
        self._scan_btn.clicked.connect(self._start_scan)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedWidth(90)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scan)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")

        h.addWidget(self._scan_btn)
        h.addWidget(self._stop_btn)
        h.addWidget(self._progress, stretch=1)

        return box

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        h   = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)

        h.addWidget(QLabel("Filter:"))
        self._status_filter = QComboBox()
        self._status_filter.addItem("All statuses", None)
        for k, v in STATUS_LABELS.items():
            self._status_filter.addItem(v, k)
        self._status_filter.setFixedWidth(130)
        self._status_filter.currentIndexChanged.connect(self._apply_filter)
        h.addWidget(self._status_filter)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search filename…")
        self._search_edit.setFixedWidth(200)
        self._search_edit.textChanged.connect(self._apply_filter)
        h.addWidget(self._search_edit)

        h.addSpacing(12)

        self._view_diff_btn = QPushButton("View Diff")
        self._view_diff_btn.setEnabled(False)
        self._view_diff_btn.clicked.connect(self._view_selected_diff)
        h.addWidget(self._view_diff_btn)

        self._mark_btn = QPushButton("Mark Reviewed")
        self._mark_btn.setEnabled(False)
        self._mark_btn.clicked.connect(
            lambda: self._set_selected_decision(DECISION_REVIEWED)
        )
        h.addWidget(self._mark_btn)

        self._ignore_btn = QPushButton("Ignore")
        self._ignore_btn.setEnabled(False)
        self._ignore_btn.clicked.connect(
            lambda: self._set_selected_decision(DECISION_IGNORED)
        )
        h.addWidget(self._ignore_btn)

        h.addStretch()
        return bar

    def _build_table(self) -> ResultsTable:
        self._table = ResultsTable()
        self._table.view_diff_requested.connect(self._open_diff_viewer)
        self._table.decision_changed.connect(self._on_decision_changed)
        self._table.selectionModel().selectionChanged.connect(
            self._on_table_selection
        )
        return self._table

    def _build_bottom_bar(self) -> QHBoxLayout:
        h = QHBoxLayout()

        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._export_csv)

        save_btn = QPushButton("Save Session…")
        save_btn.clicked.connect(self._save_session)

        load_btn = QPushButton("Load Session…")
        load_btn.clicked.connect(self._load_session)

        for btn in (export_btn, save_btn, load_btn):
            btn.setFixedWidth(130)
            h.addWidget(btn)

        h.addStretch()
        return h

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")

        a_save = QAction("Save Session…", self)
        a_save.setShortcut("Ctrl+S")
        a_save.triggered.connect(self._save_session)

        a_load = QAction("Load Session…", self)
        a_load.setShortcut("Ctrl+O")
        a_load.triggered.connect(self._load_session)

        a_export = QAction("Export CSV…", self)
        a_export.setShortcut("Ctrl+E")
        a_export.triggered.connect(self._export_csv)

        a_exit = QAction("Exit", self)
        a_exit.setShortcut("Ctrl+Q")
        a_exit.triggered.connect(self.close)

        file_menu.addAction(a_save)
        file_menu.addAction(a_load)
        file_menu.addSeparator()
        file_menu.addAction(a_export)
        file_menu.addSeparator()
        file_menu.addAction(a_exit)

        # Help menu
        help_menu = mb.addMenu("&Help")
        a_about = QAction("About", self)
        a_about.triggered.connect(self._show_about)
        help_menu.addAction(a_about)

    # ── Folder browsing ───────────────────────────────────────────────────────
    @staticmethod
    def _browse_folder(edit: QLineEdit) -> None:
        start = edit.text() or "."
        folder = QFileDialog.getExistingDirectory(
            None, "Select Folder", start,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if folder:
            edit.setText(folder)

    # ── Scanning ──────────────────────────────────────────────────────────────
    def _start_scan(self) -> None:
        folder_a = self._folder_a_edit.text().strip()
        folder_b = self._folder_b_edit.text().strip()

        if not folder_a or not folder_b:
            QMessageBox.warning(
                self, "Missing Folders",
                "Please select both Folder A and Folder B before scanning.",
            )
            return

        recursive = self._recursive_chk.isChecked()
        match_by  = (
            "filename"
            if self._match_combo.currentIndex() == 0
            else "relative_path"
        )

        try:
            pairs = match_files(folder_a, folder_b, recursive, match_by)
        except Exception as exc:
            QMessageBox.critical(self, "Scan Error", str(exc))
            return

        if not pairs:
            QMessageBox.information(
                self, "No Files Found",
                "No .docx files were found in the selected folders.",
            )
            return

        # Reset state
        self._table.clear_all()
        self._results.clear()
        self._progress.setValue(0)
        self._search_edit.clear()
        self._status_filter.setCurrentIndex(0)

        # Configure worker
        self._worker = ScanWorker(pairs)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished_scan.connect(self._on_scan_finished)
        self._worker.scan_error.connect(self._on_scan_error)
        self._worker.status_message.connect(self.statusBar().showMessage)
        # deleteLater ensures Qt only destroys the C++ thread object after the
        # OS thread has fully exited, preventing a race condition crash.
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.finished.connect(self._on_worker_done)

        self._scan_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self.statusBar().showMessage("Scanning…")

        self._table.begin_bulk_insert()
        self._worker.start()

    def _stop_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.abort()
            self.statusBar().showMessage("Stopping…")

    # ── Worker slots ──────────────────────────────────────────────────────────
    def _on_result(self, result_dict: dict) -> None:
        item = ResultItem.from_dict(result_dict)
        self._results.append(item)
        self._table.add_result(item)
        # Filter is applied once when the scan finishes, not per-row.
        # Calling _apply_filter() here would be O(n²) for large scans.

    def _on_scan_finished(self, total: int, different: int) -> None:
        self._scan_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setValue(100)
        # Re-enable sorting and repaint the table, then apply any active filter.
        self._table.end_bulk_insert()
        self._apply_filter()

        pending = sum(
            1 for it in self._results
            if it.decision == DECISION_PENDING
        )
        self.statusBar().showMessage(
            f"Done — {total} file(s) scanned, "
            f"{different} different, {pending} pending review."
        )

    def _on_worker_done(self) -> None:
        """Called when the QThread has fully stopped (after finished_scan).
        Releases the Python reference safely after Qt has cleaned up."""
        self._worker = None

    def _on_scan_error(self, msg: str) -> None:
        # finished_scan is always emitted after scan_error (try/finally in
        # run()), so end_bulk_insert() and re-enabling the scan button both
        # happen there.  Just surface the error to the user.
        QMessageBox.critical(self, "Scan Error", msg)

    # ── Diff viewer ───────────────────────────────────────────────────────────
    def _open_diff_viewer(self, item: ResultItem) -> None:
        dlg = DiffViewerDialog(item, parent=self)
        dlg.decision_made.connect(self._on_decision_changed)
        dlg.exec_()
        # Refresh row in case decision changed inside the dialog
        self._table.update_item(item.key, item)
        self._update_filter_row_visibility(item)

    def _view_selected_diff(self) -> None:
        item = self._table.get_selected_item()
        if item and item.status != STATUS_IDENTICAL:
            self._open_diff_viewer(item)

    # ── Decision handling ─────────────────────────────────────────────────────
    def _on_decision_changed(self, key: str, decision: str) -> None:
        for item in self._results:
            if item.key == key:
                item.decision = decision
                self._table.update_item(key, item)
                break

    def _set_selected_decision(self, decision: str) -> None:
        item = self._table.get_selected_item()
        if item:
            self._on_decision_changed(item.key, decision)

    # ── Filter / search ───────────────────────────────────────────────────────
    def _apply_filter(self) -> None:
        status_filter = self._status_filter.currentData()   # None = all
        search_text   = self._search_edit.text().lower()

        for vrow in range(self._table.rowCount()):
            key_item = self._table.item(vrow, 0)
            if key_item is None:
                continue
            key    = key_item.text()
            # Retrieve matching ResultItem
            item   = self._table._item_by_key(key)
            if item is None:
                continue

            visible = True
            if status_filter and item.status != status_filter:
                visible = False
            if search_text and search_text not in key.lower():
                visible = False

            self._table.setRowHidden(vrow, not visible)

    def _update_filter_row_visibility(self, item: ResultItem) -> None:
        """Re-evaluate one item's row visibility after a decision change."""
        self._apply_filter()

    # ── Table selection ───────────────────────────────────────────────────────
    def _on_table_selection(self) -> None:
        item = self._table.get_selected_item()
        has_item   = item is not None
        can_diff   = has_item and item.status != STATUS_IDENTICAL
        has_decision = has_item and item.decision not in (None, "n/a")

        self._view_diff_btn.setEnabled(can_diff)
        self._mark_btn.setEnabled(has_decision)
        self._ignore_btn.setEnabled(has_decision)

    # ── Export & session ──────────────────────────────────────────────────────
    def _export_csv(self) -> None:
        if not self._results:
            QMessageBox.information(self, "No Data", "Nothing to export yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Results as CSV", "docx_comparison.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            n = export_csv(path, self._results)
            self.statusBar().showMessage(f"Exported {n} row(s) to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _save_session(self) -> None:
        if not self._results:
            QMessageBox.information(self, "No Data", "Nothing to save yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session", "session.json", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            save_session(
                path,
                self._folder_a_edit.text(),
                self._folder_b_edit.text(),
                self._recursive_chk.isChecked(),
                "filename" if self._match_combo.currentIndex() == 0 else "relative_path",
                self._results,
            )
            self.statusBar().showMessage(f"Session saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _load_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            data = load_session(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        self._folder_a_edit.setText(data["folder_a"])
        self._folder_b_edit.setText(data["folder_b"])
        self._recursive_chk.setChecked(data["recursive"])
        idx = 0 if data["match_by"] == "filename" else 1
        self._match_combo.setCurrentIndex(idx)

        self._results = data["results"]
        self._table.set_items(self._results)
        self.statusBar().showMessage(
            f"Session loaded — {len(self._results)} result(s)."
        )

    # ── About ─────────────────────────────────────────────────────────────────
    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About DocxComparator",
            "<b>DocxComparator</b><br><br>"
            "Compare Word (.docx) documents between two folders.<br>"
            "Differences are flagged for manual review.<br><br>"
            "Dependencies: PyQt5, python-docx",
        )

    # ── Window close guard ────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Scan in progress",
                "A scan is still running. Stop it and exit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self._worker.abort()
            self._worker.wait(3000)
        event.accept()
