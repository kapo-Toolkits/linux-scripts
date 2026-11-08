"""Render a QPdfDocument onto a QPrinter (or a preview paint device).

This is the single function every print path funnels through: the real
Print dialog, the Print Preview dialog, and the headless smoke test all
call it. Qt maps the QPrinter to GDI on Windows, Cocoa on macOS and CUPS
on Linux, so this code is platform-agnostic.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPageLayout, QPainter
from PySide6.QtPdf import QPdfDocument

from .photo import PhotoLeaf, PhotoSettings, layout_for, load_image, paint_layout

# Cap raster page size so a huge page can't blow up memory.
_MAX_PX = 5000

# N-up layouts: pages-per-sheet -> (columns, rows), filled in reading order.
NUP_GRID: dict[int, tuple[int, int]] = {
    1: (1, 1),
    2: (2, 1),
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
    16: (4, 4),
}


def parse_page_range(text: str, page_count: int) -> list[int]:
    """Parse "1-3, 5, 8-10" into ordered, de-duplicated 0-based page indices.

    Blank text means "all pages". Open-ended parts are allowed: "-3" = up to
    page 3, "5-" = page 5 to the end. Out-of-range pages are dropped; a part
    that isn't a number raises ValueError.
    """
    text = (text or "").strip()
    if not text:
        return list(range(page_count))

    pages: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            start = int(a) if a.strip() else 1
            end = int(b) if b.strip() else page_count
        else:
            start = end = int(part)
        if start > end:
            start, end = end, start
        for p in range(start, end + 1):
            if 1 <= p <= page_count:
                pages.append(p - 1)

    seen: set[int] = set()
    ordered: list[int] = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _render_page_image(doc: QPdfDocument, res: int, index: int):
    """Render one PDF page to a QImage at ~`res` dpi (capped)."""
    page_pt = doc.pagePointSize(index)  # size in PostScript points (1/72")
    if page_pt.width() <= 0 or page_pt.height() <= 0:
        return None
    img_w = round(page_pt.width() / 72.0 * res)
    img_h = round(page_pt.height() / 72.0 * res)
    scale = min(1.0, _MAX_PX / max(img_w, img_h, 1))
    image = doc.render(
        index, QSize(max(1, round(img_w * scale)), max(1, round(img_h * scale)))
    )
    return None if image.isNull() else image


def _draw_into(painter: QPainter, image, rect: QRectF) -> None:
    """Fit `image` into `rect` preserving aspect ratio, centered."""
    s = image.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
    x = rect.x() + (rect.width() - s.width()) / 2
    y = rect.y() + (rect.height() - s.height()) / 2
    painter.drawImage(QRectF(x, y, s.width(), s.height()), image)


def _paint_sheet(painter, res, sheet, cols, rows, area=None) -> None:
    """Lay a group of (doc, page_index) leaves out on one printer sheet (in `area`, default: the paintable area)."""
    vp = painter.viewport() if area is None else area  # paintable area in device pixels
    cell_w = vp.width() / cols
    cell_h = vp.height() / rows
    gutter = min(cell_w, cell_h) * 0.04 if (cols * rows) > 1 else 0.0

    for slot, (doc, index) in enumerate(sheet):
        image = _render_page_image(doc, res, index)
        if image is None:
            continue
        col = slot % cols
        row = slot // cols
        cell = QRectF(
            vp.x() + col * cell_w + gutter / 2,
            vp.y() + row * cell_h + gutter / 2,
            cell_w - gutter,
            cell_h - gutter,
        )
        _draw_into(painter, image, cell)


def _group_sheets(leaves, per_sheet):
    """Consecutive document pages share a sheet (N-up); a photo always has a sheet of its own."""
    sheets, cur = [], []
    for leaf in leaves:
        if isinstance(leaf, PhotoLeaf):
            if cur:
                sheets.append(cur)
                cur = []
            sheets.append([leaf])
        else:
            cur.append(leaf)
            if len(cur) == per_sheet:
                sheets.append(cur)
                cur = []
    if cur:
        sheets.append(cur)
    return sheets


def render_leaves_to_printer(leaves, printer, nup: int = 1, photo: PhotoSettings | None = None) -> bool:
    """Paint a flat list of leaves onto `printer`.

    A leaf is (QPdfDocument, page_index) or a `PhotoLeaf` (a photo file, laid out by `photo` settings on the whole paper).
    This is the batch-capable core: leaves may come from several documents, so a single print job can span a whole queue.
    N-up groups consecutive document pages onto each sheet. Copies come from `printer.copyCount()` (driver-handled when
    possible, otherwise repeated); duplex is a printer property.

    With photos the painting origin is the paper's corner (full page), so a photo can reach the paper's edge; document
    pages in the same job are still kept inside the printable area.
    """
    leaves = [x for x in leaves if isinstance(x, PhotoLeaf) or 0 <= x[1] < x[0].pageCount()]
    if not leaves:
        return False

    cols, rows = NUP_GRID.get(nup, (1, 1))
    sheets = _group_sheets(leaves, cols * rows)
    has_photo = any(isinstance(x, PhotoLeaf) for x in leaves)
    photo = photo or PhotoSettings()

    copies = max(1, printer.copyCount())
    outer = 1 if printer.supportsMultipleCopies() else copies

    if has_photo:
        printer.setFullPage(True)
    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        res = printer.resolution()
        pl = printer.pageLayout()
        paper = pl.fullRect(QPageLayout.Unit.Millimeter)
        paper_mm = (paper.width(), paper.height())
        printable = QRectF(pl.paintRectPixels(res)) if has_photo else None
        images = {}
        first = True
        for _ in range(outer):
            for sheet in sheets:
                if not first:
                    printer.newPage()
                first = False
                if isinstance(sheet[0], PhotoLeaf):
                    path = sheet[0].path
                    if path not in images:
                        images[path] = load_image(path)
                    vp = painter.viewport()
                    paint_layout(painter, QRectF(vp), images[path], layout_for(images[path], paper_mm, photo))
                else:
                    _paint_sheet(painter, res, sheet, cols, rows, printable)
        return True
    finally:
        painter.end()


def render_pdf_to_printer(
    doc: QPdfDocument, printer, pages: list[int] | None = None, nup: int = 1
) -> bool:
    """Single-document convenience wrapper around `render_leaves_to_printer`.

    `pages` is a list of 0-based indices (as from `parse_page_range`); None
    prints every page. Returns True on success.
    """
    indices = range(doc.pageCount()) if pages is None else pages
    return render_leaves_to_printer([(doc, i) for i in indices], printer, nup)
