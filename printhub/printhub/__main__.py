"""Entry point:  python -m printhub [file]"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PrintHub")
    app.setApplicationVersion(__import__("printhub").__version__)

    win = MainWindow()
    win.show()

    # Optional: queue any files passed on the command line.
    if len(sys.argv) > 1:
        win.add_files(sys.argv[1:])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
