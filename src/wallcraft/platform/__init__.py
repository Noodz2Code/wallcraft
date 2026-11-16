"""Select the backend for the current operating system."""

from __future__ import annotations

import logging
import sys

from .base import Backend, Monitor

__all__ = ["Backend", "Monitor", "create_backend"]


def create_backend() -> Backend:
    if sys.platform == "win32":
        from .windows.backend import WindowsBackend

        return WindowsBackend()
    if sys.platform.startswith("linux"):
        from .linux.backend import LinuxBackend

        return LinuxBackend()
    if sys.platform == "darwin":
        try:
            from .macos.backend import MacBackend

            return MacBackend()
        except ImportError as exc:  # PyObjC missing when running from source
            logging.getLogger(__name__).warning("macOS support needs PyObjC (%s); using the basic backend", exc)
    from .dev import DevBackend

    return DevBackend()
