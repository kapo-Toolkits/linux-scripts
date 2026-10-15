"""Normalize any supported file into a single PDF.

The whole app works on PDF internally: it is the one format Qt can both
preview (QtPdf) and print reliably on every platform. Each input type only
needs a small "last mile" converter here.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
OFFICE_EXTS = {
    ".doc", ".docx", ".odt", ".rtf", ".txt",
    ".xls", ".xlsx", ".ods", ".csv",
    ".ppt", ".pptx", ".odp",
}


def find_soffice() -> str | None:
    """Locate the LibreOffice headless binary, or return None."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if exe:
        return exe
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# Image placement modes.
SCALE_FIT = "fit"        # scale down to fit inside the margins (aspect kept)
SCALE_FILL = "fill"      # scale to cover the whole printable area (crop overflow)
SCALE_ACTUAL = "actual"  # place at the image's real physical size (from its DPI)

_RESOLUTION = 300  # QPdfWriter device resolution (dpi)
_M_PER_IN = 0.0254


def _image_dpi(img: QImage) -> tuple[float, float]:
    """Return the image's (x, y) DPI, falling back to 96 when unknown."""
    dx = img.dotsPerMeterX() * _M_PER_IN
    dy = img.dotsPerMeterY() * _M_PER_IN
    return (dx if dx > 1 else 96.0, dy if dy > 1 else 96.0)


def image_to_pdf(src: str, out_pdf: str, mode: str = SCALE_FIT) -> str:
    """Place a single image on an A4 page (auto-orientation) using `mode`."""
    img = QImage(src)
    if img.isNull():
        raise ValueError(f"Cannot load image: {src}")

    writer = QPdfWriter(out_pdf)
    writer.setResolution(_RESOLUTION)
    landscape = img.width() > img.height()
    layout = QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait,
        QMarginsF(10, 10, 10, 10),
        QPageLayout.Unit.Millimeter,
    )
    writer.setPageLayout(layout)

    painter = QPainter(writer)
    try:
        vp = painter.viewport()  # printable area in device pixels
        if mode == SCALE_FILL:
            painter.setClipRect(vp)  # cover the page, crop the overflow
            s = img.size().scaled(vp.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            w, h = s.width(), s.height()
        elif mode == SCALE_ACTUAL:
            painter.setClipRect(vp)  # 1:1 physical size, crop if larger than page
            dpi_x, dpi_y = _image_dpi(img)
            w = img.width() / dpi_x * _RESOLUTION
            h = img.height() / dpi_y * _RESOLUTION
        else:  # SCALE_FIT (default)
            s = img.size().scaled(vp.size(), Qt.AspectRatioMode.KeepAspectRatio)
            w, h = s.width(), s.height()

        x = vp.x() + (vp.width() - w) / 2
        y = vp.y() + (vp.height() - h) / 2
        painter.drawImage(QRectF(x, y, w, h), img)
    finally:
        painter.end()
    return out_pdf


def office_to_pdf(src: str, out_dir: str) -> str:
    """Convert an Office/text document to PDF via LibreOffice headless."""
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it to print Office documents "
            "(the PDF/image path works without it)."
        )
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, src],
        check=True,
        capture_output=True,
        timeout=120,
    )
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if not os.path.exists(out):
        raise RuntimeError("LibreOffice conversion produced no PDF.")
    return out


def to_pdf(src: str, work_dir: str, image_mode: str = SCALE_FIT) -> str:
    """Return a path to a PDF representation of `src` (may be `src` itself).

    `image_mode` only affects image inputs (fit / fill / actual).
    """
    ext = os.path.splitext(src)[1].lower()
    if ext == ".pdf":
        return src
    if ext in IMAGE_EXTS:
        out = os.path.join(work_dir, f"image_{image_mode}.pdf")
        return image_to_pdf(src, out, image_mode)
    if ext in OFFICE_EXTS:
        return office_to_pdf(src, work_dir)
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")
