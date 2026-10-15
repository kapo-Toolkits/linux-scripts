"""Headless end-to-end check: convert -> QtPdf -> QPrinter (to a PDF file).

Run offscreen so it works without a display / real printer:
    QT_QPA_PLATFORM=offscreen python tests/smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.convert import to_pdf
from printhub.printing import render_pdf_to_printer


def make_test_image(path: str) -> None:
    img = QImage(1200, 800, QImage.Format.Format_RGB32)
    img.fill(QColor("#f0f4ff"))
    p = QPainter(img)
    p.setPen(QColor("#1a3d7c"))
    p.setFont(QFont("Arial", 64, QFont.Weight.Bold))
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "PrintHub\nsmoke test")
    p.setPen(QColor("#c02040"))
    p.drawRect(20, 20, img.width() - 40, img.height() - 40)
    p.end()
    img.save(path, "PNG")


def print_to_pdf(doc: QPdfDocument, out_pdf: str) -> bool:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(out_pdf)
    return render_pdf_to_printer(doc, printer)


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841  (needed for QtGui/QtPdf)
    work = tempfile.mkdtemp(prefix="printhub_smoke_")

    png = os.path.join(work, "sample.png")
    make_test_image(png)

    ok_all = True
    for label, src in [("image->pdf", png)]:
        pdf = to_pdf(src, work)
        doc = QPdfDocument()
        doc.load(pdf)
        pages = doc.pageCount()
        out = os.path.join(work, f"printed_{label.replace('->', '_')}.pdf")
        ok = print_to_pdf(doc, out)
        size = os.path.getsize(out) if os.path.exists(out) else 0
        status = "OK" if (ok and pages >= 1 and size > 0) else "FAIL"
        ok_all &= status == "OK"
        print(f"[{status}] {label:12s} pages={pages} -> {out} ({size} bytes)")

    print("\nArtifacts in:", work)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
