"""Light / dark theming via a Qt Fusion palette. Light is the default."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

_R = QPalette.ColorRole
_G = QPalette.ColorGroup


def _dark_palette() -> QPalette:
    p = QPalette()
    window = QColor(45, 45, 48)
    base = QColor(30, 30, 32)
    text = QColor(230, 230, 230)
    button = QColor(60, 60, 64)
    disabled = QColor(120, 120, 120)

    p.setColor(_R.Window, window)
    p.setColor(_R.WindowText, text)
    p.setColor(_R.Base, base)
    p.setColor(_R.AlternateBase, window)
    p.setColor(_R.Text, text)
    p.setColor(_R.Button, button)
    p.setColor(_R.ButtonText, text)
    p.setColor(_R.ToolTipBase, window)
    p.setColor(_R.ToolTipText, text)
    p.setColor(_R.PlaceholderText, QColor(140, 140, 140))
    p.setColor(_R.Highlight, QColor(38, 120, 220))
    p.setColor(_R.HighlightedText, QColor(255, 255, 255))
    p.setColor(_R.Link, QColor(90, 160, 255))

    for role in (_R.Text, _R.ButtonText, _R.WindowText):
        p.setColor(_G.Disabled, role, disabled)
    return p


def apply_theme(app, dark: bool) -> None:
    """Apply the light or dark theme to the whole application."""
    app.setStyle("Fusion")
    if dark:
        app.setPalette(_dark_palette())
    else:
        # Fusion's own light palette: clean white bases.
        app.setPalette(app.style().standardPalette())
