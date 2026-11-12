"""Filesystem locations used by Wallcraft.

Default locations on Windows:
    config:  %APPDATA%\\Wallcraft\\config.json
    cache:   %LOCALAPPDATA%\\Wallcraft\\cache
    logs:    %LOCALAPPDATA%\\Wallcraft\\logs

Portable mode: if a folder named ``wallcraft-data`` sits next to the executable,
everything is stored there instead. ``WALLCRAFT_HOME`` overrides both.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME

PORTABLE_DIR_NAME = "wallcraft-data"


def _override_home() -> Path | None:
    env = os.environ.get("WALLCRAFT_HOME")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent / PORTABLE_DIR_NAME
        if portable.is_dir():
            return portable
    return None


def is_portable() -> bool:
    return _override_home() is not None


def config_dir() -> Path:
    home = _override_home()
    if home:
        return home
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME


def data_dir() -> Path:
    home = _override_home()
    if home:
        return home
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / APP_NAME


def cache_dir() -> Path:
    return data_dir() / "cache"


def thumbnail_dir() -> Path:
    return cache_dir() / "thumbnails"


def poster_dir() -> Path:
    return cache_dir() / "posters"


def converted_dir() -> Path:
    return cache_dir() / "converted"


def log_dir() -> Path:
    return data_dir() / "logs"


def config_file() -> Path:
    return config_dir() / "config.json"


def ensure_dirs() -> None:
    for d in (config_dir(), thumbnail_dir(), poster_dir(), converted_dir(), log_dir()):
        d.mkdir(parents=True, exist_ok=True)


def resource(name: str) -> Path:
    """Path to a bundled resource. Works from source and inside a PyInstaller build."""
    return Path(__file__).resolve().parent / "resources" / name
