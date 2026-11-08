"""Photo mode in the window: the panel, the preview page, the info line, the batch, the switch off, both languages."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PRINTHUB_SETTINGS", "PrintHubTestPhoto")
os.environ.setdefault("PRINTHUB_STANDALONE", "1")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage, QPageSize
from PySide6.QtWidgets import QApplication

from printhub.mainwindow import MainWindow
from printhub.photo import PhotoLeaf

ok_all = True


def check(name, cond, detail=""):
    global ok_all
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail and not cond else ""))
    ok_all &= bool(cond)


def settle(app, w):
    w._photo_timer.stop()
    w._relay_photo()
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    QSettings(os.environ["PRINTHUB_SETTINGS"], "PrintHub").clear()
    tmp = tempfile.mkdtemp()
    photo = os.path.join(tmp, "p.png")
    img = QImage(1800, 1200, QImage.Format.Format_RGB32)   # 3:2 landscape, 1800 px
    img.fill(QColor("#c03030"))
    img.save(photo, "PNG")

    w = MainWindow()
    check("photo mode is on by default and greyed out until a photo is open", w.photo_box.isChecked() and not w.pscombo.isEnabled())
    w.add_files([photo])
    app.processEvents()
    check("opening a photo enables the photo settings", w.pscombo.isEnabled() and w.photo_margin.isEnabled())
    check("the old 'image scaling' is off while photo mode is on", not w.scale_combo.isEnabled())
    check("the preview is a PDF of the chosen paper (not an A4 stand-in)", os.path.basename(w.current_pdf).startswith("photo_"))
    check("the info line gives size and resolution", "cm" in w.photo_info.text() and "dpi" in w.photo_info.text(), w.photo_info.text())

    # pick 10 x 15 cm on the paper list: the print size follows the photo's orientation
    i = next(k for k in range(w.pscombo.count()) if w.pscombo.itemData(k) == ("size", (10.0, 15.0)))
    w.pscombo.setCurrentIndex(i)
    settle(app, w)
    check("10 x 15 selected: reported as 15.0 x 10.0 cm for a landscape photo", "15.0" in w.photo_info.text() and "10.0" in w.photo_info.text(), w.photo_info.text())
    check("crop / repeat are available for a fixed size, custom width/height are not", w.photo_crop.isEnabled() and w.photo_repeat.isEnabled() and not w._photo_dims.isEnabled())
    w.pscombo.setCurrentIndex(next(k for k in range(w.pscombo.count()) if w.pscombo.itemData(k) == ("size", None)))
    app.processEvents()
    check("custom size enables width and height", w._photo_dims.isEnabled())
    s = w._photo_settings()
    check("settings follow the widgets", s.mode == "size" and s.size_cm == (w.photo_w.value(), w.photo_h.value()))
    w.pscombo.setCurrentIndex(0)
    app.processEvents()
    check("fill disables the size-only options", not w.photo_crop.isEnabled() and not w.photo_repeat.isEnabled())

    # bigger print than the photo's pixels allow: the info says so
    w.pscombo.setCurrentIndex(next(k for k in range(w.pscombo.count()) if w.pscombo.itemData(k) == ("size", (20.0, 30.0))))
    settle(app, w)
    check("a 20 x 30 cm print that does not fit the A4 is reduced and says so", "does not fit" in w.photo_info.text(), w.photo_info.text())
    small = os.path.join(tmp, "small.png")
    tiny = QImage(600, 400, QImage.Format.Format_RGB32)
    tiny.fill(QColor("#3030c0"))
    tiny.save(small, "PNG")
    w.pscombo.setCurrentIndex(0)
    w.add_files([small])
    settle(app, w)
    check("a 600 px photo on a full paper is flagged as soft", "soft" in w.photo_info.text(), w.photo_info.text())
    w.queue_list.setCurrentRow(0)
    settle(app, w)

    # batch: a photo and a document page -> a PhotoLeaf and a normal leaf
    w.pscombo.setCurrentIndex(0)
    docs, leaves = w._build_batch_leaves()
    check("the batch holds the photo as a photo leaf", any(isinstance(x, PhotoLeaf) for x in leaves), str(leaves))
    for d in docs:
        d.close()

    # photo mode off: the old behaviour (A4 stand-in, image scaling available)
    w.photo_box.setChecked(False)
    settle(app, w)
    check("photo mode off: the old scaling is back and the preview is the old image page", w.scale_combo.isEnabled() and os.path.basename(w.current_pdf).startswith("image_"), w.current_pdf)
    docs, leaves = w._build_batch_leaves()
    check("photo mode off: no photo leaves", not any(isinstance(x, PhotoLeaf) for x in leaves))
    for d in docs:
        d.close()
    w.photo_box.setChecked(True)
    settle(app, w)

    # paper change re-lays the preview on the new paper
    before = w.doc.pagePointSize(0)
    ps = next((k for k in range(w.papersize_combo.count()) if w.papersize_combo.itemData(k).name() == "A3"), None)
    if ps is not None:
        w.papersize_combo.setCurrentIndex(ps)
        settle(app, w)
        after = w.doc.pagePointSize(0)
        check("another paper size gives another preview page size", abs(after.width() - before.width()) > 20, f"{before} {after}")

    # remembered between runs
    w.photo_margin.setValue(4.0)
    w._photo_changed()
    w2 = MainWindow()
    check("settings are remembered (margin)", abs(w2.photo_margin.value() - 4.0) < 1e-6)
    w2.close()

    # Georgian
    w._set_language("ka")
    app.processEvents()
    check("Georgian labels", w.photo_box.title() == "ფოტო-რეჟიმი" and w._photo_labels["photo_size"].text() == "ბეჭდვის ზომა" and "სმ" in w.pscombo.itemText(3), w.pscombo.itemText(3))
    w._set_language("en")
    w.close()
    QSettings(os.environ["PRINTHUB_SETTINGS"], "PrintHub").clear()
    print("\nALL PASS" if ok_all else "\nFAILURES ABOVE")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
