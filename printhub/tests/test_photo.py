"""Photo mode: where the photo lands on the paper (geometry), and that print / preview really put it there.

The geometry is checked as numbers; the printing is checked on pixels: a photo is printed to a PDF printer (the same code
path as a real printer, full page) and the result is rendered back and probed at the paper's edges."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMarginsF, QSize, QSizeF
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.photo import (ACTUAL, FILL, FIT, SIZE, TOP_LEFT, PhotoLeaf, PhotoSettings, layout_photo, paper_mm,
                            photo_to_pdf, quality)
from printhub.printing import render_leaves_to_printer

ok_all = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok_all
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail and not cond else ""))
    ok_all &= bool(cond)


def near(a, b, tol=0.05) -> bool:
    return abs(a - b) <= tol


def box(layout, i=0):
    return layout.placements[i].dest


def geometry() -> None:
    print("geometry (mm on the paper)")
    P10x15 = (100.0, 150.0)
    DPI = (300.0, 300.0)

    # a 3:2 portrait photo on 10x15 paper: fill and fit both cover it exactly, nothing cropped
    lay = layout_photo(P10x15, (2000, 3000), DPI, PhotoSettings(mode=FILL))
    check("fill, same proportions: covers the whole paper", all(near(a, b) for a, b in zip(box(lay), (0, 0, 100, 150))), str(box(lay)))
    check("fill, same proportions: nothing cropped", near(lay.cropped, 0, 1e-6))
    check("effective resolution is the photo's pixels over its printed width (2000 px / 100 mm = 508 dpi)", near(lay.dpi, 508, 1), str(lay.dpi))

    # the same photo on A4: fill covers and crops, fit leaves bands
    A4 = (210.0, 297.0)
    fill = layout_photo(A4, (2000, 3000), DPI, PhotoSettings(mode=FILL))
    x, y, w, h = box(fill)
    check("fill on A4: the paper is fully inside the photo", x <= 1e-6 and y <= 1e-6 and x + w >= 210 - 1e-6 and y + h >= 297 - 1e-6, str(box(fill)))
    check("fill on A4: part of the photo is cropped, and it says how much", 0.01 < fill.cropped < 0.3, str(fill.cropped))
    fit = layout_photo(A4, (2000, 3000), DPI, PhotoSettings(mode=FIT))
    x, y, w, h = box(fit)
    check("fit on A4: the whole photo is inside the paper, centred, in proportion",
          x >= 0 and y >= 0 and x + w <= 210 + 1e-6 and y + h <= 297 + 1e-6 and near(w / h, 2 / 3, 1e-6) and near(x, (210 - w) / 2) and near(y, (297 - h) / 2), str(box(fit)))
    check("fit: nothing cropped", near(fit.cropped, 0, 1e-6))

    # margin
    lay = layout_photo(P10x15, (2000, 3000), DPI, PhotoSettings(mode=FIT, margin_mm=5))
    x, y, w, h = box(lay)
    check("fit with a 5 mm margin stays inside it", x >= 5 - 1e-6 and y >= 5 - 1e-6 and x + w <= 95 + 1e-6 and y + h <= 145 + 1e-6, str(box(lay)))
    lay = layout_photo(P10x15, (2000, 3000), DPI, PhotoSettings(mode=FILL, margin_mm=5))
    check("fill with a margin covers the area inside it and is clipped there", lay.placements[0].clip == (5, 5, 90, 140), str(lay.placements[0].clip))

    # landscape photo on portrait paper: rotated by default, and the rotation covers the paper
    lay = layout_photo(P10x15, (3000, 2000), DPI, PhotoSettings(mode=FILL))
    check("landscape photo on portrait paper is turned to cover it", lay.placements[0].rotated and near(lay.cropped, 0, 1e-6), str(lay))
    lay = layout_photo(P10x15, (3000, 2000), DPI, PhotoSettings(mode=FILL, auto_rotate=False))
    check("with auto-rotate off it is cropped instead", not lay.placements[0].rotated and lay.cropped > 0.4, str(lay.cropped))

    # exact print sizes
    lay = layout_photo(A4, (3000, 2000), DPI, PhotoSettings(mode=SIZE, size_cm=(10, 15)))
    x, y, w, h = box(lay)
    check("10x15 on A4 for a landscape photo: 150 x 100 mm, centred", near(w, 150) and near(h, 100) and near(x, 30) and near(y, 98.5), str(box(lay)))
    lay = layout_photo(A4, (3000, 2000), DPI, PhotoSettings(mode=SIZE, size_cm=(10, 15), anchor=TOP_LEFT))
    check("top-left puts it in the corner", near(box(lay)[0], 0) and near(box(lay)[1], 0))
    lay = layout_photo(A4, (4000, 3000), DPI, PhotoSettings(mode=SIZE, size_cm=(10, 15), crop_to_size=False))
    check("a 4:3 photo fitted into a 10x15 box keeps its proportions inside it",
          (lambda d: near(d[2] / d[3], 4 / 3, 1e-3) and d[2] <= 150.01 and d[3] <= 100.01)(box(lay)), str(box(lay)))
    lay = layout_photo(A4, (4000, 3000), DPI, PhotoSettings(mode=SIZE, size_cm=(10, 15), crop_to_size=True))
    clip = lay.placements[0].clip
    check("a 4:3 photo cropped to a 10x15 box fills exactly that box and crops some",
          lay.cropped > 0.1 and all(near(a, b) for a, b in zip(clip, (30.0, 98.5, 150.0, 100.0))), str(clip))
    lay = layout_photo((100.0, 100.0), (3000, 2000), DPI, PhotoSettings(mode=SIZE, size_cm=(20, 30)))
    check("a print size bigger than the paper is reduced and says so", lay.shrunk and lay.box_mm[0] <= 100.01 and lay.box_mm[1] <= 100.01, str(lay.box_mm))

    # repeat: 10x15 prints on an A4 sheet (two 100x150 side by side, or two 150x100 one above the other)
    lay = layout_photo(A4, (3000, 2000), DPI, PhotoSettings(mode=SIZE, size_cm=(10, 15), repeat=True))
    check("repeat puts several prints on the sheet", len(lay.placements) >= 2, str(len(lay.placements)))
    rects = [p.clip for p in lay.placements]
    inside = all(r[0] >= -1e-6 and r[1] >= -1e-6 and r[0] + r[2] <= 210 + 1e-6 and r[1] + r[3] <= 297 + 1e-6 for r in rects)
    overlap = any(a is not b and a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3] for a in rects for b in rects)
    check("repeated prints stay on the paper and do not overlap", inside and not overlap, str(rects))
    lay = layout_photo((210.0, 297.0), (3000, 2000), DPI, PhotoSettings(mode=SIZE, size_cm=(9, 13), repeat=True))
    check("9x13 repeated on A4 gives at least 4 prints", len(lay.placements) >= 4, str(len(lay.placements)))

    # actual size from the file's dpi
    lay = layout_photo(A4, (1200, 1800), (300.0, 300.0), PhotoSettings(mode=ACTUAL))
    check("actual size: 1200x1800 px at 300 dpi = 101.6 x 152.4 mm, centred",
          near(box(lay)[2], 101.6, 0.01) and near(box(lay)[3], 152.4, 0.01) and near(box(lay)[0], (210 - 101.6) / 2, 0.01), str(box(lay)))
    check("and its resolution is the file's 300 dpi", near(lay.dpi, 300, 0.5), str(lay.dpi))

    # quality words
    check("quality words", (quality(300), quality(180), quality(90)) == ("good", "ok", "low"))
    # paper orientation
    ps = QPageSize(QPageSize.PageSizeId.A4)
    check("paper_mm follows the orientation", paper_mm(ps, QPageLayout.Orientation.Landscape)[0] > paper_mm(ps, QPageLayout.Orientation.Portrait)[0])


def make_photo(path: str, w: int, h: int, color="#d12020") -> None:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    img.save(path, "PNG")


def render_pdf(pdf: str, px_per_mm: float):
    d = QPdfDocument()
    d.load(pdf)
    pt = d.pagePointSize(0)
    size = QSize(round(pt.width() / 72 * 25.4 * px_per_mm), round(pt.height() / 72 * 25.4 * px_per_mm))
    img = d.render(0, size)
    canvas = QImage(size, QImage.Format.Format_RGB32)
    canvas.fill(QColor("white"))
    p = QPainter(canvas)
    p.drawImage(0, 0, img)
    p.end()
    d.close()
    return canvas, (pt.width() / 72 * 25.4, pt.height() / 72 * 25.4)


def is_red(img, x, y) -> bool:
    c = img.pixelColor(x, y)
    return c.red() > 180 and c.green() < 90 and c.blue() < 90


def is_white(img, x, y) -> bool:
    c = img.pixelColor(x, y)
    return c.red() > 235 and c.green() > 235 and c.blue() > 235


def printing() -> None:
    print("printing and preview, probed on pixels")
    tmp = tempfile.mkdtemp()
    page = QPageSize(QSizeF(100, 150), QPageSize.Unit.Millimeter)

    def print_photo(path, s, name, orientation=QPageLayout.Orientation.Portrait, extra=None):
        out = os.path.join(tmp, name)
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        pr.setOutputFileName(out)
        pr.setPageSize(page)
        pr.setPageOrientation(orientation)
        leaves = [PhotoLeaf(path)] + (extra or [])
        ok = render_leaves_to_printer(leaves, pr, 1, s)
        return ok, out

    # fill: the photo reaches every corner of the PAPER (not just the printable area)
    photo = os.path.join(tmp, "p.png")
    make_photo(photo, 1000, 1500)
    ok, out = print_photo(photo, PhotoSettings(mode=FILL), "fill.pdf")
    img, mm = render_pdf(out, 4)
    check("printed PDF page is the chosen paper (100 x 150 mm)", near(mm[0], 100, 0.6) and near(mm[1], 150, 0.6), str(mm))
    W, H = img.width(), img.height()
    corners = [(1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2), (W // 2, H // 2)]
    check("fill: all four corners and the middle are photo", ok and all(is_red(img, x, y) for x, y in corners), str([img.pixelColor(x, y).name() for x, y in corners]))

    # fit with a 5 mm margin: white frame of 5 mm on the sides, photo inside
    ok, out = print_photo(photo, PhotoSettings(mode=FIT, margin_mm=5), "fit.pdf")
    img, _ = render_pdf(out, 4)
    k = 4  # px per mm
    check("fit + 5 mm margin: white inside the margin, photo just beyond it",
          is_white(img, 3 * k, img.height() // 2) and is_red(img, 7 * k, img.height() // 2)
          and is_white(img, img.width() - 3 * k, img.height() // 2) and is_red(img, img.width() - 7 * k, img.height() // 2))

    # exact size: 8 x 12 cm print on 10 x 15 paper, centred: 1 cm white each side
    ok, out = print_photo(photo, PhotoSettings(mode=SIZE, size_cm=(8, 12)), "size.pdf")
    img, _ = render_pdf(out, 4)
    check("8 x 12 cm print is centred with 10 mm white on each side",
          is_white(img, 8 * k, img.height() // 2) and is_red(img, 12 * k, img.height() // 2)
          and is_white(img, img.width() - 8 * k, img.height() // 2) and is_red(img, img.width() - 12 * k, img.height() // 2))

    # a landscape photo on portrait paper is turned and still covers the paper
    land = os.path.join(tmp, "land.png")
    make_photo(land, 1500, 1000)
    ok, out = print_photo(land, PhotoSettings(mode=FILL), "land.pdf")
    img, _ = render_pdf(out, 4)
    check("landscape photo on portrait paper: turned, corners covered", ok and all(is_red(img, x, y) for x, y in
          [(1, 1), (img.width() - 2, 1), (1, img.height() - 2), (img.width() - 2, img.height() - 2)]))

    # a photo that really is marked: left half red, right half blue - the turn must be 90° clockwise-correct (no mirroring)
    marked = os.path.join(tmp, "marked.png")
    m = QImage(1500, 1000, QImage.Format.Format_RGB32)
    m.fill(QColor("#d12020"))
    pp = QPainter(m)
    pp.fillRect(750, 0, 750, 1000, QColor("#2020d1"))
    pp.end()
    m.save(marked, "PNG")
    ok, out = print_photo(marked, PhotoSettings(mode=FILL), "marked.pdf")
    img, _ = render_pdf(out, 4)
    top, bottom = img.pixelColor(img.width() // 2, 10), img.pixelColor(img.width() // 2, img.height() - 10)
    check("rotation is a pure 90° turn: the photo's left half (red) ends up on top, the right half (blue) below",
          top.red() > 150 and bottom.blue() > 150, f"{top.name()} {bottom.name()}")

    # the preview PDF (central view) comes from the same drawing
    pv = os.path.join(tmp, "preview.pdf")
    lay = photo_to_pdf(photo, pv, page, QPageLayout.Orientation.Portrait, PhotoSettings(mode=FIT, margin_mm=5))
    img, mm = render_pdf(pv, 4)
    check("preview PDF is the paper size and shows the same margin",
          near(mm[0], 100, 0.6) and is_white(img, 3 * k, img.height() // 2) and is_red(img, 7 * k, img.height() // 2) and lay.dpi > 100, str(mm))

    # a document page in the same job as a photo stays inside the printable area; the photo reaches the edge
    doc_pdf = os.path.join(tmp, "doc.pdf")
    w = QPdfWriter(doc_pdf)
    w.setPageSize(page)
    w.setPageMargins(QMarginsF(0, 0, 0, 0))
    pp = QPainter(w)
    pp.fillRect(pp.viewport(), QColor("#20a020"))
    pp.end()
    d = QPdfDocument()
    d.load(doc_pdf)
    out = os.path.join(tmp, "mixed.pdf")
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    pr.setOutputFileName(out)
    pr.setPageSize(page)
    check("a job with a document page and a photo prints", render_leaves_to_printer([(d, 0), PhotoLeaf(photo)], pr, 1, PhotoSettings(mode=FILL)))
    d.close()
    dd = QPdfDocument()
    dd.load(out)
    check("two sheets: the document page and the photo", dd.pageCount() == 2, str(dd.pageCount()))
    dd.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    geometry()
    printing()
    print("\nALL PASS" if ok_all else "\nFAILURES ABOVE")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
