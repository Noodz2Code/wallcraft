"""Model, filter and delegate for the wallpaper grid."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from ..library import Kind, MediaItem, norm
from . import style

if TYPE_CHECKING:
    from .context import AppContext

ItemRole = Qt.ItemDataRole.UserRole + 1
MIN_CARD_WIDTH = 190
TEXT_HEIGHT = 26
PAD = 6


class LibraryModel(QAbstractListModel):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._items: list[MediaItem] = []
        self._rows: dict[str, int] = {}
        ctx.library.changed.connect(self.reload)
        ctx.thumbs.ready.connect(self._thumb_ready)
        ctx.controller.wallpaperChanged.connect(self._touch_all)
        self.reload()

    def reload(self) -> None:
        self.beginResetModel()
        self._items = list(self._ctx.library.items)
        self._rows = {item.path: i for i, item in enumerate(self._items)}
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.path
        if role == ItemRole:
            return item
        return None

    def item_at(self, row: int) -> MediaItem | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def _thumb_ready(self, path: str) -> None:
        row = self._rows.get(path)
        if row is not None:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    def _touch_all(self) -> None:
        if self._items:
            self.dataChanged.emit(self.index(0), self.index(len(self._items) - 1))


class LibraryFilter(QSortFilterProxyModel):
    FILTERS = (("all", "All"), ("images", "Images"), ("live", "Live"), ("favorites", "Favorites"))

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._text = ""
        self._kind = "all"
        ctx.store.changed.connect(lambda s: self.invalidateFilter() if s == "favorites" else None)

    def set_text(self, text: str) -> None:
        self._text = text.strip().lower()
        self.invalidateFilter()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        item: MediaItem | None = self.sourceModel().item_at(row)
        if item is None:
            return False
        if self._text and self._text not in item.path.lower():
            return False
        if self._kind == "images":
            return item.kind is Kind.IMAGE
        if self._kind == "live":
            return item.is_live
        if self._kind == "favorites":
            return self._ctx.library.is_favorite(item.path)
        return True


class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.card = QSize(MIN_CARD_WIDTH, 150)

    def set_card_width(self, width: int) -> None:
        thumb_h = int((width - 2 * PAD) * 10 / 16)
        self.card = QSize(width, thumb_h + TEXT_HEIGHT + 2 * PAD)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return self.card

    def _in_use(self, path: str) -> bool:
        key = norm(path)
        return any(p and norm(p) == key for p in self._ctx.controller.current.values())

    def paint(self, painter: QPainter, option, index) -> None:
        item: MediaItem | None = index.data(ItemRole)
        if item is None:
            return
        t = style.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        r = option.rect.adjusted(PAD, PAD, -PAD, -PAD)
        thumb = QRect(r.x(), r.y(), r.width(), r.height() - TEXT_HEIGHT)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(thumb), 10, 10)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.fillPath(clip, QColor(t["thumb_bg"]))
        pix = self._ctx.thumbs.get(item.path)
        if pix is not None and not pix.isNull():
            # Draw the source region that covers the target (centre crop).
            src_ratio = pix.width() / max(1, pix.height())
            dst_ratio = thumb.width() / max(1, thumb.height())
            if src_ratio > dst_ratio:
                w = int(pix.height() * dst_ratio)
                src = QRect((pix.width() - w) // 2, 0, w, pix.height())
            else:
                h = int(pix.width() / dst_ratio)
                src = QRect(0, (pix.height() - h) // 2, pix.width(), h)
            painter.setClipPath(clip)
            painter.drawPixmap(thumb, pix, src)
            painter.setClipping(False)
        else:
            painter.setPen(QColor(t["muted"]))
            painter.drawText(thumb, Qt.AlignmentFlag.AlignCenter, item.kind.label)

        if hovered and not selected:
            painter.fillPath(clip, QColor(255, 255, 255, 22))
        if selected:
            painter.setPen(QPen(QColor(t["accent"]), 3))
            painter.drawPath(clip)

        badge_font = QFont(option.font)
        badge_font.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.78))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        x = thumb.x() + 8
        if item.is_live:
            tag = "LIVE" if item.kind is Kind.VIDEO else os.path.splitext(item.path)[1].lstrip(".").upper()
            x = self._badge(painter, x, thumb.y() + 8, tag,
                            QColor(0, 0, 0, 165), QColor("#FFFFFF"))
        if self._in_use(item.path):
            self._badge(painter, x, thumb.y() + 8, "IN USE", QColor(t["accent"]), QColor(t["on_accent"]))
        if self._ctx.library.is_favorite(item.path):
            star = QRect(thumb.right() - 30, thumb.y() + 6, 24, 24)
            painter.setPen(QColor("#FFC93C"))
            f = QFont(option.font)
            f.setPointSizeF(option.font.pointSizeF() * 1.3)
            painter.setFont(f)
            painter.drawText(star, Qt.AlignmentFlag.AlignCenter, "★")

        painter.setFont(option.font)
        painter.setPen(QColor(t["text"] if selected else t["muted"]))
        text_rect = QRect(r.x() + 2, thumb.bottom() + 4, r.width() - 4, TEXT_HEIGHT - 4)
        name = painter.fontMetrics().elidedText(item.name, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        painter.restore()

    @staticmethod
    def _badge(painter: QPainter, x: int, y: int, text: str, bg: QColor, fg: QColor) -> int:
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


class GridView(QListView):
    """Icon grid whose cards stretch to fill the available width."""

    def __init__(self, delegate: ThumbDelegate, parent=None) -> None:
        super().__init__(parent)
        self._delegate = delegate
        self.setObjectName("grid")
        self.setItemDelegate(delegate)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        # A permanent scrollbar keeps the viewport width stable, so the column count
        # computed in resizeEvent stays valid when the list grows past one screen.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.verticalScrollBar().setSingleStep(24)

    def resizeEvent(self, event) -> None:  # noqa: N802
        width = self.width() - self.verticalScrollBar().sizeHint().width() - 2 * self.frameWidth() - 4
        columns = max(1, width // MIN_CARD_WIDTH)
        card_w = max(MIN_CARD_WIDTH, width // columns)
        self._delegate.set_card_width(card_w)
        self.setGridSize(self._delegate.card)
        super().resizeEvent(event)
