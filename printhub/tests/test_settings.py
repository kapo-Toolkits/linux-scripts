"""Verify the settings panel applies driver-driven and static parameters."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PRINTHUB_SETTINGS", "PrintHubTest")   # never touch the real saved preferences
os.environ.setdefault("PRINTHUB_STANDALONE", "1")             # ignore the toolkit-wide language in tests

from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from printhub.mainwindow import MainWindow


def combo_index_by(combo, pred):
    for i in range(combo.count()):
        if pred(combo.itemData(i)):
            return i
    return -1


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    w = MainWindow()
    ok = True

    # Paper size list is populated (from a driver, or the static fallback) and
    # every entry is a real QPageSize.
    paper_ok = w.papersize_combo.count() > 0 and all(
        isinstance(w.papersize_combo.itemData(i), QPageSize)
        for i in range(w.papersize_combo.count())
    )
    print(f"  [{'OK' if paper_ok else 'FAIL'}] paper sizes populated ({w.papersize_combo.count()} entries)")
    ok &= paper_ok

    # Resolution (quality) list populated with integer dpi values.
    res_ok = w.resolution_combo.count() > 0 and all(
        isinstance(w.resolution_combo.itemData(i), int)
        for i in range(w.resolution_combo.count())
    )
    print(f"  [{'OK' if res_ok else 'FAIL'}] resolutions populated ({w.resolution_combo.count()} entries)")
    ok &= res_ok

    # Select a specific paper size + highest resolution, grayscale, 3 copies.
    a4 = combo_index_by(w.papersize_combo, lambda ps: ps.name() == "A4")
    if a4 < 0:
        a4 = 0
    w.papersize_combo.setCurrentIndex(a4)
    chosen_paper = w.papersize_combo.currentData().name()
    w.resolution_combo.setCurrentIndex(w.resolution_combo.count() - 1)
    chosen_dpi = w.resolution_combo.currentData()

    w.orient_combo.setCurrentIndex(
        combo_index_by(w.orient_combo, lambda d: d == QPageLayout.Orientation.Landscape)
    )
    w.color_combo.setCurrentIndex(
        combo_index_by(w.color_combo, lambda d: d == QPrinter.ColorMode.GrayScale)
    )
    w.copies_spin.setValue(3)
    w.collate_check.setChecked(False)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    w._configure_printer(printer)

    checks = {
        f"paper size = {chosen_paper}": printer.pageLayout().pageSize().name() == chosen_paper,
        "orientation = Landscape":
            printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape,
        f"resolution = {chosen_dpi}": printer.resolution() == chosen_dpi,
        "color mode = GrayScale": printer.colorMode() == QPrinter.ColorMode.GrayScale,
        "copies = 3": printer.copyCount() == 3,
        "collate = False": printer.collateCopies() is False,
    }
    for name, passed in checks.items():
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")

    # Preview keeps 1 copy but the same paper size.
    p2 = QPrinter(QPrinter.PrinterMode.HighResolution)
    w._configure_printer(p2, with_copies=False)
    prev_ok = p2.copyCount() == 1 and p2.pageLayout().pageSize().name() == chosen_paper
    print(f"  [{'OK' if prev_ok else 'FAIL'}] preview keeps 1 copy, same paper size")
    ok &= prev_ok

    w.close()
    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
