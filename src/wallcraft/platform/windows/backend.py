"""Windows implementation of the platform Backend."""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess

from ...config import FitMode
from ...library import NATIVE_IMAGE_EXTS
from ...paths import converted_dir
from ...rules import SystemState
from ..base import Backend, Monitor
from . import autostart, desktop, jobs, system, theme, wallpaper, win32

log = logging.getLogger(__name__)


class WindowsBackend(Backend):
    name = "windows"
    supports_desktop_embedding = True
    supports_per_monitor = True
    supports_os_theme_write = True
    supports_autostart = True

    def __init__(self) -> None:
        self._host: desktop.DesktopHost | None = None
        self._job: jobs.KillOnCloseJob | None = None

    # Monitors ------------------------------------------------------------- #
    def list_monitors(self) -> list[Monitor]:
        displays = win32.enum_monitors()
        com = {m.rect: m.path for m in wallpaper.com_monitors()}
        displays.sort(key=lambda d: (not d[2], d[1][0], d[1][1]))  # primary first, then left to right
        monitors = []
        for i, (device, rect, primary) in enumerate(displays):
            x, y, w, h = rect
            monitors.append(Monitor(
                id=com.get(rect, device),
                name=f"Display {i + 1}" + (" (primary)" if primary else ""),
                x=x, y=y, width=w, height=h, primary=primary, device=device,
            ))
        return monitors

    # Static wallpaper ----------------------------------------------------- #
    def _prepare(self, path: str) -> str:
        path = os.path.abspath(path)
        if os.path.splitext(path)[1].lower() in NATIVE_IMAGE_EXTS:
            return path
        # Convert formats Explorer can't render (e.g. WebP) to PNG once and cache.
        from PySide6.QtGui import QImage

        st = os.stat(path)
        key = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()
        out = converted_dir() / f"{key}.png"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            img = QImage(path)
            if img.isNull() or not img.save(str(out), "PNG"):
                raise OSError(f"Could not convert {path} for use as a wallpaper")
        return str(out)

    def set_static_wallpaper(self, path: str, fit: FitMode, monitor_id: str | None = None) -> None:
        wallpaper.set_wallpaper(self._prepare(path), fit, monitor_id)

    def current_static_wallpaper(self, monitor_id: str | None = None) -> str | None:
        return wallpaper.get_wallpaper(monitor_id)

    def set_full_quality_jpeg(self, enabled: bool) -> None:
        try:
            wallpaper.set_jpeg_import_quality(enabled)
        except OSError as exc:
            log.warning("Could not change JPEGImportQuality: %s", exc)

    # Theme ---------------------------------------------------------------- #
    def os_theme(self) -> str:
        return "light" if theme.apps_use_light_theme() else "dark"

    def set_os_theme(self, apps_light: bool | None, system_light: bool | None) -> None:
        theme.set_theme(apps_light, system_light)

    # Power / occlusion ---------------------------------------------------- #
    def system_state(self, monitors: list[Monitor]) -> SystemState:
        return system.system_state(monitors)

    # Live wallpaper embedding --------------------------------------------- #
    def _desktop_host(self) -> desktop.DesktopHost | None:
        if self._host is None or not self._host.alive():
            self._host = desktop.find_desktop_host()
        return self._host

    def attach_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        host = self._desktop_host()
        if host is None:
            return False
        return desktop.attach(hwnd, monitor.rect, host)

    def ensure_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        host = self._host
        if host is None or not win32.IsWindow(host.progman):
            self._host = None  # Explorer restarted
            return False
        if not host.alive():
            if not host.raised:
                self._host = None  # legacy WorkerW gone, and our child windows with it
                return False
            # 24H2: Explorer recreated its WorkerW (e.g. after a wallpaper change). Our window is a
            # child of Progman and survives; pick up the new WorkerW and repair the z-order.
            self._host = host = desktop.find_desktop_host()
            if host is None:
                return False
        return desktop.ensure(hwnd, monitor.rect, host)

    def refresh_desktop(self) -> None:
        desktop.refresh_wallpaper(self._host)

    def find_process_window(self, pid: int, class_name: str = "mpv") -> int | None:
        for hwnd in win32.enum_windows():
            if win32.window_pid(hwnd) == pid and win32.class_name(hwnd) == class_name:
                return hwnd
        return None

    def adopt_child_process(self, pid: int) -> None:
        if self._job is None:
            try:
                self._job = jobs.KillOnCloseJob()
            except OSError as exc:
                log.warning("Could not create job object: %s", exc)
                return
        self._job.assign(pid)

    # Misc ----------------------------------------------------------------- #
    def autostart_enabled(self) -> bool:
        return autostart.is_enabled()

    def set_autostart(self, enabled: bool) -> None:
        autostart.set_enabled(enabled)

    def reveal_in_file_manager(self, path: str) -> None:
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')  # noqa: S602
