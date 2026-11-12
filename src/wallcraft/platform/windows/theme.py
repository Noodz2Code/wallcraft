"""Read and change the Windows light/dark mode."""

from __future__ import annotations

import logging
import winreg

from . import win32

log = logging.getLogger(__name__)

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _read(name: str, default: int = 1) -> int:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return int(value)
    except (OSError, ValueError):
        return default


def apps_use_light_theme() -> bool:
    return _read("AppsUseLightTheme") != 0


def system_uses_light_theme() -> bool:
    return _read("SystemUsesLightTheme") != 0


def set_theme(apps_light: bool | None, system_light: bool | None) -> None:
    changed = False
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
        if apps_light is not None and apps_light != apps_use_light_theme():
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, int(apps_light))
            changed = True
        if system_light is not None and system_light != system_uses_light_theme():
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, int(system_light))
            changed = True
    if changed:
        log.info("Windows theme set: apps_light=%s system_light=%s", apps_light, system_light)
        win32.broadcast_setting_change("ImmersiveColorSet")
