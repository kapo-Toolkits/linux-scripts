"""Main window: open/drop a file, preview it, and print with native settings."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import (
    QAbstractPrintDialog,
    QPrintDialog,
    QPrintPreviewDialog,
    QPrinter,
    QPrinterInfo,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .convert import (
    IMAGE_EXTS,
    SCALE_ACTUAL,
    SCALE_FILL,
    SCALE_FIT,
    to_pdf,
)
from .i18n import I18n, initial_language, share_language
from .printing import (
    NUP_GRID,
    parse_page_range,
    render_leaves_to_printer,
    render_pdf_to_printer,
)
from .theme import apply_theme

# Combo entries as (i18n-key, data). Labels are translated at build/retranslate.
_DUPLEX_MODES = [
    ("dup_off", QPrinter.DuplexMode.DuplexNone),
    ("dup_long", QPrinter.DuplexMode.DuplexLongSide),
    ("dup_short", QPrinter.DuplexMode.DuplexShortSide),
]
_SCALE_MODES = [
    ("scale_fit", SCALE_FIT),
    ("scale_fill", SCALE_FILL),
    ("scale_actual", SCALE_ACTUAL),
]
_ORIENTATIONS = [
    ("ori_portrait", QPageLayout.Orientation.Portrait),
    ("ori_landscape", QPageLayout.Orientation.Landscape),
]
_COLOR_MODES = [
    ("col_color", QPrinter.ColorMode.Color),
    ("col_gray", QPrinter.ColorMode.GrayScale),
]

# Paper sizes keep their proper names (not translated) -> QPageSize.PageSizeId.
_PAPER_SIZES = [
    ("A4", QPageSize.PageSizeId.A4),
    ("A3", QPageSize.PageSizeId.A3),
    ("A5", QPageSize.PageSizeId.A5),
    ("Letter", QPageSize.PageSizeId.Letter),
    ("Legal", QPageSize.PageSizeId.Legal),
]

_OPEN_FILTER = (
    "All supported (*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp "
    "*.doc *.docx *.odt *.rtf *.txt *.xls *.xlsx *.ods *.csv *.ppt *.pptx *.odp)"
    ";;All files (*.*)"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(960, 720)
        self.setAcceptDrops(True)

        # Persisted preferences (language + theme). Defaults: English, light.
        self._settings = QSettings(os.environ.get("PRINTHUB_SETTINGS", "PrintHub"), "PrintHub")
        self.i18n = I18n(initial_language(self._settings.value("lang", None)))
        self._dark = self._settings.value("dark", False, type=bool)
        apply_theme(QApplication.instance(), self._dark)

        # Combos whose item labels are translated: (combo, [i18n keys]).
        self._i18n_combos: list[tuple[QComboBox, list[str]]] = []
        self._form_labels: dict[str, QLabel] = {}
        # Duplex modes the selected printer supports (None = show all).
        self._duplex_supported = None

        # Temp workspace for converted PDFs; cleaned up on exit.
        # ignore_cleanup_errors: on Windows a still-open PDF handle must not
        # turn teardown into a traceback.
        self._tmp = tempfile.TemporaryDirectory(
            prefix="printhub_", ignore_cleanup_errors=True
        )
        self.doc = QPdfDocument(self)
        self.current_pdf: str | None = None
        self.current_source: str | None = None
        self.queue: list[str] = []  # source paths, in print order

        self.view = QPdfView(self)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setDocument(self.doc)

        self.placeholder = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color:#888; font-size:16px;")

        self.stack = QStackedWidget()
        self.stack.addWidget(self.placeholder)  # index 0
        self.stack.addWidget(self.view)         # index 1

        # Queue panel (left): the batch of files to print, in order.
        self.queue_list = QListWidget()
        self.queue_list.setMinimumWidth(180)
        self.queue_list.setMaximumWidth(360)
        self.queue_list.currentRowChanged.connect(self._on_queue_selected)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.queue_list)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 720])
        self.setCentralWidget(splitter)

        self._build_settings_dock()  # creates the parameter widgets
        self._build_toolbar()        # actions only
        self._build_menu()           # language + theme
        self._populate_printers()            # driver list
        self._populate_from_printer()        # driver capabilities
        self._set_print_enabled(False)
        self.scale_combo.setEnabled(False)  # enabled only once an image loads
        self.retranslate()

    # ------------------------------------------------------------------ UI
    def _combo(self, entries, tooltip):
        """Build a combo whose labels are i18n keys; track it for retranslate."""
        c = QComboBox()
        keys = []
        for key, data in entries:
            c.addItem(self.i18n.t(key), data)
            keys.append(key)
        c.setToolTip(tooltip)
        self._i18n_combos.append((c, keys))
        return c

    def _build_settings_dock(self) -> None:
        """Right-hand panel with every print parameter (like a print dialog)."""
        # Page-range field: e.g. "1-3, 5, 8-10"; blank = all pages.
        # Printer picker — its capabilities drive the paper/quality/duplex lists.
        self.printer_combo = QComboBox()
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)

        self.pages_edit = QLineEdit()
        self.pages_edit.returnPressed.connect(self.print_file)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 999)
        self.copies_spin.setValue(1)

        self.collate_check = QCheckBox()
        self.collate_check.setChecked(True)

        # Dynamic (filled from the driver): paper size, resolution, duplex.
        self.papersize_combo = QComboBox()
        self.resolution_combo = QComboBox()
        self.duplex_combo = QComboBox()

        # Static, translated combos.
        self.orient_combo = self._combo(_ORIENTATIONS, "Orientation")
        self.nup_combo = self._combo([(str(n), n) for n in sorted(NUP_GRID)], "Pages per sheet")
        self.color_combo = self._combo(_COLOR_MODES, "Color / grayscale")

        # Image scaling (images only). Changing it re-lays the page.
        self.scale_combo = self._combo(_SCALE_MODES, "Image scaling")
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)

        form = QFormLayout()
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        rows = [
            ("printer", self.printer_combo),
            ("pages", self.pages_edit),
            ("copies", self.copies_spin),
            ("", self.collate_check),
            ("paper_size", self.papersize_combo),
            ("orientation", self.orient_combo),
            ("per_sheet", self.nup_combo),
            ("two_sided", self.duplex_combo),
            ("color", self.color_combo),
            ("resolution", self.resolution_combo),
            ("image_scaling", self.scale_combo),
        ]
        for key, widget in rows:
            lbl = QLabel()
            if key:
                self._form_labels[key] = lbl
            form.addRow(lbl, widget)

        self._panel_title = QLabel()
        self._panel_title.setStyleSheet("font-weight:600; padding:8px 0 0 4px;")

        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._panel_title)
        v.addLayout(form)
        v.addStretch(1)

        self._settings_dock = QDockWidget(self)
        self._settings_dock.setObjectName("settings")
        self._settings_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._settings_dock.setWidget(panel)
        self._settings_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._settings_dock)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.act_open = QAction(self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.open_file)

        self.act_preview = QAction(self)
        self.act_preview.triggered.connect(self.print_preview)

        self.act_print = QAction(self)
        self.act_print.setShortcut(QKeySequence.StandardKey.Print)
        self.act_print.triggered.connect(self.print_file)

        self.act_print_all = QAction(self)
        self.act_print_all.triggered.connect(self.print_all)

        tb.addAction(self.act_open)
        tb.addSeparator()
        tb.addAction(self.act_preview)
        tb.addAction(self.act_print)
        tb.addAction(self.act_print_all)

    def _build_menu(self) -> None:
        self._menu_view = self.menuBar().addMenu("")

        self._menu_lang = self._menu_view.addMenu("")
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        self.act_lang_en = QAction(self, checkable=True)
        self.act_lang_ka = QAction(self, checkable=True)
        for act, code in ((self.act_lang_en, "en"), (self.act_lang_ka, "ka")):
            act.setData(code)
            act.setChecked(self.i18n.lang == code)
            act.triggered.connect(lambda _=False, c=code: self._set_language(c))
            lang_group.addAction(act)
            self._menu_lang.addAction(act)

        self._menu_theme = self._menu_view.addMenu("")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.act_theme_light = QAction(self, checkable=True)
        self.act_theme_dark = QAction(self, checkable=True)
        for act, is_dark in ((self.act_theme_light, False), (self.act_theme_dark, True)):
            act.setChecked(self._dark == is_dark)
            act.triggered.connect(lambda _=False, d=is_dark: self._set_theme(d))
            theme_group.addAction(act)
            self._menu_theme.addAction(act)

    # ------------------------------------------------------ printer capabilities
    def _populate_printers(self) -> None:
        """Fill the printer picker from the installed printers."""
        self.printer_combo.blockSignals(True)
        self.printer_combo.clear()
        names = QPrinterInfo.availablePrinterNames()
        for name in names:
            self.printer_combo.addItem(name, name)
        if not names:
            self.printer_combo.addItem(self.i18n.t("no_printer"), None)
        default = QPrinterInfo.defaultPrinterName()
        idx = self.printer_combo.findData(default) if default else -1
        self.printer_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.printer_combo.blockSignals(False)

    @staticmethod
    def _printer_info(name):
        if not name:
            return None
        for info in QPrinterInfo.availablePrinters():
            if info.printerName() == name:
                return info
        return None

    def _on_printer_changed(self) -> None:
        self._populate_from_printer()

    def _populate_from_printer(self) -> None:
        """Refresh paper size / quality / duplex from the selected driver.

        This is the whole point: the lists reflect what the chosen printer can
        actually do, instead of a hardcoded guess. Falls back to sensible
        defaults when no printer (or a capability) is reported.
        """
        info = self._printer_info(self.printer_combo.currentData())

        sizes = list(info.supportedPageSizes()) if info else []
        if not sizes:
            sizes = [QPageSize(sid) for _, sid in _PAPER_SIZES]
        self._rebuild_paper(sizes)

        res = list(info.supportedResolutions()) if info else []
        if not res:
            res = [300, 600]
        self._rebuild_resolution(sorted(set(res)))

        self._duplex_supported = set(info.supportedDuplexModes()) if info else None
        self._rebuild_duplex()

    def _rebuild_paper(self, sizes) -> None:
        prev = self.papersize_combo.currentData()
        prev_name = prev.name() if isinstance(prev, QPageSize) else None
        self.papersize_combo.blockSignals(True)
        self.papersize_combo.clear()
        for ps in sizes:
            self.papersize_combo.addItem(ps.name(), ps)
        target = prev_name or "A4"
        idx = next(
            (i for i in range(self.papersize_combo.count())
             if self.papersize_combo.itemData(i).name() == target), 0
        )
        self.papersize_combo.setCurrentIndex(idx)
        self.papersize_combo.blockSignals(False)

    def _rebuild_resolution(self, resolutions) -> None:
        prev = self.resolution_combo.currentData()
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()
        for dpi in resolutions:
            self.resolution_combo.addItem(f"{dpi} dpi", dpi)
        idx = self.resolution_combo.findData(prev)
        # Default to the highest available quality.
        self.resolution_combo.setCurrentIndex(
            idx if idx >= 0 else self.resolution_combo.count() - 1
        )
        self.resolution_combo.blockSignals(False)

    def _rebuild_duplex(self) -> None:
        """Rebuild the duplex combo (translated labels, filtered to support)."""
        prev = self.duplex_combo.currentData()
        self.duplex_combo.blockSignals(True)
        self.duplex_combo.clear()
        for key, mode in _DUPLEX_MODES:
            if (self._duplex_supported is None
                    or mode in self._duplex_supported
                    or mode == QPrinter.DuplexMode.DuplexNone):
                self.duplex_combo.addItem(self.i18n.t(key), mode)
        idx = self.duplex_combo.findData(prev)
        self.duplex_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.duplex_combo.blockSignals(False)

    # ---------------------------------------------------------- language/theme
    def _set_language(self, code: str) -> None:
        self.i18n.set_language(code)
        share_language(code)
        self._settings.setValue("lang", code)
        self.retranslate()

    def _set_theme(self, dark: bool) -> None:
        self._dark = dark
        self._settings.setValue("dark", dark)
        apply_theme(QApplication.instance(), dark)

    def retranslate(self) -> None:
        """Apply the current language to every visible string."""
        t = self.i18n.t
        base = f"PrintHub — {t('app_subtitle')}"
        if self.current_source:
            self.setWindowTitle(f"PrintHub — {os.path.basename(self.current_source)}")
        else:
            self.setWindowTitle(base)

        self.act_open.setText(t("open"))
        self.act_preview.setText(t("preview"))
        self.act_print.setText(t("print"))
        self.act_print_all.setText(t("print_all"))
        self.act_print_all.setToolTip(t("tt_print_all"))

        self._menu_view.setTitle(t("menu_view"))
        self._menu_lang.setTitle(t("menu_language"))
        self._menu_theme.setTitle(t("menu_theme"))
        self.act_lang_en.setText(t("lang_en"))
        self.act_lang_ka.setText(t("lang_ka"))
        self.act_theme_light.setText(t("theme_light"))
        self.act_theme_dark.setText(t("theme_dark"))

        self._settings_dock.setWindowTitle(t("settings"))
        self._panel_title.setText("  " + t("settings"))
        for key, lbl in self._form_labels.items():
            lbl.setText(t(key))
        self.collate_check.setText(t("collate"))
        self.collate_check.setToolTip(t("tt_collate"))
        self.pages_edit.setPlaceholderText(t("ph_all"))
        self.pages_edit.setToolTip(t("tt_pages"))
        self.queue_list.setToolTip(t("tt_queue"))

        self.placeholder.setText(f"{t('placeholder')}\n\n{t('formats')}")

        for combo, keys in self._i18n_combos:
            for i, key in enumerate(keys):
                combo.setItemText(i, t(key))
        self._rebuild_duplex()  # duplex labels are translated

        # Refresh the status line for the current state.
        if self.current_source and self.doc.pageCount():
            self.statusBar().showMessage(
                t("loaded", name=os.path.basename(self.current_source), n=self.doc.pageCount())
            )
        else:
            self.statusBar().showMessage(t("ready"))

    def _set_print_enabled(self, on: bool) -> None:
        self.act_preview.setEnabled(on)
        self.act_print.setEnabled(on)
        for w in (
            self.printer_combo, self.pages_edit, self.copies_spin,
            self.collate_check, self.papersize_combo, self.orient_combo,
            self.nup_combo, self.duplex_combo, self.color_combo,
            self.resolution_combo,
        ):
            w.setEnabled(on)
        self.act_print_all.setEnabled(len(self.queue) > 0)

    def _is_image(self, path: str | None) -> bool:
        return bool(path) and os.path.splitext(path)[1].lower() in IMAGE_EXTS

    # -------------------------------------------------------------- loading
    def open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.i18n.t("open").rstrip("… "), "", _OPEN_FILTER
        )
        if paths:
            self.add_files(paths)

    def add_files(self, paths: list[str]) -> None:
        """Append files to the queue; preview the first newly added one."""
        added = []
        for path in paths:
            if path and os.path.exists(path):
                self.queue.append(path)
                self.queue_list.addItem(QListWidgetItem(os.path.basename(path)))
                added.append(path)
        if added:
            self.act_print_all.setEnabled(True)
            # Selecting the row triggers _on_queue_selected -> load().
            first_row = len(self.queue) - len(added)
            self.queue_list.setCurrentRow(first_row)

    def _on_queue_selected(self, row: int) -> None:
        if 0 <= row < len(self.queue):
            self.load(self.queue[row])

    def load(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        t = self.i18n.t
        name = os.path.basename(path)
        self.statusBar().showMessage(t("loading", name=name))
        QApplication.processEvents()

        # Release any previously loaded PDF *before* conversion: converting an
        # image re-writes image_<mode>.pdf, and Windows locks open files.
        self.doc.close()
        try:
            pdf = to_pdf(path, self._tmp.name, self.scale_combo.currentData())
        except Exception as exc:  # conversion/format errors are expected
            QMessageBox.critical(self, t("cannot_open"), str(exc))
            self._reset_empty()
            return

        self.doc.load(pdf)
        if self.doc.pageCount() == 0:
            QMessageBox.critical(self, t("cannot_open"), t("load_failed"))
            self._reset_empty()
            return

        self.current_pdf = pdf
        self.current_source = path
        self.stack.setCurrentIndex(1)
        self._set_print_enabled(True)
        # Scaling only makes sense for images.
        self.scale_combo.setEnabled(self._is_image(path))
        self.setWindowTitle(f"PrintHub — {name}")
        self.statusBar().showMessage(t("loaded", name=name, n=self.doc.pageCount()))

    def _reset_empty(self) -> None:
        self.current_pdf = None
        self.current_source = None
        self.stack.setCurrentIndex(0)
        self._set_print_enabled(False)
        self.scale_combo.setEnabled(False)
        self.setWindowTitle(f"PrintHub — {self.i18n.t('app_subtitle')}")
        self.statusBar().showMessage(self.i18n.t("ready"))

    def _on_scale_changed(self) -> None:
        # Re-lay the current image with the newly chosen scaling mode.
        if self.current_source and self._is_image(self.current_source):
            self.load(self.current_source)

    # ----------------------------------------------------------- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_files(paths)

    # -------------------------------------------------------- queue management
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.queue_list.hasFocus():
            self._remove_selected()
        else:
            super().keyPressEvent(e)

    def _remove_selected(self) -> None:
        row = self.queue_list.currentRow()
        if not (0 <= row < len(self.queue)):
            return
        self.queue.pop(row)
        self.queue_list.takeItem(row)
        if not self.queue:
            self.doc.close()
            self._reset_empty()
        self.act_print_all.setEnabled(len(self.queue) > 0)

    # -------------------------------------------------------------- printing
    @staticmethod
    def _make_printer() -> QPrinter:
        return QPrinter(QPrinter.PrinterMode.HighResolution)

    def _configure_printer(self, printer: QPrinter, with_copies: bool = True) -> None:
        """Apply the settings-panel parameters to a QPrinter before printing.

        These seed the native print dialog too, so the user can still adjust
        them there. `with_copies` is False for preview (one copy shown).
        """
        # Printer name first — it can reset page size / resolution defaults.
        name = self.printer_combo.currentData()
        if name:
            printer.setPrinterName(name)

        ps = self.papersize_combo.currentData()
        if isinstance(ps, QPageSize):
            printer.setPageSize(ps)
        res = self.resolution_combo.currentData()
        if res:
            printer.setResolution(int(res))
        printer.setPageOrientation(self.orient_combo.currentData())
        printer.setColorMode(self.color_combo.currentData())
        printer.setDuplex(self.duplex_combo.currentData())
        if with_copies:
            printer.setCopyCount(self.copies_spin.value())
            printer.setCollateCopies(self.collate_check.isChecked())

    def _resolve_pages(self) -> list[int] | None:
        """Parse the page-range field; warn and return None if it's invalid."""
        t = self.i18n.t
        try:
            pages = parse_page_range(self.pages_edit.text(), self.doc.pageCount())
        except ValueError:
            QMessageBox.warning(self, t("bad_range_title"), t("bad_range_msg"))
            return None
        if not pages:
            QMessageBox.warning(
                self, t("no_pages_title"), t("no_pages_msg", n=self.doc.pageCount())
            )
            return None
        return pages

    def print_file(self) -> None:
        if not self.current_pdf:
            return
        pages = self._resolve_pages()
        if pages is None:
            return

        nup = self.nup_combo.currentData()
        printer = self._make_printer()
        self._configure_printer(printer)

        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(self.i18n.t("print").rstrip("… "))
        # The app owns page selection, so hide the dialog's own range control.
        dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, False)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            self.copies_spin.setValue(printer.copyCount())  # reflect dialog change
            ok = render_pdf_to_printer(self.doc, printer, pages, nup)
            n = printer.copyCount()
            cw = self.i18n.t("copy_word" if n == 1 else "copies_word")
            self.statusBar().showMessage(
                self.i18n.t("sent", p=len(pages), nup=nup, c=n, cw=cw)
                if ok else self.i18n.t("print_failed")
            )

    def print_preview(self) -> None:
        if not self.current_pdf:
            return
        pages = self._resolve_pages()
        if pages is None:
            return
        nup = self.nup_combo.currentData()
        printer = self._make_printer()  # preview shows one copy of the selected pages
        self._configure_printer(printer, with_copies=False)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.paintRequested.connect(
            lambda p: render_pdf_to_printer(self.doc, p, pages, nup)
        )
        dlg.exec()

    def _build_batch_leaves(self):
        """Convert every queued file and build the (docs, leaves) for one job.

        `docs` must be kept alive (and closed by the caller) while the leaves
        are painted. `leaves` is a flat [(doc, page_index), ...] in queue order,
        honoring the page-range field per file and the image scaling mode.
        """
        mode = self.scale_combo.currentData()
        page_text = self.pages_edit.text()
        docs: list[QPdfDocument] = []
        leaves: list[tuple[QPdfDocument, int]] = []
        for i, path in enumerate(self.queue):
            sub = os.path.join(self._tmp.name, f"batch_{i}")
            os.makedirs(sub, exist_ok=True)
            pdf = to_pdf(path, sub, mode)
            d = QPdfDocument(self)
            d.load(pdf)
            if d.pageCount() == 0:
                d.close()
                continue
            docs.append(d)
            for p in parse_page_range(page_text, d.pageCount()):
                leaves.append((d, p))
        return docs, leaves

    def print_all(self) -> None:
        """Print every queued file as a single job, in queue order."""
        if not self.queue:
            return
        t = self.i18n.t
        nup = self.nup_combo.currentData()
        try:
            docs, leaves = self._build_batch_leaves()
        except Exception as exc:  # a bad file shouldn't lose the whole batch silently
            QMessageBox.critical(self, t("batch_error"), str(exc))
            return

        if not leaves:
            QMessageBox.warning(self, t("nothing_title"), t("nothing_msg"))
            for d in docs:
                d.close()
            return

        printer = self._make_printer()
        self._configure_printer(printer)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(t("print_all"))
        dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, False)
        try:
            if dlg.exec() == QPrintDialog.DialogCode.Accepted:
                ok = render_leaves_to_printer(leaves, printer, nup)
                self.statusBar().showMessage(
                    t("sent_batch", f=len(docs), p=len(leaves))
                    if ok else t("print_failed")
                )
        finally:
            for d in docs:
                d.close()

    # ---------------------------------------------------------------- teardown
    def closeEvent(self, e):
        # Free the PDF handle before the temp dir is removed.
        self.doc.close()
        self._tmp.cleanup()
        super().closeEvent(e)
