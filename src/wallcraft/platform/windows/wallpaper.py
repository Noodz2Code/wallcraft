"""Static wallpaper control via the IDesktopWallpaper COM interface (Windows 8+).

Called through raw ctypes vtable access so there is no comtypes/pywin32 dependency.
Falls back to SystemParametersInfo (all monitors only) if COM is unavailable.
"""

from __future__ import annotations

import ctypes
import logging
import winreg
from ctypes import wintypes as wt
from dataclasses import dataclass

from ...config import FitMode
from . import win32

log = logging.getLogger(__name__)

CLSID_DesktopWallpaper = "{C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD}"
IID_IDesktopWallpaper = "{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}"

# DESKTOP_WALLPAPER_POSITION
_POSITION = {
    FitMode.CENTER: 0,
    FitMode.TILE: 1,
    FitMode.STRETCH: 2,
    FitMode.FIT: 3,
    FitMode.FILL: 4,
    FitMode.SPAN: 5,
}

# Registry values used by the SystemParametersInfo fallback: (WallpaperStyle, TileWallpaper)
_REG_STYLE = {
    FitMode.FILL: ("10", "0"),
    FitMode.FIT: ("6", "0"),
    FitMode.STRETCH: ("2", "0"),
    FitMode.TILE: ("0", "1"),
    FitMode.CENTER: ("0", "0"),
    FitMode.SPAN: ("22", "0"),
}

# vtable indices (IUnknown occupies 0-2)
_RELEASE = 2
_SET_WALLPAPER = 3
_GET_WALLPAPER = 4
_GET_MONITOR_PATH_AT = 5
_GET_MONITOR_COUNT = 6
_GET_MONITOR_RECT = 7
_SET_POSITION = 10


class ComError(OSError):
    pass


@dataclass(frozen=True)
class ComMonitor:
    path: str
    rect: tuple[int, int, int, int]


class DesktopWallpaper:
    """Thin wrapper; use as a context manager so the COM object is released."""

    def __init__(self) -> None:
        win32.co_initialize()
        self._ptr = ctypes.c_void_p()
        hr = win32.CoCreateInstance(
            ctypes.byref(win32.GUID.from_string(CLSID_DesktopWallpaper)), None, win32.CLSCTX_ALL,
            ctypes.byref(win32.GUID.from_string(IID_IDesktopWallpaper)), ctypes.byref(self._ptr),
        )
        if hr < 0 or not self._ptr:
            raise ComError(f"CoCreateInstance(DesktopWallpaper) failed: 0x{hr & 0xFFFFFFFF:08X}")

    def __enter__(self) -> DesktopWallpaper:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._ptr:
            self._method(_RELEASE, ctypes.c_ulong)(self._ptr)
            self._ptr = ctypes.c_void_p()

    def _method(self, index: int, restype, *argtypes):
        vtable = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(vtable[index])

    def _call(self, index: int, *args_and_types) -> None:
        argtypes = args_and_types[1::2]
        args = args_and_types[0::2]
        hr = self._method(index, win32.HRESULT_T, *argtypes)(self._ptr, *args)
        if hr < 0:
            raise ComError(f"IDesktopWallpaper method {index} failed: 0x{hr & 0xFFFFFFFF:08X}")

    def set_wallpaper(self, monitor_id: str | None, path: str) -> None:
        self._call(_SET_WALLPAPER, monitor_id, wt.LPCWSTR, path, wt.LPCWSTR)

    def get_wallpaper(self, monitor_id: str | None) -> str:
        out = ctypes.c_void_p()
        self._call(_GET_WALLPAPER, monitor_id, wt.LPCWSTR, ctypes.byref(out), ctypes.POINTER(ctypes.c_void_p))
        try:
            return ctypes.wstring_at(out.value) if out.value else ""
        finally:
            win32.CoTaskMemFree(out)

    def set_position(self, fit: FitMode) -> None:
        self._call(_SET_POSITION, _POSITION[fit], ctypes.c_int)

    def monitors(self) -> list[ComMonitor]:
        count = ctypes.c_uint()
        self._call(_GET_MONITOR_COUNT, ctypes.byref(count), ctypes.POINTER(ctypes.c_uint))
        result = []
        for i in range(count.value):
            out = ctypes.c_void_p()
            try:
                self._call(_GET_MONITOR_PATH_AT, i, ctypes.c_uint, ctypes.byref(out),
                           ctypes.POINTER(ctypes.c_void_p))
            except ComError:
                continue
            try:
                path = ctypes.wstring_at(out.value) if out.value else ""
            finally:
                win32.CoTaskMemFree(out)
            if not path:
                continue
            r = wt.RECT()
            try:
                # Fails for monitors that are remembered but not currently attached.
                self._call(_GET_MONITOR_RECT, path, wt.LPCWSTR, ctypes.byref(r), ctypes.POINTER(wt.RECT))
            except ComError:
                continue
            rect = (r.left, r.top, r.right - r.left, r.bottom - r.top)
            if rect[2] > 0 and rect[3] > 0:
                result.append(ComMonitor(path, rect))
        return result


def com_monitors() -> list[ComMonitor]:
    try:
        with DesktopWallpaper() as dw:
            return dw.monitors()
    except OSError as exc:
        log.debug("IDesktopWallpaper unavailable for monitor listing: %s", exc)
        return []


def set_wallpaper(path: str, fit: FitMode, monitor_id: str | None) -> None:
    try:
        with DesktopWallpaper() as dw:
            dw.set_position(fit)
            dw.set_wallpaper(monitor_id, path)
            return
    except OSError as exc:
        log.warning("IDesktopWallpaper failed (%s); falling back to SystemParametersInfo", exc)
    _spi_set(path, fit)


def get_wallpaper(monitor_id: str | None) -> str | None:
    try:
        with DesktopWallpaper() as dw:
            return dw.get_wallpaper(monitor_id) or None
    except OSError:
        pass
    buf = ctypes.create_unicode_buffer(1024)
    if win32.SystemParametersInfoW(win32.SPI_GETDESKWALLPAPER, len(buf), buf, 0):
        return buf.value or None
    return None


def _spi_set(path: str, fit: FitMode) -> None:
    style, tile = _REG_STYLE[fit]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style)
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile)
    buf = ctypes.create_unicode_buffer(path)
    if not win32.SystemParametersInfoW(
        win32.SPI_SETDESKWALLPAPER, 0, buf, win32.SPIF_UPDATEINIFILE | win32.SPIF_SENDCHANGE
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def set_jpeg_import_quality(full: bool) -> None:
    """Windows re-encodes JPEG wallpapers at ~85% quality unless this value is 100."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0,
                        winreg.KEY_SET_VALUE) as key:
        if full:
            winreg.SetValueEx(key, "JPEGImportQuality", 0, winreg.REG_DWORD, 100)
        else:
            try:
                winreg.DeleteValue(key, "JPEGImportQuality")
            except FileNotFoundError:
                pass
