"""Select the backend for the current operating system."""

from __future__ import annotations

import sys

from .base import Backend, Monitor

__all__ = ["Backend", "Monitor", "create_backend"]


def create_backend() -> Backend:
    if sys.platform == "win32":
        from .windows.backend import WindowsBackend

        return WindowsBackend()
    from .dev import DevBackend

    return DevBackend()
