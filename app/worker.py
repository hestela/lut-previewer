"""
Background worker thread for LUT application.

Keeps the GUI responsive while the ~350ms trilinear interpolation runs.
"""

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from app.lut import LUT3D, apply_lut


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
