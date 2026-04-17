"""
Toolbar widget with file-open buttons, status labels, and view mode selector.

Both "Open Image" and "Open LUT" are QToolButtons with a dropdown arrow that
shows a persistent recent-files history (backed by QSettings via RecentFiles).
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QFrame, QToolButton, QMenu, QPushButton
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from app.history import RecentFiles


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep


class Toolbar(QWidget):
    open_image_requested = pyqtSignal()
    open_lut_requested = pyqtSignal()
    export_requested = pyqtSignal()
    view_mode_changed = pyqtSignal(str)      # "split" | "before" | "after"
    recent_image_selected = pyqtSignal(str)  # path chosen from image history
    recent_lut_selected = pyqtSignal(str)    # path chosen from LUT history

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_history = RecentFiles("images")
        self._lut_history = RecentFiles("luts")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._btn_image = QToolButton()
        self._btn_image.setText("Open Image")
        self._btn_image.setPopupMode(QToolButton.MenuButtonPopup)
        self._btn_image.clicked.connect(self.open_image_requested)
        self._refresh_image_menu()
        layout.addWidget(self._btn_image)

        self._lbl_image = QLabel("No image loaded")
        self._lbl_image.setMinimumWidth(160)
        self._lbl_image.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._lbl_image)

        layout.addWidget(_separator())

        self._btn_lut = QToolButton()
        self._btn_lut.setText("Open LUT")
        self._btn_lut.setPopupMode(QToolButton.MenuButtonPopup)
        self._btn_lut.clicked.connect(self.open_lut_requested)
        self._refresh_lut_menu()
        layout.addWidget(self._btn_lut)

        self._lbl_lut = QLabel("No LUT loaded")
        self._lbl_lut.setMinimumWidth(160)
        self._lbl_lut.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._lbl_lut)

        layout.addWidget(_separator())

        self._btn_export = QPushButton("Export…")
        self._btn_export.clicked.connect(self.export_requested)
        self._btn_export.setEnabled(False)
        layout.addWidget(self._btn_export)

        layout.addWidget(_separator())

        lbl_view = QLabel("View:")
        layout.addWidget(lbl_view)

        self._combo_view = QComboBox()
        self._combo_view.addItem("Split View", "split")
        self._combo_view.addItem("Before Only", "before")
        self._combo_view.addItem("After Only", "after")
        self._combo_view.currentIndexChanged.connect(self._on_view_changed)
        layout.addWidget(self._combo_view)

        layout.addWidget(_separator())

        self._lbl_status = QLabel("")
        italic_font = QFont()
        italic_font.setItalic(True)
        self._lbl_status.setFont(italic_font)
        self._lbl_status.setStyleSheet("color: #888888;")
        layout.addWidget(self._lbl_status)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image_label(self, name: str):
        self._lbl_image.setText(self._truncate(name, 28))
        self._lbl_image.setToolTip(name)

    def set_lut_label(self, name: str):
        self._lbl_lut.setText(self._truncate(name, 28))
        self._lbl_lut.setToolTip(name)

    def set_export_enabled(self, enabled: bool):
        self._btn_export.setEnabled(enabled)

    def set_processing(self, active: bool):
        self._lbl_status.setText("Applying LUT…" if active else "")
        self._btn_image.setEnabled(not active)
        self._btn_lut.setEnabled(not active)
        if active:
            self._btn_export.setEnabled(False)

    def add_recent_image(self, path: str):
        self._image_history.add(path)
        self._refresh_image_menu()

    def add_recent_lut(self, path: str):
        self._lut_history.add(path)
        self._refresh_lut_menu()

    # ------------------------------------------------------------------
    # Private: menu builders
    # ------------------------------------------------------------------

    def _refresh_image_menu(self):
        menu = QMenu(self)
        paths = self._image_history.paths()
        if paths:
            for p in paths:
                action = menu.addAction(self._truncate(os.path.basename(p), 50))
                action.setToolTip(p)
                action.triggered.connect(
                    lambda checked, path=p: self.recent_image_selected.emit(path)
                )
            menu.addSeparator()
            clear = menu.addAction("Clear History")
            clear.triggered.connect(self._clear_image_history)
        else:
            no_recent = menu.addAction("No recent files")
            no_recent.setEnabled(False)
        self._btn_image.setMenu(menu)

    def _refresh_lut_menu(self):
        menu = QMenu(self)
        paths = self._lut_history.paths()
        if paths:
            for p in paths:
                action = menu.addAction(self._truncate(os.path.basename(p), 50))
                action.setToolTip(p)
                action.triggered.connect(
                    lambda checked, path=p: self.recent_lut_selected.emit(path)
                )
            menu.addSeparator()
            clear = menu.addAction("Clear History")
            clear.triggered.connect(self._clear_lut_history)
        else:
            no_recent = menu.addAction("No recent files")
            no_recent.setEnabled(False)
        self._btn_lut.setMenu(menu)

    def _clear_image_history(self):
        self._image_history.clear()
        self._refresh_image_menu()

    def _clear_lut_history(self):
        self._lut_history.clear()
        self._refresh_lut_menu()

    def _on_view_changed(self, index: int):
        mode = self._combo_view.itemData(index)
        self.view_mode_changed.emit(mode)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return "…" + text[-(max_len - 1):]
