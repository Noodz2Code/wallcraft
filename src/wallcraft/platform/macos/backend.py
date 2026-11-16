"""macOS implementation of the platform Backend (experimental; needs PyObjC).

* Static wallpaper: NSWorkspace.setDesktopImageURL. macOS applies it to the *current
  Space* only; there is no public API for all Spaces at once.
* Live wallpaper: a borderless Qt window raised to the desktop window level (below the
  Finder's icons), shown on every Space and ignoring the mouse, the same idea Plash uses.
* Dark mode: read from user defaults, switched through System Events (macOS asks the
  user once to allow Wallcraft to control System Events).
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import AppKit  # noqa: N813 - PyObjC module names
import Foundation
import objc
import Quartz

from ... import APP_ID
from ...config import FitMode
from ...rules import SystemState
from ..base import Backend, Monitor, qt_monitors
from ..images import prepare_image
from .pmset import parse_pmset

log = logging.getLogger(__name__)

NATIVE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".bmp", ".webp", ".gif"})
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / f"io.github.{APP_ID}.plist"

# (scaling, allow clipping)
_SCALING = {
    FitMode.FILL: (AppKit.NSImageScaleProportionallyUpOrDown, True),
    FitMode.SPAN: (AppKit.NSImageScaleProportionallyUpOrDown, True),
    FitMode.FIT: (AppKit.NSImageScaleProportionallyUpOrDown, False),
    FitMode.TILE: (AppKit.NSImageScaleProportionallyUpOrDown, False),
    FitMode.STRETCH: (AppKit.NSImageScaleAxesIndependently, False),
    FitMode.CENTER: (AppKit.NSImageScaleNone, False),
}


class MacBackend(Backend):
    name = "macos"
    supports_desktop_embedding = True
    supports_per_monitor = True
    supports_os_theme_write = True
    supports_autostart = True

    @property
    def live_strategy(self) -> str:
        return "surface"

    # Monitors / wallpaper ---------------------------------------------------------- #
    def list_monitors(self) -> list[Monitor]:
        return qt_monitors()

    def _screens(self, monitor_id: str | None):
        screens = list(AppKit.NSScreen.screens() or [])
        if monitor_id is None:
            return screens
        for s in screens:
            name = s.localizedName() if s.respondsToSelector_("localizedName") else ""
            if name == monitor_id:
                return [s]
        ids = [m.id for m in qt_monitors()]
        idx = ids.index(monitor_id) if monitor_id in ids else -1
        return [screens[idx]] if 0 <= idx < len(screens) else screens

    def set_static_wallpaper(self, path: str, fit: FitMode, monitor_id: str | None = None) -> None:
        url = Foundation.NSURL.fileURLWithPath_(prepare_image(path, NATIVE_EXTS))
        scaling, clip = _SCALING[fit]
        options = {
            AppKit.NSWorkspaceDesktopImageScalingKey: scaling,
            AppKit.NSWorkspaceDesktopImageAllowClippingKey: clip,
            AppKit.NSWorkspaceDesktopImageFillColorKey: AppKit.NSColor.blackColor(),
        }
        ws = AppKit.NSWorkspace.sharedWorkspace()
        for screen in self._screens(monitor_id):
            ok, error = ws.setDesktopImageURL_forScreen_options_error_(url, screen, options, None)
            if not ok:
                raise OSError(f"macOS refused the wallpaper: {error}")

    # Theme ---------------------------------------------------------------------------- #
    def os_theme(self) -> str:
        style = Foundation.NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        return "dark" if style and str(style).lower() == "dark" else "light"

    def set_os_theme(self, apps_light: bool | None, system_light: bool | None) -> None:
        light = apps_light if apps_light is not None else system_light
        if light is None:
            return
        script = ('tell application "System Events" to tell appearance preferences to set dark mode to '
                  + ("false" if light else "true"))
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            raise OSError("macOS didn't allow the theme change. Allow Wallcraft to control System Events in "
                          f"System Settings → Privacy & Security → Automation. ({proc.stderr.strip()[:120]})")

    # System state ----------------------------------------------------------------------- #
    def system_state(self, monitors: list[Monitor]) -> SystemState:
        try:
            out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        has_battery, on_battery, percent = parse_pmset(out)
        info = Foundation.NSProcessInfo.processInfo()
        low_power = bool(info.isLowPowerModeEnabled()) if info.respondsToSelector_("isLowPowerModeEnabled") else False
        session = Quartz.CGSessionCopyCurrentDictionary() or {}
        locked = bool(session.get("CGSSessionScreenIsLocked", False))
        fullscreen, maximized = self._occluded(monitors)
        return SystemState(has_battery=has_battery, on_battery=on_battery, battery_percent=percent,
                           battery_saver=low_power, session_locked=locked,
                           fullscreen_monitors=fullscreen, maximized_monitors=maximized)

    def _occluded(self, monitors: list[Monitor]) -> tuple[frozenset[str], frozenset[str]]:
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
        own = os.getpid()
        fullscreen: set[str] = set()
        maximized: set[str] = set()
        for w in windows:
            if w.get("kCGWindowLayer", 1) != 0 or w.get("kCGWindowOwnerPID") == own:
                continue
            b = w.get("kCGWindowBounds") or {}
            x, y, width, height = (float(b.get(k, 0)) for k in ("X", "Y", "Width", "Height"))
            cx, cy = x + width / 2, y + height / 2
            for m in monitors:
                mx, my, mw, mh = m.logical or m.rect
                if not (mx <= cx < mx + mw and my <= cy < my + mh):
                    continue
                if x <= mx and y <= my and width >= mw and height >= mh:
                    fullscreen.add(m.id)
                elif width >= mw * 0.95 and height >= mh * 0.85:
                    maximized.add(m.id)
                break
        return frozenset(fullscreen), frozenset(maximized)

    # Live wallpaper windows ---------------------------------------------------------------- #
    def _ns_window(self, view_ptr: int):
        view = objc.objc_object(c_void_p=view_ptr)
        return view.window() if view is not None else None

    def _make_desktop_level(self, window) -> None:
        window.setLevel_(Quartz.CGWindowLevelForKey(Quartz.kCGDesktopWindowLevelKey))
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
        window.setIgnoresMouseEvents_(True)
        window.setHasShadow_(False)
        if window.respondsToSelector_("setHidesOnDeactivate:"):
            window.setHidesOnDeactivate_(False)

    def attach_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        window = self._ns_window(hwnd)
        if window is not None:
            self._make_desktop_level(window)
        return True  # if the NSWindow doesn't exist yet, ensure_live_window applies it after showing

    def ensure_live_window(self, hwnd: int, monitor: Monitor) -> bool:
        window = self._ns_window(hwnd)
        if window is None:
            return False
        desktop_level = Quartz.CGWindowLevelForKey(Quartz.kCGDesktopWindowLevelKey)
        if window.level() != desktop_level:
            self._make_desktop_level(window)
        return True

    # Misc -------------------------------------------------------------------------------------- #
    def autostart_enabled(self) -> bool:
        return LAUNCH_AGENT.is_file()

    def set_autostart(self, enabled: bool) -> None:
        if not enabled:
            LAUNCH_AGENT.unlink(missing_ok=True)
            return
        args = [sys.executable, "--autostart"] if getattr(sys, "frozen", False) \
            else [sys.executable, "-m", "wallcraft", "--autostart"]
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as fh:
            plistlib.dump({"Label": f"io.github.{APP_ID}", "ProgramArguments": args, "RunAtLoad": True}, fh)

    def reveal_in_file_manager(self, path: str) -> None:
        subprocess.Popen(["open", "-R", path])  # noqa: S603, S607
