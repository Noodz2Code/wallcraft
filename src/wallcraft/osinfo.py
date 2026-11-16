"""How to refer to the user's operating system in the interface."""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Used at the start of sentences: "Windows is in dark mode", "Your desktop is in dark mode".
SYSTEM_NAME = "Windows" if IS_WINDOWS else "macOS" if IS_MAC else "Your desktop"
