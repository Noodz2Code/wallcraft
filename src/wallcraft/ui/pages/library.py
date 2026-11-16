"""Library page: browse, search, preview and apply wallpapers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QImageReader
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...config import FitMode
from ...library import Kind, MediaItem, norm
from .. import style
from ..library_model import GridView, ItemRole, LibraryFilter, LibraryModel, ThumbDelegate
from ..picker import media_file_filter
from ..widgets import ElidedLabel, ThumbLabel, button, label, separator

if TYPE_CHECKING:
    from ..context import AppContext


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


class FoldersDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setWindowTitle("Library folders")
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Library folders", "h2"))
        lay.addWidget(label("Wallcraft scans these folders (including subfolders) and picks up new files "
                            "automatically.", "muted", wrap=True))
        self._list = QListWidget()
        self._list.setObjectName("list")
        lay.addWidget(self._list, 1)
        row = QHBoxLayout()
        add = button("Add folder…")
        add.clicked.connect(self._add)
        self._remove = button("Remove", danger=True)
        self._remove.clicked.connect(self._remove_selected)
        close = button("Done", primary=True)
        close.clicked.connect(self.accept)
        row.addWidget(add)
        row.addWidget(self._remove)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._list.currentRowChanged.connect(lambda r: self._remove.setEnabled(r >= 0))
        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        self._list.addItems(self._ctx.store.config.library_folders)
        self._remove.setEnabled(False)

    def _add(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a folder to your library")
        if folder:
            self._ctx.library.add_paths([folder])
            self._reload()

    def _remove_selected(self) -> None:
        item = self._list.currentItem()
        if item:
            self._ctx.library.remove_folder(item.text())
            self._reload()


class DetailsPanel(QFrame):
    def __init__(self, ctx: AppContext, page: LibraryPage) -> None:
        super().__init__()
        self._ctx = ctx
        self._page = page
        self._item: MediaItem | None = None
        self.setObjectName("card")
        self.setFixedWidth(320)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)

        # Nothing selected: a quiet prompt instead of a column of disabled controls.
        self._empty = QWidget()
        self._empty.setObjectName("detailsContent")
        empty = QVBoxLayout(self._empty)
        empty.setContentsMargins(24, 24, 24, 24)
        empty.setSpacing(6)
        empty.addStretch(1)
        for text, kind in (("No wallpaper selected", "emptyTitle"),
                           ("Select a wallpaper to preview it. Double-click one to apply it right away.", "muted")):
            lbl = label(text, kind, wrap=True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.addWidget(lbl)
        empty.addStretch(1)
        outer.addWidget(self._empty)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)
        content = QWidget()
        content.setObjectName("detailsContent")
        self._scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(10)

        self._preview = ThumbLabel(ctx, QSize(280, 158))
        lay.addWidget(self._preview)
        self._name = ElidedLabel("", "h2")
        lay.addWidget(self._name)
        tags = QHBoxLayout()
        tags.setSpacing(6)
        self._type_tag = label("", "tag")
        self._layer_tag = label("", "tag")
        self._in_use_tag = label("In use", "tagInUse")
        tags.addWidget(self._type_tag)
        tags.addWidget(self._layer_tag)
        tags.addWidget(self._in_use_tag)
        tags.addStretch(1)
        lay.addLayout(tags)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        self._info = label("", "muted")
        meta.addWidget(self._info)
        self._folder = ElidedLabel("", "small", Qt.TextElideMode.ElideMiddle)
        meta.addWidget(self._folder)
        lay.addLayout(meta)

        lay.addSpacing(4)
        self._display_label = label("Display", "small")
        self._display = QComboBox()
        self._display.setAccessibleName("Display")
        lay.addWidget(self._display_label)
        lay.addWidget(self._display)
        lay.addWidget(label("Fit", "small"))
        self._fit = QComboBox()
        self._fit.setAccessibleName("Fit")
        for fit in FitMode:
            self._fit.addItem(fit.label, fit)
        self._fit.currentIndexChanged.connect(self._fit_changed)
        lay.addWidget(self._fit)

        self._apply = button("Set as wallpaper", primary=True)
        self._apply.clicked.connect(self._apply_clicked)
        lay.addWidget(self._apply)
        self._layer_hint = label("", "small", wrap=True)
        lay.addWidget(self._layer_hint)
        self._remove_live = button("Remove animated wallpaper")
        self._remove_live.clicked.connect(lambda: ctx.controller.clear_animated(self._display.currentData()))
        lay.addWidget(self._remove_live)

        row = QHBoxLayout()
        self._fav = button("Favorite", icon=style.icon("star", "text", on_fill="star"))
        self._fav.setCheckable(True)
        self._fav.toggled.connect(self._fav_toggled)
        reveal = button("Show in folder")
        reveal.clicked.connect(lambda: self._item and ctx.backend.reveal_in_file_manager(self._item.path))
        row.addWidget(self._fav)
        row.addWidget(reveal)
        lay.addLayout(row)

        lay.addSpacing(2)
        lay.addWidget(separator())
        lay.addWidget(label("Use in", "small"))
        links = QVBoxLayout()
        links.setSpacing(0)
        for text, fn in (
            ("Add to slideshow playlist", lambda: page.add_to_slideshow([self._item])),
            ("Use for light theme", lambda: page.use_for_theme(self._item, "light")),
            ("Use for dark theme", lambda: page.use_for_theme(self._item, "dark")),
        ):
            b = button(text, flat=True)
            b.setProperty("link", True)
            b.clicked.connect(fn)
            links.addWidget(b)
        lay.addLayout(links)
        lay.addStretch(1)
        remove = button("Remove from library", flat=True, danger=True)
        remove.clicked.connect(lambda: self._item and page.remove_items([self._item]))
        lay.addWidget(remove)

        ctx.store.changed.connect(self._on_config)
        ctx.controller.wallpaperChanged.connect(self._refresh_monitors)
        ctx.controller.wallpaperChanged.connect(self._sync_state)
        self._refresh_monitors()
        self._on_config("general")
        self.set_item(None)

    def _refresh_monitors(self) -> None:
        current = self._display.currentData()
        self._display.blockSignals(True)
        self._display.clear()
        self._display.addItem("All displays", None)
        for mon in self._ctx.controller.monitors:
            self._display.addItem(f"{mon.name} · {mon.width}×{mon.height}", mon.id)
        idx = self._display.findData(current)
        self._display.setCurrentIndex(max(0, idx))
        self._display.blockSignals(False)
        multi = len(self._ctx.controller.monitors) > 1
        self._display.setVisible(multi)
        self._display_label.setVisible(multi)

    def _on_config(self, section: str) -> None:
        if section in ("general", ""):
            self._fit.blockSignals(True)
            self._fit.setCurrentIndex(self._fit.findData(self._ctx.store.config.general.fit))
            self._fit.blockSignals(False)
        if section == "favorites" and self._item:
            self._sync_fav()

    def _fit_changed(self) -> None:
        self._ctx.store.config.general.fit = self._fit.currentData()
        self._ctx.store.mark_dirty("general")

    def _sync_fav(self) -> None:
        fav = bool(self._item) and self._ctx.library.is_favorite(self._item.path)
        self._fav.blockSignals(True)
        self._fav.setChecked(fav)
        self._fav.blockSignals(False)

    def _fav_toggled(self, checked: bool) -> None:
        if self._item:
            self._ctx.library.set_favorite(self._item.path, checked)
            self._sync_fav()

    def _apply_clicked(self) -> None:
        if self._item:
            self._ctx.controller.set_wallpaper(self._item.path, self._display.currentData())

    def _sync_state(self) -> None:
        item = self._item
        animated_active = any(self._ctx.controller.current_live.values())
        self._remove_live.setVisible(bool(item) and item.is_live and animated_active)
        self._in_use_tag.setVisible(bool(item) and norm(item.path) in self._ctx.controller.in_use)

    def set_item(self, item: MediaItem | None) -> None:
        self._item = item
        self._empty.setVisible(item is None)
        self._scroll.setVisible(item is not None)
        self._sync_state()
        if item is None:
            self._preview.set_path("")
            return
        self._scroll.verticalScrollBar().setValue(0)
        self._preview.set_path(item.path)
        self._type_tag.setText(item.tag)
        self._type_tag.setObjectName("tagAnimated" if item.is_live else "tag")
        style.repolish(self._type_tag)
        self._layer_tag.setText("Animated layer" if item.is_live else "Static layer")
        if item.is_live:
            self._apply.setText("Set as animated wallpaper")
            self._layer_hint.setText("Plays on top of your static wallpaper, which stays in place underneath.")
        else:
            self._apply.setText("Set as static wallpaper")
            self._layer_hint.setText("Your regular desktop wallpaper. Animated wallpapers play on top of it.")
        self._name.setText(item.name)
        self._name.setToolTip(item.name)
        parts = []
        if item.kind is not Kind.VIDEO:
            size = QImageReader(item.path).size()
            if size.isValid():
                parts.append(f"{size.width()}×{size.height()}")
        parts.append(human_size(item.size))
        self._info.setText(" · ".join(parts))
        self._folder.setText(os.path.dirname(item.path))
        self._folder.setToolTip(item.path)
        self._sync_fav()


class LibraryPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("page")
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label("Library", "h1"))
        titles.addWidget(label("Static wallpapers are your regular desktop wallpaper. Animated ones play on top "
                               "of it. Double-click to apply.", "muted", wrap=True))
        head.addLayout(titles, 1)
        head.addSpacing(16)
        add_folder = button("Add folder…", primary=True)
        add_folder.clicked.connect(self._add_folder)
        add_files = button("Add files…")
        add_files.clicked.connect(self._add_files)
        refresh = button("Refresh", icon=style.icon("refresh"),
                         tooltip="Rescan your folders and re-apply every wallpaper (F5)")
        refresh.clicked.connect(ctx.refresh_all)
        folders = button("Folders…")
        folders.clicked.connect(lambda: FoldersDialog(ctx, self).exec())
        for b in (refresh, folders, add_files, add_folder):
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        segmented = QFrame()
        segmented.setObjectName("segmented")
        seg = QHBoxLayout(segmented)
        seg.setContentsMargins(3, 3, 3, 3)
        seg.setSpacing(2)
        self._tabs = QButtonGroup(self)
        self._tab_buttons: dict[str, QPushButton] = {}
        for key in ("static", "animated"):
            b = QPushButton()
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self._tabs.addButton(b)
            self._tab_buttons[key] = b
            seg.addWidget(b)
        self._tab_buttons["static"].setChecked(True)
        self._shown_tab = "static"
        bar.addWidget(segmented)
        self._favorites = button("Favorites", icon=style.icon("star", "text", on_fill="star"))
        self._favorites.setCheckable(True)
        bar.addWidget(self._favorites)
        bar.addSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by name or folder")
        self._search.setAccessibleName("Search wallpapers")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(200)
        self._search.setMaximumWidth(320)
        bar.addWidget(self._search)
        bar.addStretch(1)
        self._count = label("", "muted")
        bar.addWidget(self._count)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(16)
        self._stack = QStackedWidget()
        self._model = LibraryModel(ctx, self)
        self._proxy = LibraryFilter(ctx, self, kind="static")
        self._proxy.setSourceModel(self._model)
        self._grid = GridView(ThumbDelegate(ctx, self))
        self._grid.setModel(self._proxy)
        self._grid.setSelectionMode(GridView.SelectionMode.ExtendedSelection)
        self._grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._grid.customContextMenuRequested.connect(self._context_menu)
        self._grid.doubleClicked.connect(self._apply_index)
        self._grid.selectionModel().currentChanged.connect(lambda cur, _prev: self._details.set_item(
            cur.data(ItemRole) if cur.isValid() else None))
        self._stack.addWidget(self._grid)
        self._stack.addWidget(self._empty_state())
        body.addWidget(self._stack, 1)
        self._details = DetailsPanel(ctx, self)
        body.addWidget(self._details)
        root.addLayout(body, 1)

        self._search.textChanged.connect(self._proxy.set_text)
        self._tabs.buttonClicked.connect(lambda _b: self._tab_changed())
        self._favorites.toggled.connect(self._proxy.set_favorites_only)
        ctx.library.changed.connect(self._update_counts)
        self._proxy.modelReset.connect(self._update_counts)
        self._proxy.rowsInserted.connect(self._update_counts)
        self._proxy.rowsRemoved.connect(self._update_counts)
        self._proxy.layoutChanged.connect(self._update_counts)
        ctx.library.scanningChanged.connect(lambda _s: self._update_counts())
        self._update_counts()

    @property
    def tab(self) -> str:
        return "animated" if self._tab_buttons["animated"].isChecked() else "static"

    def show_tab(self, key: str) -> None:
        self._tab_buttons[key].setChecked(True)
        self._tab_changed()

    def _tab_changed(self) -> None:
        if self.tab == self._shown_tab:
            return
        self._shown_tab = self.tab
        self._proxy.set_kind(self.tab)
        # clear() also drops the current index; clearSelection() alone would leave it set, and
        # clicking that same tile again wouldn't emit currentChanged or fill the details panel.
        self._grid.selectionModel().clear()
        self._details.set_item(None)
        self._update_counts()

    def _empty_state(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        self._empty_title = label("", "h2")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty_title)
        self._empty_text = label("", "muted", wrap=True)
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text.setMaximumWidth(440)
        # Centre with stretches: an alignment flag would size the wrapped label to its minimum width.
        text_row = QHBoxLayout()
        text_row.addStretch(1)
        text_row.addWidget(self._empty_text, 100)
        text_row.addStretch(1)
        lay.addLayout(text_row)
        self._empty_button = button("", primary=True)
        self._empty_button.clicked.connect(lambda: self._empty_action())
        self._empty_action = self._add_folder
        lay.addSpacing(8)
        lay.addWidget(self._empty_button, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)
        return w

    def _set_empty(self, title: str, text: str, action_text: str, action) -> None:
        self._empty_title.setText(title)
        self._empty_text.setText(text)
        self._empty_button.setText(action_text)
        self._empty_action = action

    def _show_all(self) -> None:
        self._search.clear()
        self._favorites.setChecked(False)

    def _update_counts(self) -> None:
        items = self._ctx.library.items
        n_animated = sum(1 for i in items if i.is_live)
        counts = {"static": len(items) - n_animated, "animated": n_animated}
        self._tab_buttons["static"].setText(f"Static  {counts['static']}")
        self._tab_buttons["animated"].setText(f"Animated  {counts['animated']}")
        total = counts[self.tab]
        shown = self._proxy.rowCount()
        noun = "static wallpapers" if self.tab == "static" else "animated wallpapers"
        if self._ctx.library.scanning:
            text = "Scanning…"
        elif shown == total:
            text = f"{total} {noun}"
        else:
            text = f"{shown} of {total} {noun}"
        self._count.setText(text)
        scanning = self._ctx.library.scanning
        empty = total == 0 and not scanning
        filtered_out = total > 0 and shown == 0
        if empty:
            if not items:
                self._set_empty("Start your collection",
                                "Add a folder of images or videos. You can also drag and drop files and "
                                "folders anywhere in this window.", "Add a folder…", self._add_folder)
            elif self.tab == "animated":
                self._set_empty("No animated wallpapers yet",
                                "Add videos (MP4, WebM, MKV, MOV…) or animated images (GIF, animated "
                                "WebP). They play on top of your static wallpaper.", "Add a folder…", self._add_folder)
            else:
                self._set_empty("No static wallpapers yet",
                                "Add images (JPG, PNG, WebP, BMP…). The static wallpaper stays "
                                "underneath any animated one.", "Add a folder…", self._add_folder)
        elif filtered_out:
            query = self._search.text().strip()
            if query:
                self._set_empty("No matches", f"No {noun} match “{query}”"
                                 + (" among your favorites." if self._favorites.isChecked() else "."),
                                 "Clear search", self._show_all)
            else:
                self._set_empty("No favorites here yet",
                                f"Select one of your {noun} and choose Favorite to keep it close at hand.",
                                "Show all", self._show_all)
        self._stack.setCurrentIndex(1 if empty or filtered_out else 0)

    # Actions ------------------------------------------------------------------ #
    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a folder to your library")
        if folder:
            self._ctx.library.add_paths([folder])

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add wallpapers", "", media_file_filter())
        if files:
            self._ctx.library.add_paths(files)

    def _apply_index(self, index) -> None:
        item = index.data(ItemRole)
        if item:
            self._ctx.controller.set_wallpaper(item.path)

    def _selected_items(self) -> list[MediaItem]:
        return [i.data(ItemRole) for i in self._grid.selectionModel().selectedIndexes() if i.data(ItemRole)]

    def add_to_slideshow(self, items: list[MediaItem | None]) -> None:
        cfg = self._ctx.store.config
        existing = {norm(p) for p in cfg.slideshow.items}
        added = 0
        for item in items:
            if item and norm(item.path) not in existing:
                cfg.slideshow.items.append(item.path)
                existing.add(norm(item.path))
                added += 1
        if added:
            cfg.slideshow.use_library = False
            self._ctx.store.mark_dirty("slideshow")
        self._ctx.controller.message.emit(f"Added {added} to the slideshow playlist.")

    def use_for_theme(self, item: MediaItem | None, theme: str) -> None:
        if not item:
            return
        th = self._ctx.store.config.theme
        if theme == "light":
            th.light_wallpaper = item.path
        else:
            th.dark_wallpaper = item.path
        self._ctx.store.mark_dirty("theme")
        self._ctx.controller.message.emit(f"“{item.name}” will be used with the {theme} theme.")

    def remove_items(self, items: list[MediaItem]) -> None:
        self._ctx.library.remove_items([i.path for i in items if i])
        self._details.set_item(None)

    def _context_menu(self, pos: QPoint) -> None:
        index = self._grid.indexAt(pos)
        if not index.isValid():
            return
        item: MediaItem = index.data(ItemRole)
        selected = self._selected_items() or [item]
        menu = QMenu(self)
        noun = "animated" if item.is_live else "static"
        menu.addAction(f"Set as {noun} wallpaper", lambda: self._ctx.controller.set_wallpaper(item.path))
        monitors = self._ctx.controller.monitors
        if len(monitors) > 1:
            sub = menu.addMenu("Set on display")
            for mon in monitors:
                sub.addAction(mon.name, lambda m=mon.id: self._ctx.controller.set_wallpaper(item.path, m))
        if item.is_live and any(self._ctx.controller.current_live.values()):
            menu.addAction("Remove animated wallpaper", self._ctx.controller.clear_animated)
        menu.addSeparator()
        fav = self._ctx.library.is_favorite(item.path)
        act = QAction("Remove from favorites" if fav else "Add to favorites", menu)
        act.triggered.connect(lambda: self._ctx.library.set_favorite(item.path, not fav))
        menu.addAction(act)
        menu.addAction(f"Add to slideshow playlist ({len(selected)})" if len(selected) > 1
                       else "Add to slideshow playlist", lambda: self.add_to_slideshow(selected))
        menu.addAction("Use for light theme", lambda: self.use_for_theme(item, "light"))
        menu.addAction("Use for dark theme", lambda: self.use_for_theme(item, "dark"))
        menu.addSeparator()
        menu.addAction("Show in folder", lambda: self._ctx.backend.reveal_in_file_manager(item.path))
        menu.addAction("Remove from library", lambda: self.remove_items(selected))
        menu.exec(self._grid.viewport().mapToGlobal(pos))
