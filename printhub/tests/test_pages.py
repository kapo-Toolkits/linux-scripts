"""Verify page-range parsing and that range+copies reach the printed output."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.printing import parse_page_range, render_pdf_to_printer


def make_multipage_pdf(path: str, n: int) -> None:
    w = QPdfWriter(path)
    w.setResolution(150)
    w.setPageLayout(
        QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                    QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
    )
    p = QPainter(w)
    p.setFont(QFont("Arial", 120, QFont.Weight.Bold))
    for i in range(n):
        if i:
            w.newPage()
        p.setPen(QColor("#1a3d7c"))
        p.drawText(p.viewport(), Qt.AlignmentFlag.AlignCenter, str(i + 1))
    p.end()


def pdf_page_count(path: str) -> int:
    d = QPdfDocument()
    d.load(path)
    n = d.pageCount()
    d.close()
    return n


def test_parse() -> bool:
    cases = {
        ("", 5): [0, 1, 2, 3, 4],
        ("2", 5): [1],
        ("1-3", 5): [0, 1, 2],
        ("3-1", 5): [0, 1, 2],           # reversed range normalized
        ("1-3, 5", 5): [0, 1, 2, 4],
        ("2,2,2", 5): [1],               # de-duplicated
        ("-3", 5): [0, 1, 2],            # open start
        ("4-", 5): [3, 4],               # open end
        ("1-99", 5): [0, 1, 2, 3, 4],    # clamped
        ("8-10", 5): [],                 # out of range
    }
    ok = True
    for (text, count), expected in cases.items():
        got = parse_page_range(text, count)
        status = "OK" if got == expected else "FAIL"
        ok &= status == "OK"
        print(f"  [{status}] parse({text!r},{count}) -> {got}  expected {expected}")
    try:
        parse_page_range("abc", 5)
        print("  [FAIL] 'abc' should raise ValueError")
        ok = False
    except ValueError:
        print("  [OK] parse('abc') raises ValueError")
    return ok


def test_render() -> bool:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    work = tempfile.mkdtemp(prefix="printhub_pages_")
    src = os.path.join(work, "src.pdf")
    make_multipage_pdf(src, 5)

    doc = QPdfDocument()
    doc.load(src)
    assert doc.pageCount() == 5

    pages = parse_page_range("1, 3", doc.pageCount())  # -> [0, 2]
    copies = 2

    out = os.path.join(work, "out.pdf")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(out)
    printer.setCopyCount(copies)

    driver_copies = printer.supportsMultipleCopies()
    ok = render_pdf_to_printer(doc, printer, pages)
    doc.close()

    produced = pdf_page_count(out)
    expected = len(pages) if driver_copies else len(pages) * copies
    status = "OK" if (ok and produced == expected) else "FAIL"
    print(f"  [{status}] pages={[p+1 for p in pages]} copies={copies} "
          f"driverCopies={driver_copies} -> {produced} pages (expected {expected})")
    return status == "OK"


def main() -> int:
    print("page-range parsing:")
    a = test_parse()
    print("render range + copies:")
    b = test_render()
    print("\nALL PASS" if (a and b) else "\nFAILURES ABOVE")
    return 0 if (a and b) else 1


if __name__ == "__main__":
    raise SystemExit(main())
