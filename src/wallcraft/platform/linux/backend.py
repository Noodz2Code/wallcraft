"""Linux implementation of the platform Backend (GNOME, KDE, XFCE, Cinnamon, MATE, LXQt, sway…)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from ...config import FitMode
from ...rules import SystemState
from ..base import Backend, Monitor, qt_monitors
from ..images import prepare_image
from . import autostart, desktop, system

log = logging.getLogger(__name__)

# Formats every Linux desktop's wallpaper engine can show; anything else is converted to PNG.
NATIVE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
THEME_WRITE_FAMILIES = {"gnome", "budgie", "cinnamon", "mate", "xfce", "kde"}
PER_MONITOR_FAMILIES = {"xfce", "sway", "hyprland"}


class LinuxBackend(Backend):
    name = "linux"
    supports_autostart = True

    def __init__(self, runner: desktop.Runner | None = None, env: dict[str, str] | None = None) -> None:
        env = os.environ if env is None else env
        self.family = desktop.desktop_family(env)
        self.session = desktop.session_type(env)
        self._runner = runner or desktop.Runner()
        self._x11 = None
        self._x11_failed = False
        self._current: dict[str, str] = {}
        log.info("Linux desktop: %s (%s)", self.family, self.session)

    # Capabilities ---------------------------------------------------------------- #
    @property
    def supports_per_monitor(self) -> bool:  # type: ignore[override]
        return self.family in PER_MONITOR_FAMILIES

    @property
    def supports_os_theme_write(self) -> bool:  # type: ignore[override]
        return self.family in THEME_WRITE_FAMILIES

    @property
    def supports_desktop_embedding(self) -> bool:  # type: ignore[override]
        return self.live_strategy in ("surface", "external")

    @property
    def live_strategy(self) -> str:
        if self.session == "x11":
            return "surface"
        if self.family not in ("gnome", "budgie") and self.live_external_program():
            return "external"
        return "none"

    @property
    def live_unsupported_reason(self) -> str:
        if self.live_strategy != "none":
            return ""
        if self.family in ("gnome", "budgie"):
            return ("GNOME on Wayland doesn't let apps draw behind the desktop. Choose “GNOME on Xorg” on the "
                    "login screen to use animated wallpapers.")
        return "Install mpvpaper (and mpv) to play animated wallpapers on Wayland."

    @property
    def mpv_embeds_by_wid(self) -> bool:
        return self.session == "x11"

    def live_external_program(self) -> str | None:
        return self._runner.which("mpvpaper")

    # Monitors / wallpaper ----------------------------------------------------------- #
    def list_monitors(self) -> list[Monitor]:
        return qt_monitors()

    def set_static_wallpaper(self, path: str, fit: FitMode, monitor_id: str | None = None) -> None:
        image = prepare_image(path, NATIVE_EXTS)
        target = monitor_id if self.supports_per_monitor else None
        if monitor_id and target is None:
            log.info("%s sets one wallpaper for all displays; applying it everywhere", self.family)
        desktop.set_wallpaper(self._runner, self.family, image, fit, target,
                              all_monitors=[m.device for m in qt_monitors()])
        self._current[target or "*"] = path

    def current_static_wallpaper(self, monitor_id: str | None = None) -> str | None:
        return self._current.get(monitor_id or "*") or self._current.get("*")

    # Theme ---------------------------------------------------------------------------- #
    def os_theme(self) -> str:
        theme = desktop.read_theme(self._runner, self.family)
        if theme:
            return theme
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication

            return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
        except Exception:  # noqa: BLE001
            return "light"

    def set_os_theme(self, apps_light: bool | None, system_light: bool | None) -> None:
        light = apps_light if apps_light is not None else system_light
        if light is None:
            return
        desktop.write_theme(self._runner, self.family, dark=not light)

    # System state ----------------------------------------------------------------------- #
    def _x(self):
        if self._x11 is None and not self._x11_failed and self.session == "x11":
            try:
                from .x11 import X11

                self._x11 = X11()
            except OSError as exc:
                self._x11_failed = True
                log.warning("X11 features unavailable: %s", exc)
        return self._x11

    def system_state(self, monitors: list[Monitor]) -> SystemState:
        has_battery, on_battery, percent = system.battery_status()
        fullscreen = maximized = frozenset()
        x = self._x()
        if x is not None:
            from .x11 import occluded_monitors

            try:
                fullscreen, maximized = occluded_monitors(x, monitors)
            except OSError as exc:
                log.debug("Window check failed: %s", exc)
        return SystemState(
            has_battery=has_battery, on_battery=on_battery, battery_percent=percent,
            battery_saver=system.power_saver_on(), session_locked=system.session_locked(),
            fullscreen_monitors=fullscreen, maximized_monitors=maximized,
        )

    # Live wallpaper windows ---------------------------------------------------------------- #
    def attach_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        x = self._x()
        if x is None:
            return False
        x.make_desktop_window(hwnd)
        return True

    def ensure_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        x = self._x()
        return x is None or x.window_exists(hwnd)

    # Misc ------------------------------------------------------------------------------------ #
    def autostart_enabled(self) -> bool:
        return autostart.is_enabled()

    def set_autostart(self, enabled: bool) -> None:
        autostart.set_enabled(enabled)

    def reveal_in_file_manager(self, path: str) -> None:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            fm = QDBusInterface("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                                "org.freedesktop.FileManager1", QDBusConnection.sessionBus())
            if fm.isValid():
                fm.call("ShowItems", [Path(path).resolve().as_uri()], "")
                return
        except ImportError:
            pass
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, str(Path(path).resolve().parent)])  # noqa: S603
