"""
Split before/after image viewer widget.

Renders two images side by side with a draggable vertical divider.
Supports pan (middle-click or right-click drag) and zoom (scroll wheel).
"""

import numpy as np
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QPoint, QRect, QSize
from PyQt5.QtGui import QPainter, QPixmap, QColor, QFont, QPen, QCursor

from app.image_loader import array_to_qpixmap

_DIVIDER_WIDTH = 2
_LABEL_MARGIN = 12
_HANDLE_RADIUS = 16  # pixels around divider that count as "hit"


class ImageViewer(QWidget):
    """
    Displays before (left) and after (right) images with a draggable split line.

    Modes
    -----
    "split"  : left half = original, right half = processed, divider draggable
    "before" : full original image
    "after"  : full processed image (if available, else original)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self._processed_pixmap: QPixmap | None = None
        self._split_frac: float = 0.5  # 0.0–1.0 fraction of widget width
        self._mode: str = "split"
        self._zoom: float = 1.0
        self._pan_offset: QPoint = QPoint(0, 0)  # offset of image centre from widget centre
        self._last_mouse: QPoint | None = None
        self._dragging_split: bool = False
        self._panning: bool = False

        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_images(self, original: np.ndarray, processed: np.ndarray | None):
        """Set the original and (optionally) processed image arrays."""
        self._original_pixmap = array_to_qpixmap(original)
        self._processed_pixmap = array_to_qpixmap(processed) if processed is not None else None
        self._fit_to_window()
        self.update()

    def set_original_only(self, original: np.ndarray):
        """Show only the original image (before a LUT has been applied)."""
        self._original_pixmap = array_to_qpixmap(original)
        self._processed_pixmap = None
        self._fit_to_window()
        self.update()

    def set_mode(self, mode: str):
        """Set display mode: 'split', 'before', or 'after'."""
        self._mode = mode
        self.update()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fit_to_window(self):
        """Reset zoom and pan so the image fills the widget."""
        self._pan_offset = QPoint(0, 0)
        if self._original_pixmap is None:
            self._zoom = 1.0
            return
        pw = self._original_pixmap.width()
        ph = self._original_pixmap.height()
        ww = max(self.width(), 1)
        wh = max(self.height(), 1)
        self._zoom = min(ww / pw, wh / ph)

    def _image_rect(self) -> QRect:
        """The destination rect for the full image at the current zoom/pan."""
        if self._original_pixmap is None:
            return QRect()
        pw = int(self._original_pixmap.width() * self._zoom)
        ph = int(self._original_pixmap.height() * self._zoom)
        cx = self.width() // 2 + self._pan_offset.x()
        cy = self.height() // 2 + self._pan_offset.y()
        return QRect(cx - pw // 2, cy - ph // 2, pw, ph)

    def _split_x(self) -> int:
        """Pixel x-coordinate of the divider."""
        return int(self._split_frac * self.width())

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        if self._original_pixmap is None:
            self._paint_placeholder()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        img_rect = self._image_rect()

        if self._mode == "split":
            self._paint_split(painter, img_rect)
        elif self._mode == "before":
            painter.drawPixmap(img_rect, self._original_pixmap, self._original_pixmap.rect())
            self._draw_label(painter, "BEFORE", self.rect().topLeft() + QPoint(_LABEL_MARGIN, _LABEL_MARGIN))
        else:  # "after"
            src = self._processed_pixmap if self._processed_pixmap else self._original_pixmap
            painter.drawPixmap(img_rect, src, src.rect())
            label = "AFTER" if self._processed_pixmap else "BEFORE"
            self._draw_label(painter, label, self.rect().topLeft() + QPoint(_LABEL_MARGIN, _LABEL_MARGIN))

        painter.end()

    def _paint_split(self, painter: QPainter, img_rect: QRect):
        sx = self._split_x()

        # Left half: original
        left_clip = QRect(0, 0, sx, self.height())
        painter.setClipRect(left_clip)
        painter.drawPixmap(img_rect, self._original_pixmap, self._original_pixmap.rect())
        self._draw_label(painter, "BEFORE", QPoint(_LABEL_MARGIN, _LABEL_MARGIN))

        # Right half: processed (or original if not yet available)
        right_clip = QRect(sx, 0, self.width() - sx, self.height())
        painter.setClipRect(right_clip)
        src = self._processed_pixmap if self._processed_pixmap else self._original_pixmap
        painter.drawPixmap(img_rect, src, src.rect())
        label = "AFTER" if self._processed_pixmap else "PROCESSING..."
        self._draw_label(painter, label, QPoint(sx + _LABEL_MARGIN, _LABEL_MARGIN))

        # Divider line
        painter.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 200), _DIVIDER_WIDTH)
        painter.setPen(pen)
        painter.drawLine(sx, 0, sx, self.height())

        # Handle circle
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.setPen(Qt.NoPen)
        cy = self.height() // 2
        r = 14
        painter.drawEllipse(QPoint(sx, cy), r, r)
        # Arrows inside handle
        painter.setPen(QPen(QColor(50, 50, 50), 2))
        painter.drawLine(sx - 6, cy, sx - 10, cy)
        painter.drawLine(sx - 10, cy, sx - 7, cy - 3)
        painter.drawLine(sx - 10, cy, sx - 7, cy + 3)
        painter.drawLine(sx + 6, cy, sx + 10, cy)
        painter.drawLine(sx + 10, cy, sx + 7, cy - 3)
        painter.drawLine(sx + 10, cy, sx + 7, cy + 3)

    def _draw_label(self, painter: QPainter, text: str, pos: QPoint):
        font = QFont("Sans Serif", 10, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        pad = 6
        bg = QRect(pos.x() - pad, pos.y() - pad, tw + pad * 2, th + pad * 2)
        painter.fillRect(bg, QColor(0, 0, 0, 140))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pos.x(), pos.y() + th - 2, text)

    def _paint_placeholder(self):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        painter.setPen(QColor(120, 120, 120))
        font = QFont("Sans Serif", 14)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "Open an image to get started")
        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if self._mode == "split" and event.button() == Qt.LeftButton:
            sx = self._split_x()
            if abs(event.x() - sx) <= _HANDLE_RADIUS:
                self._dragging_split = True
                self.setCursor(QCursor(Qt.SplitHCursor))
                return
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._last_mouse = event.pos()
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, event):
        if self._dragging_split:
            frac = max(0.05, min(0.95, event.x() / max(self.width(), 1)))
            self._split_frac = frac
            self.update()
            return
        if self._panning and self._last_mouse is not None:
            delta = event.pos() - self._last_mouse
            self._pan_offset += delta
            self._last_mouse = event.pos()
            self.update()
            return
        # Update cursor near divider
        if self._mode == "split":
            sx = self._split_x()
            if abs(event.x() - sx) <= _HANDLE_RADIUS:
                self.setCursor(QCursor(Qt.SplitHCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))

    def mouseReleaseEvent(self, event):
        self._dragging_split = False
        self._panning = False
        self._last_mouse = None
        self.setCursor(QCursor(Qt.ArrowCursor))

    def wheelEvent(self, event):
        if self._original_pixmap is None:
            return
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 1 / 1.12
        new_zoom = self._zoom * factor
        # Clamp: 10% to 1000%
        new_zoom = max(0.1, min(10.0, new_zoom))

        # Zoom towards the mouse cursor position
        mouse = event.pos()
        cx = self.width() // 2 + self._pan_offset.x()
        cy = self.height() // 2 + self._pan_offset.y()
        dx = mouse.x() - cx
        dy = mouse.y() - cy
        scale = new_zoom / self._zoom
        self._pan_offset = QPoint(
            int(mouse.x() - self.width() // 2 - dx * scale),
            int(mouse.y() - self.height() // 2 - dy * scale),
        )
        self._zoom = new_zoom
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click resets to fit-to-window."""
        self._fit_to_window()
        self.update()

    def resizeEvent(self, event):
        self._fit_to_window()
        super().resizeEvent(event)
