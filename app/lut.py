"""
LUT parsing and application.

Supports the Adobe .cube 3D LUT format. Applies LUTs using fully vectorized
trilinear interpolation with numpy — no Python loops over pixels.
"""

import numpy as np


class LUTParseError(ValueError):
    pass


class LUT3D:
    def __init__(self, size: int, table: np.ndarray, title: str = ""):
        # table shape: (size, size, size, 3), dtype float32
        # indexed as table[r_idx, g_idx, b_idx] = [R_out, G_out, B_out]
        self.size = size
        self.table = table
        self.title = title

    def __repr__(self):
        return f"LUT3D(size={self.size}, title={self.title!r})"


def parse_cube(filepath: str) -> LUT3D:
    """
    Parse an Adobe .cube 3D LUT file.

    The .cube format uses blue-fastest axis ordering, which maps directly
    onto numpy C-order (last index varies fastest): table[r, g, b].
    """
    with open(filepath, "r") as f:
        lines = f.readlines()

    size = None
    title = ""
    data_start = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        upper = stripped.upper()
        if upper.startswith("TITLE"):
            title = stripped[5:].strip().strip('"')
        elif upper.startswith("LUT_3D_SIZE"):
            parts = stripped.split()
            if len(parts) < 2:
                raise LUTParseError("LUT_3D_SIZE line missing value")
            try:
                size = int(parts[1])
            except ValueError:
                raise LUTParseError(f"Invalid LUT_3D_SIZE value: {parts[1]!r}")
        elif upper.startswith("DOMAIN_MIN") or upper.startswith("DOMAIN_MAX"):
            # Accept but ignore; assume standard 0.0–1.0 domain
            pass
        else:
            # First non-header line with floats is the start of data
            try:
                float(stripped.split()[0])
                data_start = i
                break
            except (ValueError, IndexError):
                pass

    if size is None:
        raise LUTParseError("LUT_3D_SIZE not found in file")
    if data_start is None:
        raise LUTParseError("No data lines found in file")

    # Bulk-read all data lines as a single string for fast numpy parsing
    data_text = " ".join(lines[data_start:])
    try:
        flat = np.fromstring(data_text, dtype=np.float32, sep=" ")
    except Exception as e:
        raise LUTParseError(f"Failed to parse LUT data: {e}")

    expected = size ** 3 * 3
    if flat.size != expected:
        raise LUTParseError(
            f"Expected {expected} values for {size}^3 LUT, got {flat.size}"
        )

    # .cube format: R varies fastest, B slowest.
    # C-order reshape of that gives table[b_idx, g_idx, r_idx].
    # Transpose axes so table[r_idx, g_idx, b_idx] for consistent apply_lut indexing.
    table = flat.reshape((size, size, size, 3)).transpose(2, 1, 0, 3).copy()

    return LUT3D(size=size, table=table, title=title)


def apply_lut(image: np.ndarray, lut: LUT3D) -> np.ndarray:
    """
    Apply a 3D LUT to an image using trilinear interpolation.

    Parameters
    ----------
    image : np.ndarray
        Shape (H, W, 3), dtype float32, values in [0.0, 1.0]
    lut : LUT3D

    Returns
    -------
    np.ndarray
        Shape (H, W, 3), dtype float32, values in [0.0, 1.0]
    """
    N = lut.size
    scale = N - 1

    # Scale pixel channels to LUT grid coordinates
    r = image[:, :, 0] * scale  # (H, W)
    g = image[:, :, 1] * scale
    b = image[:, :, 2] * scale

    # Lower grid corners (integer), clamped so upper corner r0+1 stays in range
    r0 = np.floor(r).astype(np.int32).clip(0, N - 2)
    g0 = np.floor(g).astype(np.int32).clip(0, N - 2)
    b0 = np.floor(b).astype(np.int32).clip(0, N - 2)

    r1 = r0 + 1
    g1 = g0 + 1
    b1 = b0 + 1

    # Fractional distances, shaped (H, W, 1) for broadcasting against (H, W, 3)
    dr = (r - r0)[:, :, np.newaxis]
    dg = (g - g0)[:, :, np.newaxis]
    db = (b - b0)[:, :, np.newaxis]

    t = lut.table
    # 8 corner lookups, each (H, W, 3)
    c000 = t[r0, g0, b0]
    c001 = t[r0, g0, b1]
    c010 = t[r0, g1, b0]
    c011 = t[r0, g1, b1]
    c100 = t[r1, g0, b0]
    c101 = t[r1, g0, b1]
    c110 = t[r1, g1, b0]
    c111 = t[r1, g1, b1]

    result = (
        c000 * (1 - dr) * (1 - dg) * (1 - db)
        + c001 * (1 - dr) * (1 - dg) * db
        + c010 * (1 - dr) * dg * (1 - db)
        + c011 * (1 - dr) * dg * db
        + c100 * dr * (1 - dg) * (1 - db)
        + c101 * dr * (1 - dg) * db
        + c110 * dr * dg * (1 - db)
        + c111 * dr * dg * db
    )

    return result.astype(np.float32)
