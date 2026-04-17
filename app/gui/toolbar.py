"""
Toolbar widget with file-open buttons, status labels, and view mode selector.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QComboBox, QFrame
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep


class Toolbar(QWidget):
    open_image_requested = pyqtSignal()
    open_lut_requested = pyqtSignal()
    view_mode_changed = pyqtSignal(str)  # "split" | "before" | "after"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._btn_image = QPushButton("Open Image")
        self._btn_image.clicked.connect(self.open_image_requested)
        layout.addWidget(self._btn_image)

        self._lbl_image = QLabel("No image loaded")
        self._lbl_image.setMinimumWidth(160)
        self._lbl_image.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._lbl_image)

        layout.addWidget(_separator())

        self._btn_lut = QPushButton("Open LUT")
        self._btn_lut.clicked.connect(self.open_lut_requested)
        layout.addWidget(self._btn_lut)

        self._lbl_lut = QLabel("No LUT loaded")
        self._lbl_lut.setMinimumWidth(160)
        self._lbl_lut.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._lbl_lut)

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

    def set_processing(self, active: bool):
        self._lbl_status.setText("Applying LUT…" if active else "")
        self._btn_image.setEnabled(not active)
        self._btn_lut.setEnabled(not active)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_view_changed(self, index: int):
        mode = self._combo_view.itemData(index)
        self.view_mode_changed.emit(mode)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return "…" + text[-(max_len - 1):]
