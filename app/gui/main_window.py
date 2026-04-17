"""
Main application window.

Wires together the toolbar, image viewer, LUT sidebar panel,
and background worker threads.
"""

import os
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QStatusBar
)
from PyQt5.QtCore import Qt

from app.lut import LUT3D, parse_cube, LUTParseError
from app.image_loader import load_image, ImageLoadError, IMAGE_FILTER
from app.worker import LUTWorker, ExportWorker
from app.history import RecentFiles
from app.gui.toolbar import Toolbar
from app.gui.image_viewer import ImageViewer
from app.gui.lut_panel import LUTPanel

EXPORT_FILTER = "JPEG (*.jpg *.jpeg);;PNG (*.png);;TIFF (*.tif *.tiff)"
RAW_EXTENSIONS = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Image state
        self._image_filepath: str | None = None
        self._original_array: np.ndarray | None = None

        # Multi-LUT state
        self._lut_entries: dict[str, LUT3D] = {}          # filepath → LUT3D
        self._lut_results: dict[str, np.ndarray] = {}     # filepath → processed array
        self._lut_workers: dict[str, LUTWorker] = {}      # filepath → in-flight worker
        self._active_lut_path: str | None = None

        # Export state
        self._export_worker: ExportWorker | None = None

        # Persistent LUT history (owned here, shared with LUTPanel)
        self._lut_history = RecentFiles("luts")

        self._build_ui()
        self._populate_from_history()

    def _populate_from_history(self):
        """Pre-populate the LUT panel with all previously used LUTs."""
        for path in self._lut_history.paths():
            try:
                lut = parse_cube(path)
            except (LUTParseError, OSError):
                continue  # skip corrupt or inaccessible files silently
            self._lut_entries[path] = lut
            self._lut_panel.add_lut(path, os.path.basename(path))
            self._lut_panel.mark_ready(path)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toolbar = Toolbar()
        self._toolbar.open_image_requested.connect(self._on_open_image)
        self._toolbar.export_requested.connect(self._on_export)
        self._toolbar.view_mode_changed.connect(self._on_view_mode_changed)
        self._toolbar.recent_image_selected.connect(self._load_image_file)
        outer.addWidget(self._toolbar)

        # Main area: viewer (stretch) + LUT panel (fixed width)
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)

        self._viewer = ImageViewer()
        main_row.addWidget(self._viewer, stretch=1)

        self._lut_panel = LUTPanel()
        self._lut_panel.luts_add_requested.connect(self._on_add_luts)
        self._lut_panel.lut_selected.connect(self._on_lut_selected)
        self._lut_panel.lut_remove_requested.connect(self._on_lut_remove)
        self._lut_panel.remove_all_requested.connect(self._on_remove_all_luts)
        main_row.addWidget(self._lut_panel)

        outer.addLayout(main_row, stretch=1)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ------------------------------------------------------------------
    # Slots — image
    # ------------------------------------------------------------------

    def _on_open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", IMAGE_FILTER
        )
        if path:
            self._load_image_file(path)

    def _load_image_file(self, filepath: str):
        try:
            array, original_size = load_image(filepath)
        except ImageLoadError as e:
            QMessageBox.critical(self, "Image Load Error", str(e))
            return

        self._image_filepath = filepath
        self._original_array = array
        name = os.path.basename(filepath)
        self._toolbar.set_image_label(name)
        self._toolbar.add_recent_image(filepath)
        ow, oh = original_size
        dh, dw = array.shape[:2]
        self._status_bar.showMessage(
            f"{name}  |  {ow}×{oh} → displayed at {dw}×{dh}"
        )
        self._viewer.set_original_only(array)

        # Invalidate cached results and re-process all loaded LUTs,
        # starting the active LUT first so it appears without delay.
        self._cancel_all_workers()
        self._lut_results.clear()
        paths = list(self._lut_entries.keys())
        if self._active_lut_path in self._lut_entries:
            paths.remove(self._active_lut_path)
            paths.insert(0, self._active_lut_path)
        for path in paths:
            self._lut_panel.add_lut(path, os.path.basename(path))  # resets to pending
            self._start_lut_worker(path)

        # Restore split view for active LUT if still loaded
        if self._active_lut_path and self._active_lut_path in self._lut_entries:
            self._activate_lut(self._active_lut_path)
        elif self._lut_entries:
            self._activate_lut(next(iter(self._lut_entries)))

        self._update_export_button()

    # ------------------------------------------------------------------
    # Slots — LUT panel
    # ------------------------------------------------------------------

    def _on_add_luts(self, filepaths: list):
        first_new_path = None
        for path in filepaths:
            if path in self._lut_entries:
                continue
            try:
                lut = parse_cube(path)
            except LUTParseError as e:
                QMessageBox.warning(
                    self, "LUT Parse Error",
                    f"{os.path.basename(path)}:\n{e}"
                )
                continue
            self._lut_entries[path] = lut
            # add_lut blocks list signals internally — safe to call in a loop
            self._lut_panel.add_lut(path, os.path.basename(path))
            self._lut_history.add(path)
            if self._original_array is not None:
                self._start_lut_worker(path)
            if first_new_path is None:
                first_new_path = path

        if first_new_path is None:
            return  # nothing new was added

        # Auto-select the first newly added LUT if nothing is active yet
        if self._active_lut_path is None:
            self._activate_lut(first_new_path)

        self._update_export_button()

    def _on_lut_selected(self, filepath: str):
        self._activate_lut(filepath)

    def _on_lut_remove(self, filepath: str):
        # Cancel in-flight worker
        if filepath in self._lut_workers:
            w = self._lut_workers.pop(filepath)
            w.result_ready.disconnect()
            w.error.disconnect()
            w.quit()
            w.wait(300)

        self._lut_entries.pop(filepath, None)
        self._lut_results.pop(filepath, None)
        self._lut_history.remove(filepath)
        self._lut_panel.remove_lut(filepath)

        if self._active_lut_path == filepath:
            self._active_lut_path = None
            remaining = list(self._lut_entries.keys())
            if remaining:
                self._activate_lut(remaining[0])
            else:
                if self._original_array is not None:
                    self._viewer.set_original_only(self._original_array)
                self._update_export_button()

    def _on_remove_all_luts(self):
        self._cancel_all_workers()
        self._lut_entries.clear()
        self._lut_results.clear()
        self._active_lut_path = None
        self._lut_history.clear()
        self._lut_panel.clear()
        if self._original_array is not None:
            self._viewer.set_original_only(self._original_array)
        self._update_export_button()

    # ------------------------------------------------------------------
    # Slots — view mode
    # ------------------------------------------------------------------

    def _on_view_mode_changed(self, mode: str):
        self._viewer.set_mode(mode)

    # ------------------------------------------------------------------
    # Slots — export
    # ------------------------------------------------------------------

    def _on_export(self):
        if not self._image_filepath or not self._active_lut_path:
            return
        stem, ext = os.path.splitext(os.path.basename(self._image_filepath))
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
        lut = self._lut_entries[self._active_lut_path]
        self._export_worker = ExportWorker(
            self._image_filepath, lut, save_path, parent=self
        )
        self._export_worker.progress.connect(self._status_bar.showMessage)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_finished(self, path: str):
        self._toolbar.set_processing(False)
        self._update_export_button()
        self._status_bar.showMessage(f"Saved: {os.path.basename(path)}", 5000)

    def _on_export_error(self, message: str):
        self._toolbar.set_processing(False)
        self._update_export_button()
        QMessageBox.critical(self, "Export Error", f"Export failed:\n{message}")

    # ------------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------------

    def _start_lut_worker(self, filepath: str):
        # Cancel existing worker for this path if any
        if filepath in self._lut_workers:
            old = self._lut_workers.pop(filepath)
            old.result_ready.disconnect()
            old.error.disconnect()
            old.finished.disconnect()
            old.quit()
            old.wait(300)
            old.deleteLater()

        # parent=self: Qt holds a reference so Python GC can't destroy the
        # thread object while it's running or while its signals are being delivered.
        worker = LUTWorker(
            self._original_array, self._lut_entries[filepath], parent=self
        )
        worker.result_ready.connect(
            lambda arr, p=filepath: self._on_lut_result(p, arr)
        )
        worker.error.connect(
            lambda msg, p=filepath: self._on_lut_error(p, msg)
        )
        # finished fires after run() returns — safe to remove the dict entry here.
        worker.finished.connect(
            lambda p=filepath: self._on_worker_finished(p)
        )
        self._lut_workers[filepath] = worker
        worker.start()

    def _on_worker_finished(self, filepath: str):
        """Called when a LUTWorker thread exits. Cleans up the dict entry."""
        w = self._lut_workers.pop(filepath, None)
        if w is not None:
            w.deleteLater()

    def _cancel_all_workers(self):
        for filepath, w in list(self._lut_workers.items()):
            w.result_ready.disconnect()
            w.error.disconnect()
            w.finished.disconnect()
            w.quit()
            w.wait(300)
            w.deleteLater()
        self._lut_workers.clear()

    def _on_lut_result(self, filepath: str, result: np.ndarray):
        # Do NOT pop from _lut_workers here — that happens in _on_worker_finished
        # (finished signal fires after run() returns, safely after this slot).
        self._lut_results[filepath] = result
        self._lut_panel.mark_ready(filepath)
        if filepath == self._active_lut_path:
            self._viewer.set_images(self._original_array, result)
            self._update_export_button()

    def _on_lut_error(self, filepath: str, message: str):
        # Do NOT pop from _lut_workers here — handled by _on_worker_finished.
        self._lut_panel.remove_lut(filepath)
        self._lut_entries.pop(filepath, None)
        QMessageBox.warning(
            self, "LUT Error",
            f"{os.path.basename(filepath)}:\n{message}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _activate_lut(self, filepath: str):
        self._active_lut_path = filepath
        self._lut_panel.set_active(filepath)
        if filepath in self._lut_results and self._original_array is not None:
            self._viewer.set_images(self._original_array, self._lut_results[filepath])
        elif self._original_array is not None:
            # Still processing — show original until result arrives
            self._viewer.set_original_only(self._original_array)
        self._update_export_button()

    def _update_export_button(self):
        self._toolbar.set_export_enabled(
            self._image_filepath is not None
            and self._active_lut_path is not None
            and self._active_lut_path in self._lut_results
        )
