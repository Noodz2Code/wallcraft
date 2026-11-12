"""Dialog for choosing a wallpaper from the library (or from disk)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..library import ALL_EXTS
from .library_model import GridView, ItemRole, LibraryFilter, LibraryModel, ThumbDelegate
from .widgets import button, label

if TYPE_CHECKING:
    from .context import AppContext


def media_file_filter() -> str:
    exts = " ".join(f"*{e}" for e in sorted(ALL_EXTS))
    return f"Wallpapers ({exts});;All files (*)"


class WallpaperPicker(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None, current: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose a wallpaper")
        self.resize(900, 620)
        self.selected = ""
        self._ctx = ctx

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(label("Choose a wallpaper", "h2"))
        top.addStretch(1)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search library")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(220)
        top.addWidget(self._search)
        self._kind = QComboBox()
        for key, text in LibraryFilter.FILTERS:
            self._kind.addItem(text, key)
        top.addWidget(self._kind)
        lay.addLayout(top)

        self._model = LibraryModel(ctx, self)
        self._proxy = LibraryFilter(ctx, self)
        self._proxy.setSourceModel(self._model)
        self._view = GridView(ThumbDelegate(ctx, self))
        self._view.setModel(self._proxy)
        lay.addWidget(self._view, 1)
        if not ctx.library.items:
            lay.addWidget(label("Your library is empty. Use “Browse files…” or add a folder in the Library.",
                                "muted"))

        self._search.textChanged.connect(self._proxy.set_text)
        self._kind.currentIndexChanged.connect(lambda _i: self._proxy.set_kind(self._kind.currentData()))
        self._view.doubleClicked.connect(lambda _i: self._accept_selection())
        self._view.selectionModel().selectionChanged.connect(lambda *_: self._update_ok())

        bottom = QHBoxLayout()
        browse = button("Browse files…")
        browse.clicked.connect(self._browse)
        bottom.addWidget(browse)
        bottom.addStretch(1)
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self._ok = button("Choose", primary=True)
        self._ok.clicked.connect(self._accept_selection)
        bottom.addWidget(cancel)
        bottom.addWidget(self._ok)
        lay.addLayout(bottom)
        self._select(current)
        self._update_ok()

    def _select(self, path: str) -> None:
        if not path:
            return
        for row in range(self._proxy.rowCount()):
            idx = self._proxy.index(row, 0)
            item = idx.data(ItemRole)
            if item and item.path == path:
                self._view.setCurrentIndex(idx)
                self._view.scrollTo(idx)
                return

    def _update_ok(self) -> None:
        self._ok.setEnabled(self._view.currentIndex().isValid())

    def _accept_selection(self) -> None:
        item = self._view.currentIndex().data(ItemRole)
        if item is not None:
            self.selected = item.path
            self.accept()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a wallpaper", "", media_file_filter())
        if path:
            self.selected = path
            self.accept()


def pick_wallpaper(ctx: AppContext, parent: QWidget | None = None, current: str = "") -> str:
    dlg = WallpaperPicker(ctx, parent, current)
    return dlg.selected if dlg.exec() == QDialog.DialogCode.Accepted else ""
