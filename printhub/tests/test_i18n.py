"""Verify bilingual UI (English default) and light/dark theme switching."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PRINTHUB_SETTINGS", "PrintHubTest")   # never touch the real saved preferences
os.environ.setdefault("PRINTHUB_STANDALONE", "1")             # ignore the toolkit-wide language in tests

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from printhub.mainwindow import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    QSettings(os.environ.get("PRINTHUB_SETTINGS", "PrintHub"), "PrintHub").clear()  # deterministic defaults

    w = MainWindow()
    ok = True

    # Defaults: English + light.
    d1 = w.i18n.lang == "en" and w._dark is False
    print(f"  [{'OK' if d1 else 'FAIL'}] defaults: lang=en, light theme")
    ok &= d1

    en_ok = (
        w.act_print.text() == "Print…"
        and w._form_labels["paper_size"].text() == "Paper size"
        and w.duplex_combo.itemText(0) == "Off"
    )
    print(f"  [{'OK' if en_ok else 'FAIL'}] English labels present")
    ok &= en_ok

    # Switch to Georgian.
    w._set_language("ka")
    ka_ok = (
        w.act_print.text() == "ბეჭდვა…"
        and w._form_labels["paper_size"].text() == "ფურცლის ზომა"
        and w.duplex_combo.itemText(0) == "გამორთ."
        and w.i18n.t("app_subtitle") == "უნივერსალური ბეჭდვა"
    )
    print(f"  [{'OK' if ka_ok else 'FAIL'}] Georgian labels after switch")
    ok &= ka_ok

    # Combo data survives retranslation (only labels change).
    from PySide6.QtGui import QPageLayout
    data_ok = w.orient_combo.itemData(0) == QPageLayout.Orientation.Portrait
    print(f"  [{'OK' if data_ok else 'FAIL'}] combo data unchanged by language switch")
    ok &= data_ok

    # Theme toggle doesn't crash and updates state; persists to QSettings.
    w._set_theme(True)
    dark_ok = w._dark is True and QSettings(os.environ.get("PRINTHUB_SETTINGS", "PrintHub"), "PrintHub").value("dark", type=bool) is True
    w._set_theme(False)
    light_ok = w._dark is False
    print(f"  [{'OK' if (dark_ok and light_ok) else 'FAIL'}] theme dark<->light toggles + persists")
    ok &= dark_ok and light_ok

    # Persistence of language across a fresh window.
    w2 = MainWindow()
    persist_ok = w2.i18n.lang == "ka"
    print(f"  [{'OK' if persist_ok else 'FAIL'}] language persists to a new window")
    ok &= persist_ok

    QSettings(os.environ.get("PRINTHUB_SETTINGS", "PrintHub"), "PrintHub").clear()
    w.close(); w2.close()
    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
