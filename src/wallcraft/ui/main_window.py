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
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import Mode
from ..paths import resource
from .pages.library import LibraryPage
from .pages.performance import PerformancePage
from .pages.settings import SettingsPage
from .pages.slideshow import SlideshowPage
from .pages.theme import ThemePage
from .pages.timeofday import TimeOfDayPage
from .widgets import ThumbLabel, label

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


class NowShowing(QFrame):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(label("NOW SHOWING", "small"))
        self._thumb = ThumbLabel(ctx, QSize(198, 111))
        lay.addWidget(self._thumb)
        self._name = label("", "small")
        self._name.setMaximumWidth(198)
        lay.addWidget(self._name)
        lay.addSpacing(6)
        lay.addWidget(label("MODE", "small"))
        self._mode = QComboBox()
        for mode in Mode:
            self._mode.addItem(mode.label, mode)
        self._mode.currentIndexChanged.connect(lambda _i: ctx.controller.set_mode(self._mode.currentData()))
        lay.addWidget(self._mode)
        self._live = label("", "small")
        self._live.setWordWrap(True)
        self._live.setMaximumWidth(198)
        lay.addWidget(self._live)

        ctx.controller.wallpaperChanged.connect(self._update)
        ctx.controller.liveStatusChanged.connect(self._update)
        ctx.store.changed.connect(lambda _s: self._update())
        self._update()

    def _update(self) -> None:
        c = self._ctx.controller
        paths = [p for p in (c.current.get(m.id, "") for m in c.monitors) if p]
        first = paths[0] if paths else ""
        self._thumb.set_path(first)
        if first:
            name = os.path.splitext(os.path.basename(first))[0]
            extra = len(set(paths)) - 1
            text = name + (f"  +{extra} more" if extra > 0 else "")
        else:
            text = "Nothing set yet"
        self._name.setText(self._name.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 198))
        self._name.setToolTip("\n".join(dict.fromkeys(paths)))
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
