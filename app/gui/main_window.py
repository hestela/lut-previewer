"""
Main application window.

Wires together the toolbar, image viewer, and background LUT worker.
"""

import os
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox, QStatusBar
)
from PyQt5.QtCore import Qt

from app.lut import LUT3D, parse_cube, LUTParseError
from app.image_loader import load_image, ImageLoadError, IMAGE_FILTER, array_to_qpixmap
from app.worker import LUTWorker, ExportWorker
from app.gui.toolbar import Toolbar
from app.gui.image_viewer import ImageViewer

LUT_FILTER = "LUT Files (*.cube)"
EXPORT_FILTER = "JPEG (*.jpg *.jpeg);;PNG (*.png);;TIFF (*.tif *.tiff)"
RAW_EXTENSIONS = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._lut: LUT3D | None = None
        self._image_filepath: str | None = None
        self._original_array: np.ndarray | None = None
        self._processed_array: np.ndarray | None = None
        self._worker: LUTWorker | None = None
        self._export_worker: ExportWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toolbar = Toolbar()
        self._toolbar.open_image_requested.connect(self._on_open_image)
        self._toolbar.open_lut_requested.connect(self._on_open_lut)
        self._toolbar.export_requested.connect(self._on_export)
        self._toolbar.view_mode_changed.connect(self._on_view_mode_changed)
        self._toolbar.recent_image_selected.connect(self._load_image_file)
        self._toolbar.recent_lut_selected.connect(self._load_lut_file)
        layout.addWidget(self._toolbar)

        self._viewer = ImageViewer()
        layout.addWidget(self._viewer)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", IMAGE_FILTER
        )
        if path:
            self._load_image_file(path)

    def _on_open_lut(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LUT File", "", LUT_FILTER
        )
        if path:
            self._load_lut_file(path)

    def _on_export(self):
        stem, ext = os.path.splitext(os.path.basename(self._image_filepath))
        # Default to JPEG for RAW source files (can't write RAW)
        if ext.lower() in RAW_EXTENSIONS:
            ext = ".jpg"
        suggested = os.path.join(
            os.path.dirname(self._image_filepath), f"{stem}_lut{ext}"
        )
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", suggested, EXPORT_FILTER
        )
        if not save_path:
            return

        self._toolbar.set_processing(True)
        self._export_worker = ExportWorker(
            self._image_filepath, self._lut, save_path, parent=self
        )
        self._export_worker.progress.connect(self._status_bar.showMessage)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_view_mode_changed(self, mode: str):
        self._viewer.set_mode(mode)

    def _on_lut_result(self, result: np.ndarray):
        self._processed_array = result
        self._viewer.set_images(self._original_array, self._processed_array)
        self._toolbar.set_processing(False)
        self._update_export_button()
        self._status_bar.showMessage("LUT applied.", 3000)

    def _on_worker_error(self, message: str):
        self._toolbar.set_processing(False)
        self._update_export_button()
        QMessageBox.critical(self, "LUT Error", f"Failed to apply LUT:\n{message}")

    def _on_export_finished(self, path: str):
        self._toolbar.set_processing(False)
        self._update_export_button()
        self._status_bar.showMessage(f"Saved: {os.path.basename(path)}", 5000)

    def _on_export_error(self, message: str):
        self._toolbar.set_processing(False)
        self._update_export_button()
        QMessageBox.critical(self, "Export Error", f"Export failed:\n{message}")

    # ------------------------------------------------------------------
    # Loading logic
    # ------------------------------------------------------------------

    def _load_image_file(self, filepath: str):
        try:
            array, original_size = load_image(filepath)
        except ImageLoadError as e:
            QMessageBox.critical(self, "Image Load Error", str(e))
            return

        self._image_filepath = filepath
        self._original_array = array
        self._processed_array = None
        name = os.path.basename(filepath)
        self._toolbar.set_image_label(name)
        ow, oh = original_size
        dh, dw = array.shape[:2]
        self._status_bar.showMessage(
            f"{name}  |  {ow}×{oh} → displayed at {dw}×{dh}"
        )
        self._toolbar.add_recent_image(filepath)
        self._update_export_button()
        self._viewer.set_original_only(array)

        if self._lut is not None:
            self._trigger_lut_application()

    def _load_lut_file(self, filepath: str):
        try:
            lut = parse_cube(filepath)
        except LUTParseError as e:
            QMessageBox.critical(self, "LUT Parse Error", str(e))
            return

        self._lut = lut
        self._toolbar.add_recent_lut(filepath)
        name = os.path.basename(filepath)
        self._toolbar.set_lut_label(name)
        self._status_bar.showMessage(
            f"LUT loaded: {name}  |  {lut.size}³ grid"
            + (f'  \u201c{lut.title}\u201d' if lut.title else "")
        )
        self._update_export_button()

        if self._original_array is not None:
            self._trigger_lut_application()

    def _trigger_lut_application(self):
        # Cancel any in-flight worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.result_ready.disconnect()
            self._worker.error.disconnect()
            self._worker.quit()
            self._worker.wait(500)

        self._toolbar.set_processing(True)
        self._worker = LUTWorker(self._original_array, self._lut, parent=self)
        self._worker.result_ready.connect(self._on_lut_result)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _update_export_button(self):
        self._toolbar.set_export_enabled(
            self._image_filepath is not None and self._lut is not None
        )
