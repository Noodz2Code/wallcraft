"""Light/dark styling: Fusion palette plus a token-based stylesheet."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from ..paths import cache_dir

LIGHT = {
    "bg": "#F4F5F7",
    "sidebar": "#ECEEF1",
    "surface": "#FFFFFF",
    "surface_alt": "#F0F1F4",
    "hover": "#E4E6EA",
    "border": "#DCDFE4",
    "text": "#17191C",
    "muted": "#636A75",
    "accent": "#4F5BD5",
    "accent_hover": "#4350C8",
    "accent_soft": "#E5E7FB",
    "on_accent": "#FFFFFF",
    "success": "#1E8E4E",
    "success_soft": "#E2F4E9",
    "warning": "#B86E00",
    "danger": "#C93C3C",
    "thumb_bg": "#E3E5EA",
}

DARK = {
    "bg": "#141518",
    "sidebar": "#101114",
    "surface": "#1C1D21",
    "surface_alt": "#23252A",
    "hover": "#2A2C32",
    "border": "#2F3138",
    "text": "#E9EAEC",
    "muted": "#9599A2",
    "accent": "#7C86F0",
    "accent_hover": "#8D96F4",
    "accent_soft": "#262A49",
    "on_accent": "#FFFFFF",
    "success": "#4CC17E",
    "success_soft": "#1A2E23",
    "warning": "#E0A030",
    "danger": "#EF6B6B",
    "thumb_bg": "#26282E",
}

_current: dict[str, str] = LIGHT


def tokens() -> dict[str, str]:
    return _current


def color(name: str) -> QColor:
    return QColor(_current[name])


def _arrow(path: Path, hex_color: str, up: bool) -> str:
    """Draw a small chevron PNG for combo/spin boxes (avoids bundling image files)."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(hex_color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    path_ = QPainterPath()
    if up:
        points = (QPointF(6, 12), QPointF(10, 8), QPointF(14, 12))
    else:
        points = (QPointF(6, 8), QPointF(10, 12), QPointF(14, 8))
    path_.moveTo(points[0])
    for pt in points[1:]:
        path_.lineTo(pt)
    p.drawPath(path_)
    p.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(path), "PNG")
    return path.as_posix()


