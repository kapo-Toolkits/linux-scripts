"""Verify N-up sheet counting and produce a visual 4-up sample."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QMarginsF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.printing import render_pdf_to_printer


def make_multipage_pdf(path: str, n: int) -> None:
    w = QPdfWriter(path)
    w.setResolution(150)
    w.setPageLayout(
        QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                    QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
    )
    p = QPainter(w)
    colors = ["#1a3d7c", "#c02040", "#2a7d2a", "#b8860b", "#6a1b9a", "#00838f"]
    for i in range(n):
        if i:
            w.newPage()
        p.fillRect(p.viewport(), QColor(colors[i % len(colors)]).lighter(180))
        p.setPen(QColor(colors[i % len(colors)]))
        p.setFont(QFont("Arial", 160, QFont.Weight.Bold))
        p.drawText(p.viewport(), Qt.AlignmentFlag.AlignCenter, str(i + 1))
    p.end()


def count_after_nup(doc, nup, out) -> int:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(out)
    render_pdf_to_printer(doc, printer, None, nup)
    d = QPdfDocument()
    d.load(out)
    n = d.pageCount()
    d.close()
    return n


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    work = tempfile.mkdtemp(prefix="printhub_nup_")
    src = os.path.join(work, "src.pdf")
    make_multipage_pdf(src, 5)
    doc = QPdfDocument()
    doc.load(src)

    ok = True
    for nup, expected_sheets in [(1, 5), (2, 3), (4, 2), (9, 1)]:
        got = count_after_nup(doc, nup, os.path.join(work, f"nup{nup}.pdf"))
        status = "OK" if got == expected_sheets else "FAIL"
        ok &= status == "OK"
        print(f"  [{status}] 5 pages, {nup}-up -> {got} sheet(s) (expected {expected_sheets})")

    # Visual: render sheet 0 of the 4-up output to a PNG for inspection.
    d = QPdfDocument()
    d.load(os.path.join(work, "nup4.pdf"))
    img = d.render(0, QSize(827, 1169))  # ~A4 @ 100dpi
    shot = os.path.join(os.environ.get("PRINTHUB_SHOTS") or __import__("tempfile").gettempdir(), "nup4_sample.png")  # set PRINTHUB_SHOTS=docs to refresh the README images
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    img.save(shot, "PNG")
    d.close()
    doc.close()
    print(f"  visual 4-up sheet -> {shot} ({os.path.getsize(shot)} bytes)")

    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
