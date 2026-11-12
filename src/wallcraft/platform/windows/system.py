"""Power, session and window-occlusion state used by the performance rules."""

from __future__ import annotations

import ctypes
import logging

from ...rules import SystemState
from ..base import Monitor
from . import win32

log = logging.getLogger(__name__)

_SHELL_CLASSES = frozenset({
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow", "TopLevelWindowForOverflowXamlIsland",
})


def power_status() -> tuple[bool, bool, int | None, bool]:
    """(has_battery, on_battery, percent, battery_saver)."""
    s = win32.SYSTEM_POWER_STATUS()
    if not win32.GetSystemPowerStatus(ctypes.byref(s)):
        return False, False, None, False
    has_battery = s.BatteryFlag != 128 and s.BatteryFlag != 255
    on_battery = has_battery and s.ACLineStatus == 0
    percent = None if s.BatteryLifePercent == 255 else int(s.BatteryLifePercent)
    saver = s.SystemStatusFlag == 1
    return has_battery, on_battery, percent, saver


def session_locked() -> bool:
    desk = win32.OpenInputDesktop(0, False, win32.DESKTOP_SWITCHDESKTOP)
    if not desk:
        return True
    try:
        return not win32.SwitchDesktop(desk)
    finally:
        win32.CloseDesktop(desk)


def _monitor_lookup(monitors: list[Monitor]) -> dict[str, Monitor]:
    return {m.device: m for m in monitors if m.device}


def occluded_monitors(monitors: list[Monitor]) -> tuple[frozenset[str], frozenset[str]]:
    """Return (fullscreen monitor ids, maximized monitor ids)."""
    by_device = _monitor_lookup(monitors)
    own_pid = win32.GetCurrentProcessId()
    fullscreen: set[str] = set()
    maximized: set[str] = set()

    def monitor_for(hwnd: int) -> Monitor | None:
        hmon = win32.MonitorFromWindow(hwnd, win32.MONITOR_DEFAULTTONULL)
        if not hmon:
            return None
        info = win32.monitor_info(hmon)
        return by_device.get(info.szDevice) if info else None

    for hwnd in win32.enum_windows():
        if not win32.IsWindowVisible(hwnd) or win32.IsIconic(hwnd):
            continue
        if win32.class_name(hwnd) in _SHELL_CLASSES:
            continue
        if win32.window_pid(hwnd) == own_pid or win32.is_cloaked(hwnd):
            continue
        rect = win32.window_rect(hwnd)
        if not rect or rect[2] <= 0 or rect[3] <= 0:
            continue
        mon = monitor_for(hwnd)
        if mon is None:
            continue
        if win32.IsZoomed(hwnd):
            # Maximized frames overhang the monitor edge, so don't also count them as fullscreen.
            maximized.add(mon.id)
            continue
        x, y, w, h = rect
        if x <= mon.x and y <= mon.y and x + w >= mon.x + mon.width and y + h >= mon.y + mon.height:
            fullscreen.add(mon.id)

    # Exclusive-fullscreen games and presentations may not show up as covering windows.
    state = ctypes.c_int()
    if win32.SHQueryUserNotificationState(ctypes.byref(state)) >= 0 and state.value in (
        win32.QUNS_BUSY, win32.QUNS_RUNNING_D3D_FULL_SCREEN, win32.QUNS_PRESENTATION_MODE
    ):
        fg = win32.GetForegroundWindow()
        mon = monitor_for(fg) if fg else None
        if mon:
            fullscreen.add(mon.id)
    return frozenset(fullscreen), frozenset(maximized)


def system_state(monitors: list[Monitor]) -> SystemState:
    has_battery, on_battery, percent, saver = power_status()
    try:
        fullscreen, maximized = occluded_monitors(monitors)
    except OSError as exc:
        log.debug("Occlusion check failed: %s", exc)
        fullscreen, maximized = frozenset(), frozenset()
    return SystemState(
        has_battery=has_battery,
        on_battery=on_battery,
        battery_percent=percent,
        battery_saver=saver,
        session_locked=session_locked(),
        fullscreen_monitors=fullscreen,
        maximized_monitors=maximized,
    )