def _stylesheet(t: dict[str, str], down: str, up: str) -> str:
    return f"""
QWidget {{ color: {t['text']}; }}
QMainWindow, QDialog, #page {{ background: {t['bg']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

#sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
#appTitle {{ font-size: 15pt; font-weight: 600; }}
#nav {{ background: transparent; border: none; outline: 0; }}
#nav::item {{ padding: 0 12px; border-radius: 8px; color: {t['muted']}; }}
#nav::item:hover {{ background: {t['hover']}; color: {t['text']}; }}
#nav::item:selected {{ background: {t['accent_soft']}; color: {t['accent']}; }}

QLabel#h1 {{ font-size: 19pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 11pt; font-weight: 600; }}
QLabel#muted {{ color: {t['muted']}; }}
QLabel#small {{ color: {t['muted']}; font-size: 8.5pt; }}
QLabel#pill {{ background: {t['accent_soft']}; color: {t['accent']}; border-radius: 9px;
               padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }}
QLabel#thumb {{ background: {t['thumb_bg']}; border-radius: 10px; color: {t['muted']}; }}

QFrame#card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QFrame#banner {{ background: {t['accent_soft']}; border-radius: 10px; }}
QFrame#banner[active="true"] {{ background: {t['success_soft']}; }}
QFrame#banner QLabel {{ background: transparent; }}
QFrame#separator {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
               padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['surface_alt']}; }}
QPushButton:disabled {{ color: {t['muted']}; background: {t['surface_alt']}; }}
QPushButton:checked {{ background: {t['accent_soft']}; color: {t['accent']}; border-color: {t['accent']}; }}
QPushButton[primary="true"] {{ background: {t['accent']}; color: {t['on_accent']}; border-color: {t['accent']};
                               font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t['accent_hover']}; }}
QPushButton[primary="true"]:disabled {{ background: {t['hover']}; color: {t['muted']}; border-color: {t['border']}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; color: {t['accent']}; padding: 4px 6px; }}
QPushButton[flat="true"]:hover {{ background: {t['hover']}; }}
QPushButton[danger="true"] {{ color: {t['danger']}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 7px;
    padding: 5px 8px; min-height: 20px; selection-background-color: {t['accent']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTimeEdit:focus {{
    border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; outline: 0; padding: 4px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; border: none; width: 20px; height: 15px;
    background: transparent; margin-top: 1px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; border: none; width: 20px; height: 15px;
    background: transparent; margin-bottom: 1px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QTimeEdit::down-button:hover {{
    background: {t['hover']}; border-radius: 4px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QTimeEdit::up-arrow {{ image: url({up}); width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QTimeEdit::down-arrow {{
    image: url({down}); width: 12px; height: 12px; }}

QListView#grid {{ background: transparent; border: none; outline: 0; }}
QListWidget#list {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px;
                    outline: 0; padding: 4px; }}
QListWidget#list::item {{ border-radius: 6px; padding: 4px; }}
QListWidget#list::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}

QTableWidget {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px;
                gridline-color: transparent; outline: 0; }}
QTableWidget::item {{ border-bottom: 1px solid {t['border']}; }}
QTableWidget::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QHeaderView::section {{ background: transparent; border: none; border-bottom: 1px solid {t['border']};
                        padding: 8px 6px; color: {t['muted']}; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
QMenu::item:disabled {{ color: {t['muted']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px 8px; }}
QStatusBar {{ background: {t['bg']}; color: {t['muted']}; }}
QStatusBar::item {{ border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['accent']}; width: 14px; height: 14px; margin: -5px 0;
                              border-radius: 7px; }}
"""


def apply_theme(app: QApplication, dark: bool) -> None:
    global _current
    _current = DARK if dark else LIGHT
    t = _current
    app.setStyle("Fusion")
    if sys.platform == "win32":
        font = QFont("Segoe UI", 10)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)

    pal = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        pal.setColor(group, QPalette.ColorRole.Window, QColor(t["bg"]))
        pal.setColor(group, QPalette.ColorRole.WindowText, QColor(t["text"]))
        pal.setColor(group, QPalette.ColorRole.Base, QColor(t["surface"]))
        pal.setColor(group, QPalette.ColorRole.AlternateBase, QColor(t["surface_alt"]))
        pal.setColor(group, QPalette.ColorRole.Text, QColor(t["text"]))
        pal.setColor(group, QPalette.ColorRole.Button, QColor(t["surface"]))
        pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(t["text"]))
        pal.setColor(group, QPalette.ColorRole.Highlight, QColor(t["accent"]))
        pal.setColor(group, QPalette.ColorRole.HighlightedText, QColor(t["on_accent"]))
        pal.setColor(group, QPalette.ColorRole.ToolTipBase, QColor(t["surface"]))
        pal.setColor(group, QPalette.ColorRole.ToolTipText, QColor(t["text"]))
        pal.setColor(group, QPalette.ColorRole.PlaceholderText, QColor(t["muted"]))
        pal.setColor(group, QPalette.ColorRole.Link, QColor(t["accent"]))
        pal.setColor(group, QPalette.ColorRole.Mid, QColor(t["border"]))
        pal.setColor(group, QPalette.ColorRole.Light, QColor(t["surface"]))
        pal.setColor(group, QPalette.ColorRole.Dark, QColor(t["border"]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["muted"]))
    app.setPalette(pal)

    ui_dir = cache_dir() / "ui"
    variant = "dark" if dark else "light"
    down = _arrow(ui_dir / f"chevron-down-{variant}.png", t["muted"], up=False)
    up = _arrow(ui_dir / f"chevron-up-{variant}.png", t["muted"], up=True)
    app.setStyleSheet(_stylesheet(t, down, up))


def repolish(widget) -> None:
    """Re-evaluate the stylesheet after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
