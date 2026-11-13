"""Main application window: sidebar navigation + pages."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import Mode
from ..library import file_tag
from ..paths import resource
from .pages.library import LibraryPage
from .pages.performance import PerformancePage
from .pages.settings import SettingsPage
from .pages.slideshow import SlideshowPage
from .pages.theme import ThemePage
from .pages.timeofday import TimeOfDayPage
from .widgets import ThumbLabel, button, label

if TYPE_CHECKING:
    from .context import AppContext

PAGES = (
    ("Library", LibraryPage),
    ("Slideshow", SlideshowPage),
    ("Time of day", TimeOfDayPage),
    ("Theme sync", ThemePage),
    ("Performance", PerformancePage),
    ("Settings", SettingsPage),
)


class LayerRow(QFrame):
    """One wallpaper layer in the sidebar: small thumbnail, layer name, file name and type tag."""

    def __init__(self, ctx: AppContext, title: str, animated: bool) -> None:
        super().__init__()
        self._title = title
        self._animated = animated
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.thumb = ThumbLabel(ctx, QSize(64, 40))
        row.addWidget(self.thumb)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title, "layerName"))
        line = QHBoxLayout()
        line.setSpacing(5)
        self.tag = label("", "tagAnimated" if animated else "tag")
        line.addWidget(self.tag)
        self.name = label("", "small")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        line.addWidget(self.name, 1)
        text.addLayout(line)
        row.addLayout(text, 1)
        self.remove = button("✕", flat=True, tooltip="Remove the animated wallpaper")
        self.remove.setFixedWidth(26)
        self.remove.setVisible(False)
        row.addWidget(self.remove, 0, Qt.AlignmentFlag.AlignTop)

    def set_paths(self, paths: list[str], empty_text: str) -> None:
        first = paths[0] if paths else ""
        self.thumb.set_path(first)
        self.tag.setVisible(bool(first))
        self.tag.setText(file_tag(first) if first else "")
        if first:
            name = os.path.splitext(os.path.basename(first))[0]
            extra = len(set(paths)) - 1
            text = name + (f" +{extra}" if extra > 0 else "")
        else:
            text = empty_text
        # Sidebar is 198px: thumbnail 64 + gap 8 + remove button 26 leaves ~100px for tag + name.
        width = 100 - (self.tag.sizeHint().width() + 5 if first else 0)
        self.name.setText(self.name.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(40, width)))
        self.name.setToolTip("\n".join(dict.fromkeys(paths)))
        self.remove.setVisible(self._animated and bool(first))


class NowShowing(QFrame):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("NOW SHOWING", "small"))
        self._animated = LayerRow(ctx, "Animated", animated=True)
        self._animated.remove.clicked.connect(lambda: ctx.controller.clear_animated())
        self._static = LayerRow(ctx, "Static", animated=False)
        lay.addWidget(self._animated)
        lay.addWidget(self._static)
        self._live = label("", "small")
        self._live.setWordWrap(True)
        self._live.setMaximumWidth(198)
        lay.addWidget(self._live)
        lay.addSpacing(4)
        lay.addWidget(label("MODE", "small"))
        self._mode = QComboBox()
        for mode in Mode:
            self._mode.addItem(mode.label, mode)
        self._mode.currentIndexChanged.connect(lambda _i: ctx.controller.set_mode(self._mode.currentData()))
        lay.addWidget(self._mode)

        ctx.controller.wallpaperChanged.connect(self._update)
        ctx.controller.liveStatusChanged.connect(self._update)
        ctx.store.changed.connect(lambda _s: self._update())
        self._update()

    def _update(self) -> None:
        c = self._ctx.controller

        def paths(layer: dict[str, str]) -> list[str]:
            return [p for p in (layer.get(m.id, "") for m in c.monitors) if p]

        self._static.set_paths(paths(c.current_static), "Not set: Windows keeps its own")
        self._animated.set_paths(paths(c.current_live), "None")
        self._mode.blockSignals(True)
        self._mode.setCurrentIndex(self._mode.findData(self._ctx.store.config.mode))
        self._mode.blockSignals(False)
        live = c.live.has_assignments
        self._live.setVisible(live)
        if live:
            self._live.setText(c.live_status())


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, on_quit: Callable[[], None]) -> None:
        super().__init__()
        self._ctx = ctx
        self._on_quit = on_quit
        self.on_tray_hint: Callable[[], None] | None = None  # set by the tray icon
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource("icon.png"))))
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 18)
        side.setSpacing(6)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(resource("icon.png"))).pixmap(28, 28))
        brand.addWidget(logo)
        brand.addWidget(label(APP_NAME, "appTitle"))
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(14)
        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setCursor(Qt.CursorShape.PointingHandCursor)
        side.addWidget(self._nav, 1)
        side.addWidget(NowShowing(ctx))
        root.addWidget(sidebar)

        self._stack = QStackedWidget()
        self._nav.setSpacing(1)
        for title, cls in PAGES:
            item = QListWidgetItem(title)
            item.setSizeHint(QSize(0, 36))
            self._nav.addItem(item)
            self._stack.addWidget(cls(ctx))
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)
        root.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        ctx.controller.message.connect(lambda text: self.statusBar().showMessage(text, 6000))

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_page(self, title: str) -> None:
        for i, (name, _cls) in enumerate(PAGES):
            if name == title:
                self._nav.setCurrentRow(i)

    # Drag & drop files/folders anywhere to add them to the library ---------------- #
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            added = self._ctx.library.add_paths(paths)
            self.statusBar().showMessage(
                f"Added {added} item(s) to your library." if added else "Nothing new to add.", 5000)
            self.show_page("Library")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        g = self._ctx.store.config.general
        if g.close_to_tray and self.tray_available:
            event.ignore()
            self.hide()
            if not g.tray_hint_shown:
                g.tray_hint_shown = True
                self._ctx.store.save_later()
                if self.on_tray_hint:
                    self.on_tray_hint()
            return
        event.accept()
        self._on_quit()
