"""Main application window: sidebar navigation + pages."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
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
from ..library import file_tag
from ..osinfo import SYSTEM_NAME
from ..paths import resource
from .pages.library import LibraryPage
from .pages.performance import PerformancePage
from .pages.settings import SettingsPage
from .pages.slideshow import SlideshowPage
from .pages.theme import ThemePage
from .pages.timeofday import TimeOfDayPage
from .widgets import ElidedLabel, ThumbLabel, button, icon_button, label

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
    """One wallpaper layer in the sidebar: thumbnail with its type badge, layer name, file name."""

    def __init__(self, ctx: AppContext, title: str, animated: bool) -> None:
        super().__init__()
        self._animated = animated
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.thumb = ThumbLabel(ctx, QSize(64, 40), compact=True)
        row.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addStretch(1)
        text.addWidget(label(title, "layerName"))
        self.name = ElidedLabel("", "small")
        text.addWidget(self.name)
        self.status = ElidedLabel("", "small")
        self.status.setVisible(False)
        text.addWidget(self.status)
        text.addStretch(1)
        row.addLayout(text, 1)
        self.remove = icon_button("close", "Remove the animated wallpaper", size=24)
        self.remove.setVisible(False)
        row.addWidget(self.remove, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_paths(self, paths: list[str], empty_text: str, empty_hint: str = "") -> None:
        first = paths[0] if paths else ""
        self.thumb.set_path(first)
        self.thumb.set_badge(file_tag(first) if first else "", self._animated)
        if first:
            name = os.path.splitext(os.path.basename(first))[0]
            extra = len(set(paths)) - 1
            self.name.setText(name + (f" +{extra}" if extra > 0 else ""))
            self.name.setToolTip("\n".join(dict.fromkeys(paths)))
        else:
            self.name.setText(empty_text)
            self.name.setToolTip(empty_hint)
        self.remove.setVisible(self._animated and bool(first))

    def set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setToolTip(text)
        self.status.setVisible(bool(text))


class NowShowing(QFrame):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label("Now showing", "small"))
        self._animated = LayerRow(ctx, "Animated", animated=True)
        self._animated.remove.clicked.connect(lambda: ctx.controller.clear_animated())
        self._static = LayerRow(ctx, "Static", animated=False)
        lay.addWidget(self._animated)
        lay.addWidget(self._static)
        lay.addSpacing(10)
        lay.addWidget(label("Mode", "small"))
        self._mode = QComboBox()
        self._mode.setAccessibleName("Mode")
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

        self._static.set_paths(paths(c.current_static), "Not set", f"{SYSTEM_NAME} keeps its own wallpaper")
        self._animated.set_paths(paths(c.current_live), "None")
        self._animated.set_status(c.live_status() if c.live.has_assignments else "")
        self._mode.blockSignals(True)
        self._mode.setCurrentIndex(self._mode.findData(self._ctx.store.config.mode))
        self._mode.blockSignals(False)


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
        self._update_btn = button("Update available", primary=True)
        self._update_btn.setVisible(False)
        self._update_btn.clicked.connect(self.open_update)
        side.addSpacing(6)
        side.addWidget(self._update_btn)
        side.addSpacing(8)
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
        refresh = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        refresh.activated.connect(ctx.refresh_all)

        if ctx.updates is not None:
            ctx.updates.available.connect(self._on_update_available)
            ctx.updates.up_to_date.connect(lambda _r, manual: manual and self._report_update())
            ctx.updates.failed.connect(lambda _e, manual: manual and self._report_update())

    # Updates ------------------------------------------------------------------------- #
    def _on_update_available(self, release, manual: bool) -> None:
        self._update_btn.setText(f"Update to {release.version}")
        self._update_btn.setToolTip(f"Wallcraft {release.version} is available. Click to see what's new.")
        self._update_btn.setVisible(True)
        if manual:
            self._report_update()

    def _report_update(self) -> None:
        from .update_dialog import show_update_result

        if self._ctx.updates is not None:
            show_update_result(self if self.isVisible() else None, self._ctx.updates)

    def open_update(self) -> None:
        from .update_dialog import UpdateDialog

        u = self._ctx.updates
        if u is not None and u.latest is not None:
            UpdateDialog(u.latest, u, self).exec()

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
