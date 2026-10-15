"""Verify image fit / fill / actual-size placement on the page."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from printhub.convert import SCALE_ACTUAL, SCALE_FILL, SCALE_FIT, image_to_pdf


def make_wide_image(path: str, dpi: int) -> None:
    """A wide, saturated image with a frame; DPI stamped for actual-size."""
    img = QImage(1600, 500, QImage.Format.Format_RGB32)
    img.fill(QColor("#2f6fed"))
    p = QPainter(img)
    p.setPen(QColor("black"))
    for off in range(6):
        p.drawRect(off, off, img.width() - 1 - 2 * off, img.height() - 1 - 2 * off)
    p.end()
    dpm = round(dpi / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    img.save(path, "PNG")


def content_bbox(page_img: QImage) -> tuple[float, float]:
    """Return (width_frac, height_frac) of the non-white bounding box."""
    w, h = page_img.width(), page_img.height()
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if page_img.pixelColor(x, y).lightnessF() < 0.92:
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
    if maxx < 0:
        return (0.0, 0.0)
    return ((maxx - minx) / w, (maxy - miny) / h)


def render_page0(pdf: str, size: QSize) -> QImage:
    d = QPdfDocument()
    d.load(pdf)
    img = d.render(0, size)
    d.close()
    # QtPdf leaves un-painted page areas transparent; composite over white so
    # letterbox regions read as white, not black.
    canvas = QImage(size, QImage.Format.Format_RGB32)
    canvas.fill(QColor("white"))
    p = QPainter(canvas)
    p.drawImage(0, 0, img)
    p.end()
    return canvas


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    work = tempfile.mkdtemp(prefix="printhub_scale_")
    src = os.path.join(work, "wide.png")
    make_wide_image(src, dpi=150)

    render_size = QSize(360, 509)  # ~A4 portrait, small for a fast pixel scan
    results = {}
    tiles = []
    for mode in (SCALE_FIT, SCALE_FILL, SCALE_ACTUAL):
        pdf = image_to_pdf(src, os.path.join(work, f"{mode}.pdf"), mode)
        page = render_page0(pdf, render_size)
        results[mode] = content_bbox(page)
        tiles.append(page)

    fw, fh = results[SCALE_FIT]
    lw, lh = results[SCALE_FILL]
    aw, ah = results[SCALE_ACTUAL]
    print(f"  fit    bbox  w={fw:.2f} h={fh:.2f}")
    print(f"  fill   bbox  w={lw:.2f} h={lh:.2f}")
    print(f"  actual bbox  w={aw:.2f} h={ah:.2f}")

    # image_to_pdf uses 10 mm page margins, so "fill" covers the printable
    # area (~0.9 of the sheet each way), not the physical edge.
    checks = {
        "fit is letterboxed (height < 60% of page)": fh < 0.60,
        "fill fills printable width (>= 88%)": lw >= 0.88,
        "fill fills printable height (>= 88%)": lh >= 0.88,
        "fill much taller than fit": lh - fh > 0.20,
        "actual is physical size (shorter than fill)": ah < lh - 0.20,
    }
    ok = True
    for name, passed in checks.items():
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")

    # Visual: three page renders side by side.
    gap = 12
    combo = QImage(360 * 3 + gap * 2, 509, QImage.Format.Format_RGB32)
    combo.fill(QColor("#dddddd"))
    p = QPainter(combo)
    for i, tile in enumerate(tiles):
        p.drawImage((360 + gap) * i, 0, tile)
    p.end()
    shot = os.path.join(os.environ.get("PRINTHUB_SHOTS") or __import__("tempfile").gettempdir(), "scale_modes.png")  # set PRINTHUB_SHOTS=docs to refresh the README images
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    combo.save(shot, "PNG")
    print(f"  visual fit|fill|actual -> {shot}")

    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
