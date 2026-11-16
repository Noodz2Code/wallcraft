"""Light/dark styling: Fusion palette plus a token-based stylesheet."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QIconEngine, QPainter, QPainterPath, QPalette, QPen, QPixmap
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
    "animated_tag": "#E67C3AED",  # Qt order: #AARRGGBB
    "animated": "#7C3AED",
    "star": "#B87900",
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
    "accent_soft": "#21253F",
    "on_accent": "#0E1033",  # dark ink on the light accent: 5.7:1, white would be 3.2:1
    "success": "#4CC17E",
    "success_soft": "#1A2E23",
    "warning": "#E0A030",
    "danger": "#EF6B6B",
    "thumb_bg": "#26282E",
    "animated_tag": "#E67C3AED",  # Qt order: #AARRGGBB
    "animated": "#7C3AED",  # white tag text needs the deeper violet in dark mode too
    "star": "#F5B83D",
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
QFrame#segmented {{ background: {t['surface_alt']}; border: 1px solid {t['border']}; border-radius: 9px; }}
QFrame#segmented QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px;
                                padding: 5px 16px; color: {t['muted']}; font-weight: 600; }}
QFrame#segmented QPushButton:hover {{ color: {t['text']}; }}
QFrame#segmented QPushButton:checked {{ background: {t['surface']}; color: {t['text']}; border-color: {t['border']}; }}
QLabel#tag {{ background: {t['surface_alt']}; border: 1px solid {t['border']}; color: {t['text']};
              border-radius: 6px; padding: 1px 7px; font-size: 8pt; font-weight: 700; }}
QLabel#tagAnimated {{ background: {t['animated']}; color: #FFFFFF; border-radius: 6px;
                      padding: 1px 7px; font-size: 8pt; font-weight: 700; }}
QLabel#tagInUse {{ background: {t['accent']}; color: {t['on_accent']}; border-radius: 6px;
                   padding: 1px 7px; font-size: 8pt; font-weight: 700; }}
QLabel#layerName {{ font-weight: 600; }}
QLabel#emptyTitle {{ font-size: 11pt; font-weight: 600; }}
QWidget#detailsContent {{ background: transparent; }}
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
QPushButton[flat="true"]:disabled {{ background: transparent; color: {t['muted']}; }}
QPushButton[danger="true"] {{ color: {t['danger']}; }}
QPushButton[danger="true"]:disabled {{ color: {t['muted']}; }}
QPushButton[link="true"] {{ text-align: left; }}
QPushButton#iconButton {{ background: transparent; border: none; border-radius: 6px; padding: 0;
                          min-height: 0; }}
QPushButton#iconButton:hover {{ background: {t['hover']}; }}
QPushButton#iconButton:pressed {{ background: {t['border']}; }}
/* Buttons take focus from the keyboard only (see widgets.button), so this ring never lingers after a click. */
QPushButton:focus {{ border-color: {t['accent']}; }}
QPushButton[primary="true"]:focus {{ border-color: {t['text']}; }}
QPushButton[flat="true"]:focus, QPushButton#iconButton:focus {{ background: {t['hover']}; }}
QFrame#segmented QPushButton:focus {{ border-color: {t['accent']}; }}

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
QScrollBar[idle="true"]::handle:vertical {{ background: transparent; }}
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


# Icons -------------------------------------------------------------------------- #
# A small drawn icon set (one stroke weight, 20×20 grid) instead of font glyphs, which
# render in whatever symbol font each system happens to have. Colours are read from the
# current tokens at paint time, so icons follow light/dark switches without rebuilding.

def _star_path(cx: float, cy: float, outer: float, inner: float) -> QPainterPath:
    path = QPainterPath()
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        a = math.radians(-90 + i * 36)
        pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    return path


def paint_icon(p: QPainter, rect: QRectF, name: str, color: QColor, fill: QColor | None = None) -> None:
    """Draw icon ``name`` into ``rect`` (any size; geometry is defined on a 20×20 grid)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / 20, rect.height() / 20)
    pen = QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    lines = {
        "close": ((6, 6, 14, 14), (14, 6, 6, 14)),
        "plus": ((10, 5, 10, 15), (5, 10, 15, 10)),
    }
    polylines = {
        "chevron-left": ((12, 5), (7, 10), (12, 15)),
        "chevron-right": ((8, 5), (13, 10), (8, 15)),
    }
    if name in lines:
        for x1, y1, x2, y2 in lines[name]:
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name in polylines:
        path = QPainterPath()
        pts = polylines[name]
        path.moveTo(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        p.drawPath(path)
    elif name == "refresh":
        # Open circle (gap at the upper right) with an arrowhead on its leading end.
        ring = QRectF(4.5, 4.5, 11, 11)
        arc = QPainterPath()
        arc.arcMoveTo(ring, 40)
        arc.arcTo(ring, 40, 290)
        p.drawPath(arc)
        head = QPainterPath()
        head.moveTo(QPointF(15.6, 3.6))
        head.lineTo(QPointF(14.4, 7.3))
        head.lineTo(QPointF(10.7, 6.2))
        p.drawPath(head)
    elif name == "star":
        if fill is not None:
            p.setPen(QPen(fill, 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(fill)
        p.drawPath(_star_path(10, 10.6, 7.2, 3.1))
    p.restore()


class _IconEngine(QIconEngine):
    def __init__(self, name: str, role: str, on_fill: str | None) -> None:
        super().__init__()
        self._name = name
        self._role = role
        self._on_fill = on_fill

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        if mode == QIcon.Mode.Disabled:
            c = color("muted")
            c.setAlphaF(0.6)
        else:
            c = color(self._role)
        fill = None
        if self._on_fill and state == QIcon.State.On and mode != QIcon.Mode.Disabled:
            c = fill = color(self._on_fill)
        paint_icon(painter, QRectF(rect), self._name, c, fill)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pix = QPixmap(size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pix

    def clone(self) -> QIconEngine:
        return _IconEngine(self._name, self._role, self._on_fill)


def icon(name: str, role: str = "text", on_fill: str | None = None) -> QIcon:
    """Themed icon: ``close``, ``plus``, ``chevron-left``, ``chevron-right``, ``refresh`` or ``star``.

    ``role`` is the colour token for the stroke; ``on_fill`` fills the shape in that token
    when a checkable button is checked (e.g. a filled star for favourites).
    """
    return QIcon(_IconEngine(name, role, on_fill))


def draw_badge(painter: QPainter, x: float, y: float, text: str, bg: QColor, fg: QColor) -> float:
    """Pill-shaped label (file type, IN USE) painted over a thumbnail. Returns the x after it."""
    fm = painter.fontMetrics()
    w = fm.horizontalAdvance(text) + 12
    h = fm.height() + 4
    rect = QRectF(x, y, w, h)
    path = QPainterPath()
    path.addRoundedRect(rect, h / 2, h / 2)
    painter.fillPath(path, bg)
    painter.setPen(fg)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    return x + w + 6
