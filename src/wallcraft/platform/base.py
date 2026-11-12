"""Platform abstraction. Everything OS-specific goes through a Backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import FitMode
from ..rules import SystemState


@dataclass(frozen=True)
class Monitor:
    id: str  # stable identifier used in config (device path on Windows)
    name: str  # human readable
    x: int  # physical pixels, virtual-desktop coordinates
    y: int
    width: int
    height: int
    primary: bool = False
    device: str = ""  # e.g. \\.\DISPLAY1

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


class Backend(ABC):
    name = "base"
    supports_desktop_embedding = False
    supports_per_monitor = False
    supports_os_theme_write = False
    supports_autostart = False

    @abstractmethod
    def list_monitors(self) -> list[Monitor]: ...

    @abstractmethod
    def set_static_wallpaper(self, path: str, fit: FitMode, monitor_id: str | None = None) -> None:
        """Set a still image. ``monitor_id=None`` means every monitor."""

    def current_static_wallpaper(self, monitor_id: str | None = None) -> str | None:
        return None

    @abstractmethod
    def os_theme(self) -> str:
        """"light" or "dark" (the app colour mode)."""

    def set_os_theme(self, apps_light: bool | None, system_light: bool | None) -> None:
        raise NotImplementedError

    def system_state(self, monitors: list[Monitor]) -> SystemState:
        return SystemState()

    # Live wallpaper embedding --------------------------------------------- #
    def attach_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        """Place a native window behind the desktop icons on the given monitor."""
        return False

    def ensure_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        """Re-check an attached window. False means it must be recreated."""
        return True

    def refresh_desktop(self) -> None:
        """Repaint the desktop after live windows go away."""

    def find_process_window(self, pid: int, class_name: str = "mpv") -> int | None:
        """Top-level window of a child process (used to embed the mpv player)."""
        return None

    def adopt_child_process(self, pid: int) -> None:
        """Make a child process exit together with Wallcraft, even after a crash."""

    # Misc ----------------------------------------------------------------- #
    def autostart_enabled(self) -> bool:
        return False

    def set_autostart(self, enabled: bool) -> None:
        raise NotImplementedError

    def reveal_in_file_manager(self, path: str) -> None:
        pass

    def set_full_quality_jpeg(self, enabled: bool) -> None:
        pass
