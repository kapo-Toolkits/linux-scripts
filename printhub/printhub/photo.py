"""Photo mode: put a photo on the paper the way a photo print needs it.

A document page is fitted into the printable area; a photo is different: the paper size is the print size (10x15, A4 ...),
the photo should cover it edge to edge (or sit at an exact size), and what the preview shows must be what comes out.
So the layout is decided here, in millimetres on the *paper* (not on an A4 stand-in page), by one pure function
(`layout_photo`), and one painter (`paint_layout`) draws it on any QPainter: the printer, the print preview and the
preview PDF all use the same two functions.

Modes
  fill    cover the whole paper (inside the margin); the overflow is cropped        -> borderless-style prints
  fit     the whole photo inside the margin, nothing cropped                        -> margins show on one side
  size    an exact print size (9x13, 10x15, ... or your own), cropped to it or fitted in it, optionally repeated
          to fill the sheet (4 prints of 10x15 on an A4)
  actual  the photo's own physical size from its DPI
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtGui import QImage, QImageReader, QPageLayout, QPageSize, QPainter, QPdfWriter

FILL, FIT, SIZE, ACTUAL = "fill", "fit", "size", "actual"
MODES = (FILL, FIT, SIZE, ACTUAL)
CENTER, TOP_LEFT = "center", "top_left"
MM_PER_IN = 25.4

# Print sizes offered as presets, width x height in cm (the photo-lab sizes; the inch names are the usual ones)
PRESETS_CM = [(9.0, 13.0), (10.0, 15.0), (13.0, 18.0), (15.0, 21.0), (20.0, 25.0), (20.0, 30.0)]
PRESET_LABELS = {(9.0, 13.0): "9 × 13 cm", (10.0, 15.0): "10 × 15 cm  (4×6″)", (13.0, 18.0): "13 × 18 cm  (5×7″)",
                 (15.0, 21.0): "15 × 21 cm  (A5)", (20.0, 25.0): "20 × 25 cm  (8×10″)", (20.0, 30.0): "20 × 30 cm  (8×12″)"}

DPI_GOOD, DPI_OK = 240.0, 150.0     # photo printing wants ~300; below ~150 it looks soft, below ~100 it looks coarse


@dataclass(frozen=True)
class PhotoSettings:
    mode: str = FILL
    size_cm: tuple = (10.0, 15.0)   # SIZE: width x height as typed; swapped to match the photo when auto_rotate is on
    margin_mm: float = 0.0
    anchor: str = CENTER            # where a fixed-size print / the actual-size photo sits: center or top_left
    auto_rotate: bool = True        # turn the photo (or the print box) 90° when that suits the paper better
    crop_to_size: bool = True       # SIZE: fill the box (crop the overflow); False = the whole photo inside the box
    repeat: bool = False            # SIZE: as many prints as fit on the sheet
    gap_mm: float = 2.0             # between repeated prints


@dataclass(frozen=True)
class Placement:
    dest: tuple        # (x, y, w, h) in mm on the paper: where the photo is drawn, as it appears (after any rotation)
    clip: tuple        # (x, y, w, h) in mm: nothing is drawn outside this
    rotated: bool      # the photo is turned 90° clockwise inside dest


@dataclass(frozen=True)
class Layout:
    paper: tuple                  # (w, h) mm
    placements: tuple
    dpi: float                    # the lowest effective resolution of the photo over the placements
    cropped: float                # fraction of the photo that is not shown (0..1)
    shrunk: bool = False          # the requested print size did not fit the paper and was reduced
    box_mm: tuple = (0.0, 0.0)    # the size of one print (width, height), for the info line


def _fit_in(box, iw, ih, crop, anchor_top_left=False):
    """The (x, y, w, h) of an iw:ih image scaled into box (x, y, w, h): to cover it (crop) or to sit inside it."""
    bx, by, bw, bh = box
    s = max(bw / iw, bh / ih) if crop else min(bw / iw, bh / ih)
    w, h = iw * s, ih * s
    if anchor_top_left and not crop:
        return (bx, by, w, h)
    return (bx + (bw - w) / 2, by + (bh - h) / 2, w, h)


def _place_in_box(box, img_px, crop, auto_rotate, anchor_top_left=False):
    """-> (Placement, rotated). The photo is turned 90° first when auto_rotate and its orientation differs from the box's."""
    iw, ih = img_px
    bw, bh = box[2], box[3]
    rotated = bool(auto_rotate and bw != bh and iw != ih and (iw > ih) != (bw > bh))
    pw, ph = (ih, iw) if rotated else (iw, ih)             # the photo's size in pixels as it appears
    dest = _fit_in(box, pw, ph, crop, anchor_top_left)
    return Placement(dest=dest, clip=box, rotated=rotated)


