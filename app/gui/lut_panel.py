"""
Right-sidebar panel for managing multiple loaded LUTs.

Users add one or more .cube files, then click items in the list to
switch which LUT is shown in the main split view. All LUTs are
processed in parallel background threads; pending items show a
"(…)" suffix until their result is ready.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog, QFrame
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont, QColor

LUT_FILTER = "LUT Files (*.cube)"


class LUTPanel(QWidget):
    """
    Signals
    -------
    luts_add_requested   : list[str] of filepaths chosen via dialog
    lut_selected         : filepath when the user clicks a list item
    lut_remove_requested : filepath of the item the user wants to remove
    """

    luts_add_requested = pyqtSignal(list)
    lut_selected = pyqtSignal(str)
    lut_remove_requested = pyqtSignal(str)
    remove_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, QListWidgetItem] = {}  # filepath → list item
        self._active_path: str | None = None
        self._build_ui()
        self.setFixedWidth(210)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)

        header = QLabel("LUTs")
        bold = QFont()
        bold.setBold(True)
        header.setFont(bold)
        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_add = QPushButton("Add LUT(s)…")
        self._btn_add.clicked.connect(self._on_add_clicked)
        btn_row.addWidget(self._btn_add, stretch=1)

        self._btn_remove = QPushButton("Remove")
        self._btn_remove.setEnabled(False)
        self._btn_remove.clicked.connect(self._on_remove_clicked)
        btn_row.addWidget(self._btn_remove)

        layout.addLayout(btn_row)

        self._btn_remove_all = QPushButton("Remove All")
        self._btn_remove_all.setEnabled(False)
        self._btn_remove_all.clicked.connect(self._on_remove_all_clicked)
        layout.addWidget(self._btn_remove_all)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_lut(self, filepath: str, name: str):
        """Add a LUT entry (or reset existing one to pending state).

        Signals are blocked during addItem to prevent currentItemChanged from
        firing re-entrantly while the caller is still populating the list.
        Call set_active() explicitly after all items are added.
        """
        if filepath in self._items:
            # Reset existing item to pending state (new image loaded)
            item = self._items[filepath]
            item.setText(f"{name} (…)")
            item.setForeground(QColor(128, 128, 128))
            f = item.font()
            f.setBold(False)
            item.setFont(f)
            return
        item = QListWidgetItem(f"{name} (…)")
        item.setData(Qt.UserRole, filepath)
        item.setForeground(QColor(128, 128, 128))
        self._list.blockSignals(True)
        self._list.addItem(item)
        self._list.blockSignals(False)
        self._items[filepath] = item
        self._btn_remove.setEnabled(True)
        self._btn_remove_all.setEnabled(True)

    def mark_ready(self, filepath: str):
        """Remove the pending indicator from a LUT entry."""
        item = self._items.get(filepath)
        if item is None:
            return
        item.setText(os.path.basename(filepath))
        item.setData(Qt.ForegroundRole, None)
        self._update_active_font()

    def remove_lut(self, filepath: str):
        """Remove a LUT entry from the list."""
        item = self._items.pop(filepath, None)
        if item is None:
            return
        row = self._list.row(item)
        self._list.takeItem(row)
        if filepath == self._active_path:
            self._active_path = None
        has_items = self._list.count() > 0
        self._btn_remove.setEnabled(has_items)
        self._btn_remove_all.setEnabled(has_items)

    def set_active(self, filepath: str):
        """Highlight the given entry as the currently displayed LUT."""
        self._active_path = filepath
        item = self._items.get(filepath)
        if item:
            self._list.blockSignals(True)
            self._list.setCurrentItem(item)
            self._list.blockSignals(False)
        self._update_active_font()

    def clear(self):
        """Remove all LUT entries."""
        self._list.clear()
        self._items.clear()
        self._active_path = None
        self._btn_remove.setEnabled(False)
        self._btn_remove_all.setEnabled(False)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_add_clicked(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add LUT Files", "", LUT_FILTER
        )
        if paths:
            self.luts_add_requested.emit(paths)

    def _on_remove_clicked(self):
        item = self._list.currentItem()
        if item:
            filepath = item.data(Qt.UserRole)
            self.lut_remove_requested.emit(filepath)

    def _on_remove_all_clicked(self):
        self.remove_all_requested.emit()

    def _on_current_changed(self, current: QListWidgetItem, previous):
        if current is None:
            return
        filepath = current.data(Qt.UserRole)
        self.lut_selected.emit(filepath)

    def _update_active_font(self):
        for path, item in self._items.items():
            f = item.font()
            f.setBold(path == self._active_path)
            item.setFont(f)
