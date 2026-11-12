"""Start-with-Windows via the per-user Run registry key (no admin rights needed)."""

from __future__ import annotations

import os
import sys
import winreg

from ... import APP_NAME

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_FLAG = "--autostart"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_FLAG}'
    # Running from source: prefer pythonw.exe so no console window appears.
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    return f'"{exe}" -m wallcraft {AUTOSTART_FLAG}'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