def _effective_dpi(p, img_px):
    iw, ih = img_px
    shown_w_px = ih if p.rotated else iw
    return shown_w_px / (p.dest[2] / MM_PER_IN) if p.dest[2] > 0 else 0.0


def _cropped_fraction(p, img_px):
    """How much of the photo falls outside its clip rectangle (0..1)."""
    x, y, w, h = p.dest
    cx, cy, cw, ch = p.clip
    vis_w = max(0.0, min(x + w, cx + cw) - max(x, cx))
    vis_h = max(0.0, min(y + h, cy + ch) - max(y, cy))
    return 1.0 - (vis_w * vis_h) / (w * h) if w * h > 0 else 0.0


def layout_photo(paper_mm, img_px, dpi, s: PhotoSettings) -> Layout:
    """Where the photo goes on a paper of paper_mm (w, h), for an image of img_px (w, h) pixels with the file's dpi (x, y)."""
    W, H = float(paper_mm[0]), float(paper_mm[1])
    iw, ih = img_px
    m = max(0.0, min(float(s.margin_mm), min(W, H) / 2 - 1))
    area = (m, m, W - 2 * m, H - 2 * m)
    ax, ay, aw, ah = area
    top_left = s.anchor == TOP_LEFT
    shrunk = False
    box_mm = (aw, ah)
    if s.mode == SIZE:
        tw, th = s.size_cm[0] * 10.0, s.size_cm[1] * 10.0
        photo_landscape = iw > ih
        if s.auto_rotate and tw != th and (tw > th) != photo_landscape:
            tw, th = th, tw                                   # the print follows the photo's orientation
        boxes_grid = None
        if s.repeat:
            best = None
            for bw, bh in ((tw, th), (th, tw)) if s.auto_rotate else ((tw, th),):
                cols = int((aw + s.gap_mm) // (bw + s.gap_mm))
                rows = int((ah + s.gap_mm) // (bh + s.gap_mm))
                key = (cols * rows, (bw > bh) == photo_landscape)
                if cols * rows and (best is None or key > best[0]):
                    best = (key, bw, bh, cols, rows)
            if best:
                _, bw, bh, cols, rows = best
                gw, gh = cols * bw + (cols - 1) * s.gap_mm, rows * bh + (rows - 1) * s.gap_mm
                ox = ax if top_left else ax + (aw - gw) / 2
                oy = ay if top_left else ay + (ah - gh) / 2
                boxes_grid = [(ox + c * (bw + s.gap_mm), oy + r * (bh + s.gap_mm), bw, bh) for r in range(rows) for c in range(cols)]
                tw, th = bw, bh
        if boxes_grid is None:
            f = min(1.0, aw / tw, ah / th)
            if f < 1.0:
                shrunk = True
                tw, th = tw * f, th * f
            ox = ax if top_left else ax + (aw - tw) / 2
            oy = ay if top_left else ay + (ah - th) / 2
            boxes_grid = [(ox, oy, tw, th)]
        placements = [_place_in_box(b, img_px, s.crop_to_size, s.auto_rotate) for b in boxes_grid]
        box_mm = (tw, th)
    elif s.mode == ACTUAL:
        dx, dy = dpi
        w, h = iw / dx * MM_PER_IN, ih / dy * MM_PER_IN
        x = ax if top_left else ax + (aw - w) / 2
        y = ay if top_left else ay + (ah - h) / 2
        placements = [Placement(dest=(x, y, w, h), clip=area, rotated=False)]
        box_mm = (w, h)
    else:                                                     # FILL / FIT
        placements = [_place_in_box(area, img_px, s.mode == FILL, s.auto_rotate, top_left)]
    dpis = [_effective_dpi(p, img_px) for p in placements]
    return Layout(paper=(W, H), placements=tuple(placements), dpi=min(dpis) if dpis else 0.0,
                  cropped=max((_cropped_fraction(p, img_px) for p in placements), default=0.0), shrunk=shrunk, box_mm=box_mm)


def quality(dpi: float) -> str:
    """'good' | 'ok' | 'low' for an effective resolution."""
    return "good" if dpi >= DPI_GOOD else "ok" if dpi >= DPI_OK else "low"


def load_image(path: str) -> QImage:
    """The photo as it is meant to be seen: the camera's rotation (EXIF) applied."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise ValueError(f"Cannot load image: {path}")
    return img


def image_dpi(img: QImage) -> tuple:
    dx, dy = img.dotsPerMeterX() * 0.0254, img.dotsPerMeterY() * 0.0254
    return (dx if dx > 1 else 96.0, dy if dy > 1 else 96.0)


def layout_for(img: QImage, paper_mm, s: PhotoSettings) -> Layout:
    return layout_photo(paper_mm, (img.width(), img.height()), image_dpi(img), s)


def paint_layout(painter: QPainter, target: QRectF, img: QImage, layout: Layout) -> None:
    """Draw the photo on `target` (the whole paper, in painter units) as `layout` says."""
    W, H = layout.paper
    sx, sy = target.width() / W, target.height() / H
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for p in layout.placements:
        painter.save()
        cx, cy, cw, ch = p.clip
        painter.setClipRect(QRectF(target.x() + cx * sx, target.y() + cy * sy, cw * sx, ch * sy))
        x, y, w, h = p.dest
        dest = QRectF(target.x() + x * sx, target.y() + y * sy, w * sx, h * sy)
        if p.rotated:                                          # turned 90° clockwise about the centre of dest
            painter.translate(dest.center())
            painter.rotate(90)
            painter.drawImage(QRectF(-dest.height() / 2, -dest.width() / 2, dest.height(), dest.width()), img)
        else:
            painter.drawImage(dest, img)
        painter.restore()


def paper_mm(page_size: QPageSize, orientation) -> tuple:
    """(width, height) in mm of the paper as it lies in the printer."""
    sz = page_size.size(QPageSize.Unit.Millimeter)
    w, h = sz.width(), sz.height()
    lo, hi = min(w, h), max(w, h)
    return (hi, lo) if orientation == QPageLayout.Orientation.Landscape else (lo, hi)


@dataclass(frozen=True)
class PhotoLeaf:
    """A photo in a print job: it is painted from the file by the photo layout, one sheet each."""
    path: str


def photo_to_pdf(src: str, out_pdf: str, page_size: QPageSize, orientation, s: PhotoSettings) -> Layout:
    """The preview of a photo on the chosen paper: a PDF page of exactly that paper, drawn by the same code as the print."""
    img = load_image(src)
    layout = QPageLayout(page_size, orientation, QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer = QPdfWriter(out_pdf)
    writer.setResolution(300)
    writer.setPageLayout(layout)
    lay = layout_for(img, paper_mm(page_size, orientation), s)
    painter = QPainter(writer)
    try:
        paint_layout(painter, QRectF(painter.viewport()), img, lay)
    finally:
        painter.end()
    return lay
