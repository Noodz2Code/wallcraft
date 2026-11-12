"""System tray icon and menu."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import APP_NAME
from ..config import Mode

if TYPE_CHECKING:
    from .context import AppContext
    from .main_window import MainWindow


class Tray(QSystemTrayIcon):
    def __init__(self, ctx: AppContext, window: MainWindow, icon: QIcon, on_quit: Callable[[], None]) -> None:
        super().__init__(icon)
        self._ctx = ctx
        self._window = window
        menu = QMenu()
        menu.addAction("Open Wallcraft", window.show_and_raise)
        menu.addSeparator()
        menu.addAction("Next wallpaper", lambda: ctx.controller.next_wallpaper(1))
        menu.addAction("Previous wallpaper", lambda: ctx.controller.next_wallpaper(-1))
        self._pause = QAction("Pause live wallpapers", menu)
        self._pause.setCheckable(True)
        self._pause.triggered.connect(lambda _c: ctx.controller.toggle_pause())
        menu.addAction(self._pause)
        menu.addSeparator()
        modes = menu.addMenu("Mode")
        self._mode_group = QActionGroup(modes)
        self._mode_actions: dict[Mode, QAction] = {}
        for mode in Mode:
            act = QAction(mode.label, modes)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, m=mode: ctx.controller.set_mode(m))
            self._mode_group.addAction(act)
            modes.addAction(act)
            self._mode_actions[mode] = act
        menu.addSeparator()
        menu.addAction("Quit Wallcraft", on_quit)
        self._menu = menu  # keep a reference; QSystemTrayIcon doesn't own it
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        ctx.controller.wallpaperChanged.connect(self._sync)
        ctx.controller.liveStatusChanged.connect(self._sync)
        ctx.store.changed.connect(lambda _s: self._sync())
        window.on_tray_hint = lambda: self.showMessage(
            APP_NAME, "Wallcraft is still running here. Quit from this menu.",
            QSystemTrayIcon.MessageIcon.Information, 4000)
        self._sync()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self._window.isVisible() and not self._window.isMinimized():
                self._window.hide()
            else:
                self._window.show_and_raise()

    def _sync(self) -> None:
        c = self._ctx.controller
        mode = self._ctx.store.config.mode
        self._mode_actions[mode].setChecked(True)
        self._pause.setChecked(c.user_paused)
        self._pause.setEnabled(c.live.has_assignments)
        current = next((p for p in c.current.values() if p), "")
        name = os.path.splitext(os.path.basename(current))[0] if current else "no wallpaper"
        tip = f"{APP_NAME} · {mode.label}\n{name}"
        self.setToolTip(tip[:120])
