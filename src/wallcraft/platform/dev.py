"""Development backend for non-Windows systems.

Lets the UI and engine run on Linux/macOS for development. Live wallpapers open
in normal preview windows; static wallpapers are applied on GNOME when possible.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import FitMode
from .base import Backend, Monitor

log = logging.getLogger(__name__)

_GNOME_FIT = {
    FitMode.FILL: "zoom",
    FitMode.FIT: "scaled",
    FitMode.STRETCH: "stretched",
    FitMode.CENTER: "centered",
    FitMode.TILE: "wallpaper",
    FitMode.SPAN: "spanned",
}


class DevBackend(Backend):
    name = "dev"

    def __init__(self) -> None:
        self._current: dict[str, str] = {}
        self._gsettings = shutil.which("gsettings") if sys.platform.startswith("linux") else None

    def list_monitors(self) -> list[Monitor]:
        from PySide6.QtGui import QGuiApplication

        monitors = []
        for i, screen in enumerate(QGuiApplication.screens()):
            g = screen.geometry()
            r = screen.devicePixelRatio()
            monitors.append(Monitor(
                id=screen.name() or f"screen{i}",
                name=f"Display {i + 1}",
                x=int(g.x() * r), y=int(g.y() * r),
                width=int(g.width() * r), height=int(g.height() * r),
                primary=screen == QGuiApplication.primaryScreen(),
                device=screen.name(),
            ))
        return monitors or [Monitor("screen0", "Display 1", 0, 0, 1920, 1080, True)]

    def set_static_wallpaper(self, path: str, fit: FitMode, monitor_id: str | None = None) -> None:
        self._current[monitor_id or "*"] = path
        log.info("[dev] static wallpaper %s -> %s (%s)", monitor_id or "all", path, fit.value)
        if self._gsettings:
            uri = Path(path).resolve().as_uri()
            for key in ("picture-uri", "picture-uri-dark"):
                subprocess.run([self._gsettings, "set", "org.gnome.desktop.background", key, uri],
                               check=False, capture_output=True)
            subprocess.run([self._gsettings, "set", "org.gnome.desktop.background", "picture-options",
                            _GNOME_FIT[fit]], check=False, capture_output=True)

    def current_static_wallpaper(self, monitor_id: str | None = None) -> str | None:
        return self._current.get(monitor_id or "*") or self._current.get("*")

    def os_theme(self) -> str:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication

            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:  # noqa: BLE001 - very old Qt or no app instance
            return "light"
