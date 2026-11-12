"""Reusable UI building blocks."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import Mode
from . import style

if TYPE_CHECKING:
    from .context import AppContext


def button(text: str, *, primary: bool = False, flat: bool = False, danger: bool = False,
           tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        b.setProperty("primary", True)
    if flat:
        b.setProperty("flat", True)
    if danger:
        b.setProperty("danger", True)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def label(text: str = "", kind: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if kind:
        lbl.setObjectName(kind)
    lbl.setWordWrap(wrap)
    return lbl


def separator() -> QFrame:
    f = QFrame()
    f.setObjectName("separator")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def rounded(pix: QPixmap, size: QSize, radius: float = 10.0) -> QPixmap:
    """Scale-to-cover and clip to a rounded rectangle."""
    dpr = 2.0
    out = QPixmap(int(size.width() * dpr), int(size.height() * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    scaled = pix.scaled(size * dpr, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(dpr)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    p.setClipPath(path)
    x = (size.width() - scaled.width() / dpr) / 2
    y = (size.height() - scaled.height() / dpr) / 2
    p.drawPixmap(int(x), int(y), scaled)
    p.end()
    return out


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 20)
        self.body.setSpacing(12)
        if title:
            self.body.addWidget(label(title, "h2"))
        if subtitle:
            self.body.addWidget(label(subtitle, "muted", wrap=True))


class Page(QScrollArea):
    """Scrollable page with a title and a vertical content layout."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(32, 28, 32, 32)
        self.content.setSpacing(16)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label(title, "h1"))
        if subtitle:
            head.addWidget(label(subtitle, "muted", wrap=True))
        self.content.addLayout(head)


class ThumbLabel(QLabel):
    """Shows a wallpaper thumbnail, updating when the thumbnail cache finishes."""

    def __init__(self, ctx: AppContext, size: QSize, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._size = size
        self._path = ""
        self.setObjectName("thumb")
        self.setFixedSize(size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctx.thumbs.ready.connect(self._on_ready)
        self.set_path("")

    def set_path(self, path: str) -> None:
        self._path = path
        self._render()

    def _on_ready(self, path: str) -> None:
        if path == self._path:
            self._render()

    def _render(self) -> None:
        if not self._path:
            self.setPixmap(QPixmap())
            self.setText("No wallpaper")
            return
        if not os.path.exists(self._path):
            self.setPixmap(QPixmap())
            self.setText("File missing")
            return
        pix = self._ctx.thumbs.get(self._path)
        if pix is None:
            self.setPixmap(QPixmap())
            self.setText("Loading…")
            return
        self.setText("")
        self.setPixmap(rounded(pix, self._size))


class WallpaperSlot(QFrame):
    """Thumbnail + Choose/Clear buttons for picking a single wallpaper."""

    changed = Signal(str)

    def __init__(self, ctx: AppContext, title: str, thumb: QSize | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        thumb = thumb or QSize(240, 135)
        self._ctx = ctx
        self._path = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._title = label(title, "h2")
        lay.addWidget(self._title)
        self._thumb = ThumbLabel(ctx, thumb)
        lay.addWidget(self._thumb)
        self._name = label("", "small")
        self._name.setMaximumWidth(thumb.width())
        lay.addWidget(self._name)
        row = QHBoxLayout()
        row.setSpacing(6)
        choose = button("Choose…")
        choose.clicked.connect(self._choose)
        self._clear = button("Clear", flat=True)
        self._clear.clicked.connect(lambda: self._set("", emit=True))
        row.addWidget(choose)
        row.addWidget(self._clear)
        row.addStretch(1)
        lay.addLayout(row)
        self._set("", emit=False)

    @property
    def path(self) -> str:
        return self._path

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_path(self, path: str) -> None:
        self._set(path, emit=False)

    def _set(self, path: str, emit: bool) -> None:
        self._path = path
        self._thumb.set_path(path)
        name = os.path.basename(path) if path else "Nothing selected"
        self._name.setText(self._name.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle,
                                                               self._name.maximumWidth()))
        self._name.setToolTip(path)
        self._clear.setVisible(bool(path))
        if emit:
            self.changed.emit(path)

    def _choose(self) -> None:
        from .picker import pick_wallpaper

        path = pick_wallpaper(self._ctx, self, current=self._path)
        if path:
            self._set(path, emit=True)


class ModeBanner(QFrame):
    """Tells the user whether this page's mode is active and offers to activate it."""

    def __init__(self, ctx: AppContext, mode: Mode, inactive_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self._ctx = ctx
        self._mode = mode
        self._inactive_text = inactive_text
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 12, 12)
        self._text = label("", wrap=True)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._text, 1)
        self._btn = button("Turn on", primary=True)
        self._btn.clicked.connect(lambda: ctx.controller.set_mode(mode))
        lay.addWidget(self._btn)
        ctx.store.changed.connect(lambda _s: self.update_state())
        self.update_state()

    def update_state(self) -> None:
        active = self._ctx.store.config.mode is self._mode
        self.setProperty("active", active)
        style.repolish(self)
        self._btn.setVisible(not active)
        self._text.setText("✓  This mode is active." if active else self._inactive_text)
