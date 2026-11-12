"""Embedding windows behind the desktop icons (the "WorkerW" technique).

Sending the undocumented message 0x052C to Progman makes Explorer create a
WorkerW window that sits between the wallpaper and the icon layer. Child
windows of that WorkerW draw over the wallpaper but under the icons.

Two desktop layouts exist:
  * Legacy (Windows 10, Windows 11 before 24H2): the WorkerW is a top-level
    window that follows the window hosting SHELLDLL_DefView.
  * Raised (Windows 11 24H2+): SHELLDLL_DefView and WorkerW are both children
    of Progman. Our window is parented to Progman, placed below the icon view
    and above WorkerW, and must be layered to be composited.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes as wt
from dataclasses import dataclass

from . import win32

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DesktopHost:
    parent: int
    defview: int | None
    workerw: int | None
    raised: bool

    def alive(self) -> bool:
        return bool(win32.IsWindow(self.parent))


def find_desktop_host() -> DesktopHost | None:
    progman = win32.FindWindowW("Progman", None)
    if not progman:
        log.warning("Progman window not found; is Explorer running?")
        return None

    result = ctypes.c_size_t()
    win32.SendMessageTimeoutW(progman, win32.WM_SPAWN_WORKER, 0xD, 0x1, win32.SMTO_NORMAL, 1000,
                              ctypes.byref(result))
    win32.SendMessageTimeoutW(progman, win32.WM_SPAWN_WORKER, 0, 0, win32.SMTO_NORMAL, 1000,
                              ctypes.byref(result))

    defview = win32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    workerw = win32.FindWindowExW(progman, None, "WorkerW", None)
    if defview and workerw:
        log.info("Desktop layout: raised (Windows 11 24H2+)")
        return DesktopHost(parent=progman, defview=defview, workerw=workerw, raised=True)

    found: list[int] = []
    for hwnd in win32.enum_windows():
        if win32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            sibling = win32.FindWindowExW(None, hwnd, "WorkerW", None)
            if sibling:
                found.append(sibling)
                break
    if found:
        log.info("Desktop layout: legacy WorkerW")
        return DesktopHost(parent=found[0], defview=None, workerw=found[0], raised=False)

    log.warning("WorkerW not found; falling back to Progman as parent")
    return DesktopHost(parent=progman, defview=defview, workerw=None, raised=False)


def _client_origin(parent: int, x: int, y: int) -> tuple[int, int]:
    pt = wt.POINT(x, y)
    win32.MapWindowPoints(None, parent, ctypes.byref(pt), 1)
    return pt.x, pt.y


def place(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> None:
    x, y, w, h = rect
    cx, cy = _client_origin(host.parent, x, y)
    insert_after = host.defview if host.defview else None
    flags = win32.SWP_NOACTIVATE | (0 if insert_after else win32.SWP_NOZORDER)
    win32.SetWindowPos(hwnd, insert_after, cx, cy, w, h, flags)
    if host.raised and host.workerw:
        # Keep the wallpaper-painting WorkerW underneath us.
        win32.SetWindowPos(host.workerw, hwnd, 0, 0, 0, 0,
                           win32.SWP_NOMOVE | win32.SWP_NOSIZE | win32.SWP_NOACTIVATE)


def attach(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> bool:
    style = win32.GetWindowLongPtrW(hwnd, win32.GWL_STYLE) & 0xFFFFFFFF
    style &= ~(win32.WS_POPUP | win32.WS_CAPTION | win32.WS_THICKFRAME | win32.WS_SYSMENU
               | win32.WS_MAXIMIZEBOX | win32.WS_MINIMIZEBOX)
    style |= win32.WS_CHILD
    win32.SetWindowLongPtrW(hwnd, win32.GWL_STYLE, ctypes.c_ssize_t(style).value)

    ex = win32.GetWindowLongPtrW(hwnd, win32.GWL_EXSTYLE) & 0xFFFFFFFF
    ex = (ex & ~win32.WS_EX_APPWINDOW) | win32.WS_EX_NOACTIVATE
    if host.raised:
        ex |= win32.WS_EX_LAYERED
    win32.SetWindowLongPtrW(hwnd, win32.GWL_EXSTYLE, ctypes.c_ssize_t(ex).value)
    if host.raised:
        win32.SetLayeredWindowAttributes(hwnd, 0, 255, win32.LWA_ALPHA)

    if not win32.SetParent(hwnd, host.parent):
        log.error("SetParent failed: %s", ctypes.get_last_error())
        return False
    place(hwnd, rect, host)
    return True


def ensure(hwnd: int, rect: tuple[int, int, int, int], host: DesktopHost) -> bool:
    """Verify the window is still embedded and correctly positioned."""
    if not win32.IsWindow(hwnd) or not host.alive():
        return False
    if win32.GetAncestor(hwnd, win32.GA_PARENT) != host.parent:
        return False
    if win32.window_rect(hwnd) != rect:
        place(hwnd, rect, host)
    if not host.raised and not win32.IsWindowVisible(host.parent):
        # Explorer can hide the WorkerW after a wallpaper change; show it again.
        win32.ShowWindow(host.parent, win32.SW_SHOWNA)
    return True


def redraw(host: DesktopHost | None) -> None:
    if host and host.alive():
        win32.RedrawWindow(host.parent, None, None,
                           win32.RDW_INVALIDATE | win32.RDW_ERASE | win32.RDW_ALLCHILDREN | win32.RDW_UPDATENOW)
