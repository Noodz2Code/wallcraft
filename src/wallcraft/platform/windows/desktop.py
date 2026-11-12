"""Placing windows behind the desktop icons, the way Lively Wallpaper does it.

Sending the undocumented message 0x052C to Progman makes Explorer create a
"WorkerW" window between the wallpaper and the icons. Two desktop layouts exist:

Legacy (Windows 10, Windows 11 before 24H2)
    WorkerW is a top-level window right after the window that hosts the icon
    view (SHELLDLL_DefView). Wallpaper windows become children of that WorkerW.

Raised (Windows 11 24H2+)
    Progman is created with WS_EX_NOREDIRECTIONBITMAP and both the icon view and
    WorkerW are its children. Microsoft's guidance (quoted in Lively's source):
    "create your own WS_EX_LAYERED child HWND that is z-ordered under the DefView
    window but above the WorkerW window", with SetLayeredWindowAttributes(alpha 255).
    Changing the static wallpaper destroys and recreates WorkerW in this layout,
    so callers must avoid it while live windows are attached, and ensure() repairs
    the z-order if it happens anyway.

Reference: lively-community/lively, src/Lively/Lively/Core/WinDesktopCore.cs
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes as wt
from dataclasses import dataclass

from . import win32

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DesktopHost:
    progman: int
    workerw: int
    defview: int | None
    raised: bool

    @property
    def parent(self) -> int:
        return self.progman if self.raised else self.workerw

    def alive(self) -> bool:
        return bool(win32.IsWindow(self.progman) and win32.IsWindow(self.workerw))


def _spawn_and_find() -> DesktopHost | None:
    progman = win32.FindWindowW("Progman", None)
    if not progman:
        log.error("Progman not found; is Explorer running?")
        return None
    raised = bool(win32.ex_style(progman) & win32.WS_EX_NOREDIRECTIONBITMAP)

    # Ask Explorer for a WorkerW behind the icons. Harmless if one already exists.
    result = ctypes.c_size_t()
    win32.SendMessageTimeoutW(progman, win32.WM_SPAWN_WORKER, 0xD, 0x1, win32.SMTO_NORMAL, 1000,
                              ctypes.byref(result))

    workerw = defview = None
    for top in win32.enum_windows():
        view = win32.FindWindowExW(top, None, "SHELLDLL_DefView", None)
        if view:
            defview = view
            workerw = win32.FindWindowExW(None, top, "WorkerW", None)

    if raised:
        workerw = win32.FindWindowExW(progman, None, "WorkerW", None)
        defview = win32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) or defview

    if not workerw:
        return None
    return DesktopHost(progman=progman, workerw=workerw, defview=defview, raised=raised)


def find_desktop_host() -> DesktopHost | None:
    host = _spawn_and_find()
    if host is None:
        # Explorer sometimes needs a moment to create the WorkerW (Lively retries the same way).
        time.sleep(0.5)
        host = _spawn_and_find()
    if host is None:
        log.error("Could not find the desktop WorkerW window")
    else:
        log.info("Desktop layer: %s layout (WorkerW %#x)", "raised 24H2+" if host.raised else "legacy",
                 host.workerw)
    return host


# --------------------------------------------------------------------------- #
# Window preparation
# --------------------------------------------------------------------------- #

def _make_borderless(hwnd: int) -> None:
    s = win32.style(hwnd) & ~(win32.WS_CAPTION | win32.WS_THICKFRAME | win32.WS_SYSMENU
                              | win32.WS_MAXIMIZEBOX | win32.WS_MINIMIZEBOX)
    win32.set_style(hwnd, s)
    ex = win32.ex_style(hwnd) & ~(win32.WS_EX_DLGMODALFRAME | win32.WS_EX_COMPOSITED | win32.WS_EX_WINDOWEDGE
                                  | win32.WS_EX_CLIENTEDGE | win32.WS_EX_LAYERED | win32.WS_EX_STATICEDGE
                                  | win32.WS_EX_TOOLWINDOW | win32.WS_EX_APPWINDOW)
    win32.set_ex_style(hwnd, ex)


def _hide_from_taskbar(hwnd: int) -> None:
    # Style changes are cached until the window is re-shown.
    win32.ShowWindow(hwnd, win32.SW_HIDE)
    win32.set_ex_style(hwnd, win32.ex_style(hwnd) | win32.WS_EX_NOACTIVATE | win32.WS_EX_TOOLWINDOW)
    win32.ShowWindow(hwnd, win32.SW_SHOWNA)


def _make_layered(hwnd: int) -> None:
    win32.set_ex_style(hwnd, win32.ex_style(hwnd) | win32.WS_EX_LAYERED)
    win32.SetLayeredWindowAttributes(hwnd, 0, 255, win32.LWA_ALPHA)


def _last_child(parent: int) -> int | None:
    first = win32.GetWindow(parent, win32.GW_CHILD)
    return win32.GetWindow(first, win32.GW_HWNDLAST) if first else None


def _below(upper: int, lower: int, limit: int = 256) -> bool:
    """True if `lower` comes after `upper` among its siblings (i.e. is drawn underneath)."""
    h = win32.GetWindow(upper, win32.GW_HWNDNEXT)
    for _ in range(limit):
        if not h:
            return False
        if h == lower:
            return True
        h = win32.GetWindow(h, win32.GW_HWNDNEXT)
    return False


def _ensure_workerw_at_bottom(host: DesktopHost) -> None:
    if host.raised and _last_child(host.progman) != host.workerw:
        log.info("Restoring WorkerW z-order")
        win32.SetWindowPos(host.workerw, win32.HWND_BOTTOM, 0, 0, 0, 0,
                           win32.SWP_NOMOVE | win32.SWP_NOSIZE | win32.SWP_NOACTIVATE)


def _place_under_icons(hwnd: int, host: DesktopHost) -> None:
    if host.raised and host.defview:
        win32.SetWindowPos(hwnd, host.defview, 0, 0, 0, 0,
                           win32.SWP_NOMOVE | win32.SWP_NOSIZE | win32.SWP_NOACTIVATE)
        _ensure_workerw_at_bottom(host)


def _client_point(host: DesktopHost, x: int, y: int) -> tuple[int, int]:
    """Screen coordinates -> coordinates inside the desktop layer (which spans all monitors)."""
    pt = wt.POINT(x, y)
    win32.MapWindowPoints(None, host.parent, ctypes.byref(pt), 1)
    return pt.x, pt.y


def place(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> None:
    x, y, w, h = rect
    cx, cy = _client_point(host, x, y)
    win32.SetWindowPos(hwnd, None, cx, cy, w, h, win32.SWP_NOACTIVATE | win32.SWP_NOZORDER)


def refresh_wallpaper(host: DesktopHost | None) -> None:
    """Make Explorer repaint the static wallpaper (legacy layout only).

    In the raised layout this would destroy the WorkerW, so it is skipped, as Lively does.
    """
    if host is None or host.raised:
        return
    win32.SystemParametersInfoW(win32.SPI_SETDESKWALLPAPER, 0, None, win32.SPIF_UPDATEINIFILE)


def attach(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> bool:
    """Move a top-level window behind the desktop icons, covering `rect` (screen pixels)."""
    x, y, w, h = rect
    _make_borderless(hwnd)
    _hide_from_taskbar(hwnd)
    win32.SetWindowPos(hwnd, win32.HWND_BOTTOM, x, y, w, h, win32.SWP_NOACTIVATE)

    if host.raised:
        win32.set_style(hwnd, win32.style(hwnd) | win32.WS_CHILD)
        _make_layered(hwnd)  # must happen before SetParent for some renderers
        if not win32.SetParent(hwnd, host.progman):
            log.error("SetParent(Progman) failed: %s", ctypes.get_last_error())
            return False
        _place_under_icons(hwnd, host)
    elif not win32.SetParent(hwnd, host.workerw):
        log.error("SetParent(WorkerW) failed: %s", ctypes.get_last_error())
        return False

    # Players start minimized so they never steal focus; un-minimize without activating.
    win32.ShowWindow(hwnd, win32.SW_SHOWNOACTIVATE)
    place(hwnd, rect, host)
    refresh_wallpaper(host)
    log.info("Attached window %#x to the desktop at %s", hwnd, rect)
    return True


def ensure(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> bool:
    """Check an attached window and repair position/z-order. False means re-create it."""
    if not win32.IsWindow(hwnd) or not host.alive():
        return False
    if win32.GetAncestor(hwnd, win32.GA_PARENT) != host.parent:
        return False
    if win32.window_rect(hwnd) != rect:
        place(hwnd, rect, host)
    if host.raised:
        if host.defview and not _below(host.defview, hwnd):
            log.info("Live window was above the desktop icons; moving it back under them")
            _place_under_icons(hwnd, host)
        elif not _below(hwnd, host.workerw):
            _place_under_icons(hwnd, host)
        _ensure_workerw_at_bottom(host)
    elif not win32.IsWindowVisible(host.workerw):
        win32.ShowWindow(host.workerw, win32.SW_SHOWNA)
    return True
