"""Verify the batch queue: multiple files -> one print job, in order."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PRINTHUB_SETTINGS", "PrintHubTest")   # never touch the real saved preferences
os.environ.setdefault("PRINTHUB_STANDALONE", "1")             # ignore the toolkit-wide language in tests

from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.mainwindow import MainWindow
from printhub.printing import render_leaves_to_printer


def make_pdf(path: str, n: int) -> None:
    w = QPdfWriter(path)
    w.setResolution(150)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                QPageLayout.Orientation.Portrait,
                                QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter))
    p = QPainter(w)
    for i in range(n):
        if i:
            w.newPage()
        p.drawText(p.viewport(), Qt.AlignmentFlag.AlignCenter, f"pdf p{i+1}")
    p.end()


def make_png(path: str, color: str) -> None:
    im = QImage(600, 400, QImage.Format.Format_RGB32)
    im.fill(QColor(color))
    im.save(path, "PNG")


def out_pages(leaves, nup, out) -> int:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(out)
    render_leaves_to_printer(leaves, printer, nup)
    d = QPdfDocument()
    d.load(out)
    n = d.pageCount()
    d.close()
    return n


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    work = tempfile.mkdtemp(prefix="printhub_batch_")

    a = os.path.join(work, "a.png"); make_png(a, "#e0f0ff")
    b = os.path.join(work, "b.pdf"); make_pdf(b, 3)
    c = os.path.join(work, "c.png"); make_png(c, "#ffe0e0")
    # queue = [image(1), pdf(3), image(1)]  -> 5 source pages total

    win = MainWindow()
    win.add_files([a, b, c])

    ok = True
    q_ok = len(win.queue) == 3 and win.queue_list.count() == 3 and win.act_print_all.isEnabled()
    print(f"  [{'OK' if q_ok else 'FAIL'}] queue built: {len(win.queue)} items, PrintAll enabled")
    ok &= q_ok

    # Build the batch leaves the same way print_all does, then render.
    docs, leaves = win._build_batch_leaves()
    total = len(leaves)
    t_ok = total == 5
    print(f"  [{'OK' if t_ok else 'FAIL'}] total pages across queue = {total} (expected 5)")
    ok &= t_ok

    n1 = out_pages(leaves, 1, os.path.join(work, "all_1up.pdf"))
    o1 = n1 == 5
    print(f"  [{'OK' if o1 else 'FAIL'}] 1-up job -> {n1} sheets (expected 5)")
    ok &= o1

    n4 = out_pages(leaves, 4, os.path.join(work, "all_4up.pdf"))
    o4 = n4 == 2
    print(f"  [{'OK' if o4 else 'FAIL'}] 4-up job -> {n4} sheets (expected 2)")
    ok &= o4

    for d in docs:
        d.close()

    # Per-file page range: "1" -> first page of each file -> 3 pages.
    win.pages_edit.setText("1")
    docs2, leaves2 = win._build_batch_leaves()
    r_ok = len(leaves2) == 3
    print(f"  [{'OK' if r_ok else 'FAIL'}] page-range '1' per file -> {len(leaves2)} pages (expected 3)")
    ok &= r_ok
    for d in docs2:
        d.close()

    # Remove one from the queue.
    win.pages_edit.setText("")
    win.queue_list.setCurrentRow(1)
    win.queue_list.setFocus()
    win._remove_selected()
    rm_ok = len(win.queue) == 2 and win.queue_list.count() == 2
    print(f"  [{'OK' if rm_ok else 'FAIL'}] remove item -> {len(win.queue)} left (expected 2)")
    ok &= rm_ok

    win.close()
    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
