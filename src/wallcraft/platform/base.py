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
    device: str = ""  # e.g. \\.\DISPLAY1, or the connector name (eDP-1) on Linux
    # Geometry in Qt's device-independent coordinates. Set on Linux and macOS, where live
    # wallpaper windows are positioned through Qt rather than with native calls.
    logical: tuple[int, int, int, int] | None = None

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


def qt_monitors() -> list[Monitor]:
    """Monitors as Qt sees them (id = screen name). Used by the Linux and macOS backends."""
    from PySide6.QtGui import QGuiApplication

    monitors = []
    primary = QGuiApplication.primaryScreen()
    screens = sorted(QGuiApplication.screens(), key=lambda s: (s != primary, s.geometry().x(), s.geometry().y()))
    for i, screen in enumerate(screens):
        g = screen.geometry()
        r = screen.devicePixelRatio()
        name = screen.name() or f"screen{i}"
        monitors.append(Monitor(
            id=name,
            name=f"Display {i + 1}" + (" (primary)" if screen == primary else ""),
            x=round(g.x() * r), y=round(g.y() * r), width=round(g.width() * r), height=round(g.height() * r),
            primary=screen == primary, device=name, logical=(g.x(), g.y(), g.width(), g.height()),
        ))
    return monitors or [Monitor("screen0", "Display 1", 0, 0, 1920, 1080, True, "screen0", (0, 0, 1920, 1080))]


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

    # How live wallpapers are shown on this system:
    #   "attach"   the player opens its own window and the backend moves it behind the icons (Windows)
    #   "surface"  Wallcraft opens a window, the backend turns it into a desktop-level window, and the
    #              player draws into it (Linux X11, macOS)
    #   "external" a helper program draws the wallpaper itself (mpvpaper on Wayland)
    #   "preview"  no desktop integration: show a normal preview window (development)
    #   "none"     not possible here; ``live_unsupported_reason`` explains why
    @property
    def live_strategy(self) -> str:
        return "attach" if self.supports_desktop_embedding else "preview"

    @property
    def live_unsupported_reason(self) -> str:
        return ""

    @property
    def mpv_embeds_by_wid(self) -> bool:
        """True if mpv can draw into a window Wallcraft created (``--wid``)."""
        return False

    def live_external_program(self) -> str | None:
        """Helper used by the "external" strategy (e.g. mpvpaper)."""
        return None

    # Live wallpaper embedding --------------------------------------------- #
    def attach_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        """Place a native window behind the desktop icons on the given monitor."""
        return False

    def ensure_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        """Re-check an attached window. False means it must be recreated."""
        return True

    def refresh_desktop(self) -> None:
        """Repaint the desktop after live windows go away."""

    def reset_desktop(self) -> None:
        """Forget cached desktop window handles so they are looked up again."""

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
