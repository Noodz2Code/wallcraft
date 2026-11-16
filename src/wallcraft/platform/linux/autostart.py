"""Start at login on Linux: a standard XDG autostart entry (works on every desktop)."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from ... import APP_NAME

AUTOSTART_FLAG = "--autostart"


def autostart_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "wallcraft.desktop"


def launch_command() -> str:
    appimage = os.environ.get("APPIMAGE")  # set by the AppImage runtime
    if appimage:
        return f"{shlex.quote(appimage)} {AUTOSTART_FLAG}"
    if getattr(sys, "frozen", False):
        return f"{shlex.quote(sys.executable)} {AUTOSTART_FLAG}"
    return f"{shlex.quote(sys.executable)} -m wallcraft {AUTOSTART_FLAG}"


def is_enabled() -> bool:
    return autostart_file().is_file()


def set_enabled(enabled: bool) -> None:
    path = autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Wallpaper manager\n"
        f"Exec={launch_command()}\n"
        "Icon=wallcraft\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
