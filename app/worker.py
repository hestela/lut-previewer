"""
Background worker threads for LUT application and image export.

Keeps the GUI responsive during heavy numpy/IO operations.
"""

import os
import numpy as np
from PIL import Image
from PyQt5.QtCore import QThread, pyqtSignal

from app.lut import LUT3D, apply_lut
from app.image_loader import load_image


class LUTWorker(QThread):
    """
    Applies a LUT to an image in a background thread.

    Signals
    -------
    result_ready : emits the processed (H, W, 3) float32 array
    error        : emits a human-readable error message string
    """

    result_ready = pyqtSignal(object)  # np.ndarray
    error = pyqtSignal(str)

    def __init__(self, image: np.ndarray, lut: LUT3D, parent=None):
        super().__init__(parent)
        self._image = image
        self._lut = lut

    def run(self):
        try:
            result = apply_lut(self._image, self._lut)
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ExportWorker(QThread):
    """
    Full-resolution LUT export in a background thread.

    Loads the source image at its original resolution (bypassing the 1600px
    display cap), applies the LUT, and saves to disk.

    Signals
    -------
    progress : status string ("Loading…", "Applying LUT…", "Saving…")
    finished : emits the saved filepath on success
    error    : emits a human-readable error message on failure
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image_filepath: str, lut: LUT3D, save_filepath: str, parent=None):
        super().__init__(parent)
        self._image_filepath = image_filepath
        self._lut = lut
        self._save_filepath = save_filepath

    def run(self):
        try:
            self.progress.emit("Loading full-resolution image…")
            array, _ = load_image(self._image_filepath, max_display_px=None)

            self.progress.emit("Applying LUT…")
            result = apply_lut(array, self._lut)

            self.progress.emit("Saving…")
            uint8 = (result.clip(0.0, 1.0) * 255).astype(np.uint8)
            img = Image.fromarray(uint8, "RGB")
            ext = os.path.splitext(self._save_filepath)[1].lower()
            if ext in (".jpg", ".jpeg"):
                img.save(self._save_filepath, quality=100)
            else:
                img.save(self._save_filepath)

            self.finished.emit(self._save_filepath)
        except Exception as e:
            self.error.emit(str(e))
