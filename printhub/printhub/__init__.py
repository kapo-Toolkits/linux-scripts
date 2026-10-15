"""PrintHub — a universal, cross-platform print front-end.

Backend: Qt (QtPrintSupport) — one code path on Windows, macOS and Linux.
Everything is normalized to PDF, previewed with QtPdf, and sent to the
native print dialog of the host OS.
"""

__version__ = "0.2.1"
