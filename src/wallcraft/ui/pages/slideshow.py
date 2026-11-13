"""Slideshow page: rotate through the library or a playlist on a timer."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QSpinBox,
)

from ...config import Mode
from .. import style
from ..picker import media_file_filter, pick_wallpaper
from ..widgets import Card, ModeBanner, Page, button, label, rounded

if TYPE_CHECKING:
    from ..context import AppContext

ICON = QSize(72, 45)


class SlideshowPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Slideshow", "Rotate through wallpapers on a timer.")
        self._ctx = ctx
        self.content.addWidget(ModeBanner(ctx, Mode.SLIDESHOW,
                                          "Slideshow mode is off. Turn it on to start rotating wallpapers."))

        # Source ------------------------------------------------------------- #
        src = Card("Source")
        self._library_radio = QRadioButton("Entire library")
        self._playlist_radio = QRadioButton("Playlist below")
        group = QButtonGroup(self)
        group.addButton(self._library_radio)
        group.addButton(self._playlist_radio)
        row = QHBoxLayout()
        row.addWidget(self._library_radio)
        row.addWidget(self._playlist_radio)
        row.addStretch(1)
        src.body.addLayout(row)
        self._include_live = QCheckBox("Include live wallpapers (videos and animated images)")
        src.body.addWidget(self._include_live)
        self.content.addWidget(src)

        # Timing -------------------------------------------------------------- #
        timing = Card("Timing")
        row = QHBoxLayout()
        row.addWidget(label("Change every"))
        self._interval = QSpinBox()
        self._interval.setRange(1, 7 * 24 * 60)
        self._interval.setSuffix(" min")
        self._interval.setMinimumWidth(110)
        row.addWidget(self._interval)
        for minutes, text in ((5, "5m"), (30, "30m"), (60, "1h"), (360, "6h"), (1440, "1d")):
            b = button(text, flat=True)
            b.clicked.connect(lambda _c=False, m=minutes: self._interval.setValue(m))
            row.addWidget(b)
        row.addStretch(1)
        timing.body.addLayout(row)
        self._shuffle = QCheckBox("Shuffle")
        timing.body.addWidget(self._shuffle)
        ctl = QHBoxLayout()
        prev = button("Previous", icon=style.icon("chevron-left"))
        prev.clicked.connect(lambda: ctx.controller.next_wallpaper(-1))
        nxt = button("Next", icon=style.icon("chevron-right"))
        nxt.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # chevron after the text
        nxt.clicked.connect(lambda: ctx.controller.next_wallpaper(1))
        ctl.addWidget(prev)
        ctl.addWidget(nxt)
        ctl.addSpacing(12)
        self._countdown = label("", "muted")
        ctl.addWidget(self._countdown)
        ctl.addStretch(1)
        timing.body.addLayout(ctl)
        self.content.addWidget(timing)

        # Playlist ------------------------------------------------------------ #
        self._playlist_card = Card("Playlist", "Drag to reorder. Folders include everything inside them.")
        self._list = QListWidget()
        self._list.setObjectName("list")
        self._list.setIconSize(ICON)
        self._list.setMinimumHeight(260)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.model().rowsMoved.connect(lambda *_: self._save_playlist())
        self._playlist_card.body.addWidget(self._list)
        row = QHBoxLayout()
        for text, fn in (("Add from library…", self._add_from_library), ("Add files…", self._add_files),
                         ("Add folder…", self._add_folder)):
            b = button(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        remove = button("Remove")
        remove.clicked.connect(self._remove_selected)
        clear = button("Clear", danger=True)
        clear.clicked.connect(self._clear)
        row.addWidget(remove)
        row.addWidget(clear)
        self._playlist_card.body.addLayout(row)
        self.content.addWidget(self._playlist_card)
        self.content.addStretch(1)

        # Wiring -------------------------------------------------------------- #
        self._library_radio.toggled.connect(self._source_changed)
        self._include_live.toggled.connect(self._options_changed)
        self._shuffle.toggled.connect(self._options_changed)
        self._interval.valueChanged.connect(self._options_changed)
        ctx.thumbs.ready.connect(self._thumb_ready)
        ctx.store.changed.connect(lambda s: self._load() if s in ("slideshow", "") else None)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start()
        self._load()

    # Load / save ------------------------------------------------------------- #
    def _load(self) -> None:
        cfg = self._ctx.store.config.slideshow
        widgets = (self._library_radio, self._playlist_radio, self._include_live, self._shuffle, self._interval)
        for w in widgets:
            w.blockSignals(True)
        self._library_radio.setChecked(cfg.use_library)
        self._playlist_radio.setChecked(not cfg.use_library)
        self._include_live.setChecked(cfg.include_live)
        self._shuffle.setChecked(cfg.shuffle)
        self._interval.setValue(cfg.interval_minutes)
        for w in widgets:
            w.blockSignals(False)
        self._playlist_card.setEnabled(not cfg.use_library)
        self._list.clear()
        for path in cfg.items:
            self._add_list_item(path)
        self._update_countdown()

    def _add_list_item(self, path: str) -> None:
        is_dir = os.path.isdir(path)
        name = os.path.basename(path.rstrip("\\/")) or path
        item = QListWidgetItem(f"{name}  (folder)" if is_dir else name)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        if not is_dir:
            pix = self._ctx.thumbs.get(path)
            if pix is not None:
                item.setIcon(QIcon(rounded(pix, ICON, 6)))
        self._list.addItem(item)

    def _thumb_ready(self, path: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                pix = self._ctx.thumbs.get(path)
                if pix is not None:
                    item.setIcon(QIcon(rounded(pix, ICON, 6)))

    def _save_playlist(self) -> None:
        cfg = self._ctx.store.config.slideshow
        cfg.items = [self._list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self._list.count())]
        self._ctx.store.mark_dirty("playlist")

    def _source_changed(self) -> None:
        cfg = self._ctx.store.config.slideshow
        cfg.use_library = self._library_radio.isChecked()
        self._playlist_card.setEnabled(not cfg.use_library)
        self._ctx.store.mark_dirty("slideshow-options")

    def _options_changed(self) -> None:
        cfg = self._ctx.store.config.slideshow
        cfg.include_live = self._include_live.isChecked()
        cfg.shuffle = self._shuffle.isChecked()
        cfg.interval_minutes = self._interval.value()
        self._ctx.store.mark_dirty("slideshow-options")

    # Playlist editing ---------------------------------------------------------- #
    def _append(self, paths: list[str]) -> None:
        existing = {self._list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self._list.count())}
        for p in paths:
            if p and p not in existing:
                self._add_list_item(p)
                existing.add(p)
        self._save_playlist()

    def _add_from_library(self) -> None:
        path = pick_wallpaper(self._ctx, self)
        if path:
            self._append([path])

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add to playlist", "", media_file_filter())
        self._append(files)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a folder to the playlist")
        if folder:
            # Folder contents come from the library, so make sure it's scanned.
            self._ctx.library.add_paths([folder])
            self._append([folder])

    def _remove_selected(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))
        self._save_playlist()

    def _clear(self) -> None:
        self._list.clear()
        self._save_playlist()

    def _update_countdown(self) -> None:
        if not self.isVisible():
            return
        when = self._ctx.controller.slideshow_next_change()
        if when is None:
            self._countdown.setText("")
            return
        remaining = max(0, int(when - time.time()))
        h, rem = divmod(remaining, 3600)
        m, s = divmod(rem, 60)
        self._countdown.setText(f"Next change in {h}:{m:02d}:{s:02d}" if h else f"Next change in {m}:{s:02d}")
