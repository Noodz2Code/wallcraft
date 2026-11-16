"""Minimal X11 access through libX11 (ctypes): desktop windows and window-state queries.

Used for live wallpapers on X11 (a window of type _NET_WM_WINDOW_TYPE_DESKTOP that
stays below everything, on every workspace) and for detecting fullscreen and
maximized windows via the EWMH properties window managers publish.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

XA_ATOM = 4
XA_CARDINAL = 6
XA_WINDOW = 33
PROP_MODE_REPLACE = 0
ANY_PROPERTY_TYPE = 0
ALL_DESKTOPS = 0xFFFFFFFF

_ErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


@dataclass(frozen=True)
class ClientWindow:
    window: int
    pid: int
    types: frozenset[str]
    states: frozenset[str]
    desktop: int
    rect: tuple[int, int, int, int]  # root coordinates, physical pixels


class X11:
    def __init__(self) -> None:
        name = ctypes.util.find_library("X11")
        if not name:
            raise OSError("libX11 not found")
        x = ctypes.CDLL(name)
        self._x = x
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetAtomName.restype = ctypes.c_void_p
        x.XGetAtomName.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        x.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long, ctypes.c_int,
            ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p),
        ]
        x.XGetGeometry.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
        ]
        x.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
        ]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XSetErrorHandler.restype = ctypes.c_void_p
        x.XSetErrorHandler.argtypes = [ctypes.c_void_p]

        self._dpy = x.XOpenDisplay(None)
        if not self._dpy:
            raise OSError("Can't open the X display")
        self._root = x.XDefaultRootWindow(self._dpy)
        self._atoms: dict[str, int] = {}
        self._names: dict[int, str] = {}
        # Windows can vanish between listing and querying them. Xlib's default error handler
        # would exit the whole process, so errors are ignored while we talk to the server.
        self._ignore = _ErrorHandler(lambda _d, _e: 0)

    # Helpers ------------------------------------------------------------------- #
    def atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = self._x.XInternAtom(self._dpy, name.encode(), 0)
        return self._atoms[name]

    def atom_name(self, atom: int) -> str:
        if atom not in self._names:
            ptr = self._x.XGetAtomName(self._dpy, atom)
            self._names[atom] = ctypes.string_at(ptr).decode("latin-1") if ptr else ""
            if ptr:
                self._x.XFree(ptr)
        return self._names[atom]

    def _guarded(self, fn):
        previous = self._x.XSetErrorHandler(ctypes.cast(self._ignore, ctypes.c_void_p))
        try:
            return fn()
        finally:
            self._x.XSync(self._dpy, 0)
            self._x.XSetErrorHandler(previous)

    def get_cardinals(self, window: int, prop: str) -> list[int]:
        actual_type, fmt = ctypes.c_ulong(), ctypes.c_int()
        nitems, after, data = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = self._x.XGetWindowProperty(
            self._dpy, window, self.atom(prop), 0, 4096, 0, ANY_PROPERTY_TYPE,
            ctypes.byref(actual_type), ctypes.byref(fmt), ctypes.byref(nitems), ctypes.byref(after),
            ctypes.byref(data))
        if status != 0 or not data.value:
            return []
        try:
            if fmt.value != 32:
                return []
            # 32-bit X properties are returned as C longs (64-bit on 64-bit systems).
            arr = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
            return [arr[i] & 0xFFFFFFFF for i in range(nitems.value)]
        finally:
            self._x.XFree(data)

    def _set_cardinals(self, window: int, prop: str, prop_type: int, values: list[int]) -> None:
        arr = (ctypes.c_ulong * len(values))(*values)
        self._x.XChangeProperty(self._dpy, window, self.atom(prop), prop_type, 32, PROP_MODE_REPLACE,
                                ctypes.cast(arr, ctypes.c_void_p), len(values))

    def window_rect(self, window: int) -> tuple[int, int, int, int] | None:
        root, x, y = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        w, h, border, depth = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        if not self._x.XGetGeometry(self._dpy, window, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y),
                                    ctypes.byref(w), ctypes.byref(h), ctypes.byref(border), ctypes.byref(depth)):
            return None
        rx, ry, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        if not self._x.XTranslateCoordinates(self._dpy, window, self._root, 0, 0, ctypes.byref(rx),
                                             ctypes.byref(ry), ctypes.byref(child)):
            return None
        return (rx.value, ry.value, int(w.value), int(h.value))

    # Public ------------------------------------------------------------------------ #
    def make_desktop_window(self, window: int) -> None:
        """Turn a not-yet-mapped window into a desktop-level window on every workspace."""
        def apply() -> None:
            self._set_cardinals(window, "_NET_WM_WINDOW_TYPE", XA_ATOM,
                                [self.atom("_NET_WM_WINDOW_TYPE_DESKTOP")])
            self._set_cardinals(window, "_NET_WM_STATE", XA_ATOM, [
                self.atom("_NET_WM_STATE_BELOW"), self.atom("_NET_WM_STATE_STICKY"),
                self.atom("_NET_WM_STATE_SKIP_TASKBAR"), self.atom("_NET_WM_STATE_SKIP_PAGER")])
            self._set_cardinals(window, "_NET_WM_DESKTOP", XA_CARDINAL, [ALL_DESKTOPS])
            self._x.XFlush(self._dpy)
        self._guarded(apply)

    def window_exists(self, window: int) -> bool:
        return self._guarded(lambda: self.window_rect(window)) is not None

    def clients(self) -> list[ClientWindow]:
        def collect() -> list[ClientWindow]:
            current = (self.get_cardinals(self._root, "_NET_CURRENT_DESKTOP") or [0])[0]
            result = []
            for win in self.get_cardinals(self._root, "_NET_CLIENT_LIST"):
                desktop = (self.get_cardinals(win, "_NET_WM_DESKTOP") or [current])[0]
                if desktop not in (current, ALL_DESKTOPS):
                    continue  # on another workspace
                rect = self.window_rect(win)
                if rect is None:
                    continue
                result.append(ClientWindow(
                    window=win,
                    pid=(self.get_cardinals(win, "_NET_WM_PID") or [0])[0],
                    types=frozenset(self.atom_name(a) for a in self.get_cardinals(win, "_NET_WM_WINDOW_TYPE")),
                    states=frozenset(self.atom_name(a) for a in self.get_cardinals(win, "_NET_WM_STATE")),
                    desktop=desktop,
                    rect=rect,
                ))
            return result
        return self._guarded(collect)


def occluded_monitors(x11: X11, monitors) -> tuple[frozenset[str], frozenset[str]]:
    """(fullscreen monitor ids, maximized monitor ids) on the current workspace."""
    own = os.getpid()
    fullscreen: set[str] = set()
    maximized: set[str] = set()
    for c in x11.clients():
        if c.pid == own or "_NET_WM_STATE_HIDDEN" in c.states:
            continue
        if c.types & {"_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK"}:
            continue
        x, y, w, h = c.rect
        cx, cy = x + w // 2, y + h // 2
        mon = next((m for m in monitors if m.x <= cx < m.x + m.width and m.y <= cy < m.y + m.height), None)
        if mon is None:
            continue
        if "_NET_WM_STATE_FULLSCREEN" in c.states:
            fullscreen.add(mon.id)
        elif {"_NET_WM_STATE_MAXIMIZED_VERT", "_NET_WM_STATE_MAXIMIZED_HORZ"} <= c.states:
            maximized.add(mon.id)
    return frozenset(fullscreen), frozenset(maximized)
