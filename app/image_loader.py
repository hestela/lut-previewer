"""
Image loading for the LUT previewer.

Supports JPEG, PNG, TIFF, BMP via Pillow.
Supports RAW files (NEF, CR2, ARW, DNG) via rawpy if installed;
falls back to Pillow's embedded-thumbnail extraction otherwise.
"""

import os
import numpy as np
from PIL import Image

try:
    import rawpy
    _RAWPY_AVAILABLE = True
except ImportError:
    _RAWPY_AVAILABLE = False

from PyQt5.QtGui import QImage, QPixmap


RAW_EXTENSIONS = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2"}
IMAGE_FILTER = (
    "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp "
    "*.nef *.cr2 *.cr3 *.arw *.dng *.orf *.rw2)"
)


class ImageLoadError(IOError):
    pass


def load_image(filepath: str, max_display_px: int = 1600) -> tuple:
    """
    Load an image and return a display-resolution numpy array.

    Returns
    -------
    (array, original_size)
        array        : (H, W, 3) float32 in [0.0, 1.0], RGB
        original_size: (width, height) before downsampling
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in RAW_EXTENSIONS:
            pil_img = _load_raw(filepath)
        else:
            pil_img = Image.open(filepath).convert("RGB")
    except ImageLoadError:
        raise
    except Exception as e:
        raise ImageLoadError(f"Cannot open image: {e}") from e

    original_size = pil_img.size  # (width, height)

    # Downsample so the longer edge fits within max_display_px
    w, h = pil_img.size
    if max(w, h) > max_display_px:
        scale = max_display_px / max(w, h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

    array = np.asarray(pil_img, dtype=np.float32) / 255.0
    return array, original_size


def _load_raw(filepath: str) -> Image.Image:
    """Decode a RAW file to a PIL Image (RGB, 8-bit)."""
    if _RAWPY_AVAILABLE:
        try:
            with rawpy.imread(filepath) as raw:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    output_bps=8,
                    no_auto_bright=False,
                )
            return Image.fromarray(rgb)
        except Exception as e:
            raise ImageLoadError(f"rawpy failed to decode RAW file: {e}") from e
    else:
        # Pillow can extract the small TIFF/JPEG thumbnail embedded in most RAW files
        try:
            img = Image.open(filepath)
            img.load()
            return img.convert("RGB")
        except Exception as e:
            raise ImageLoadError(
                f"rawpy is not installed; Pillow fallback also failed: {e}\n"
                "Install rawpy for full-resolution RAW support: pip install rawpy"
            ) from e


def array_to_qpixmap(array: np.ndarray) -> QPixmap:
    """
    Convert a (H, W, 3) float32 array in [0, 1] to a QPixmap.

    Must be called from the main (GUI) thread.
    """
    uint8 = (array.clip(0.0, 1.0) * 255).astype(np.uint8)
    h, w = uint8.shape[:2]
    # Make the array contiguous so QImage can use it directly
    contiguous = np.ascontiguousarray(uint8)
    qimg = QImage(
        contiguous.data, w, h, w * 3, QImage.Format_RGB888
    )
    # QPixmap.fromImage copies the pixel data, so the numpy array can be freed
    return QPixmap.fromImage(qimg)
