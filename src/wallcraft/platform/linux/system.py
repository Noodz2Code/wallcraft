"""Battery, power-saver and screen-lock state on Linux.

Battery comes straight from /sys/class/power_supply (no daemon needed). Power saver
and the lock screen come from the standard D-Bus services (power-profiles-daemon,
systemd-logind, org.freedesktop.ScreenSaver); each is optional.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

POWER_SUPPLY = Path("/sys/class/power_supply")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def battery_status(root: Path = POWER_SUPPLY) -> tuple[bool, bool, int | None]:
    """(has_battery, on_battery, percent)."""
    try:
        supplies = list(root.iterdir())
    except OSError:
        return False, False, None
    mains_online: list[bool] = []
    batteries: list[tuple[int | None, str]] = []
    for s in supplies:
        kind = _read(s / "type")
        if kind == "Mains":
            mains_online.append(_read(s / "online") == "1")
        elif kind == "Battery" and _read(s / "scope") != "Device":  # skip mice, headsets…
            cap = _read(s / "capacity")
            batteries.append((int(cap) if cap.isdigit() else None, _read(s / "status")))
    if not batteries:
        return False, False, None
    if mains_online:
        on_battery = not any(mains_online)
    else:
        on_battery = all(status == "Discharging" for _cap, status in batteries)
    caps = [c for c, _s in batteries if c is not None]
    return True, on_battery, (round(sum(caps) / len(caps)) if caps else None)


def _dbus_property(bus: str, service: str, path: str, interface: str, name: str):
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:
        return None
    conn = QDBusConnection.systemBus() if bus == "system" else QDBusConnection.sessionBus()
    if not conn.isConnected():
        return None
    iface = QDBusInterface(service, path, interface, conn)
    if not iface.isValid():
        return None
    return iface.property(name)


def power_saver_on() -> bool:
    for service, path in (("org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles"),
                          ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")):
        profile = _dbus_property("system", service, path, service, "ActiveProfile")
        if profile:
            return str(profile) == "power-saver"
    return False


def session_locked() -> bool:
    hint = _dbus_property("system", "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                          "org.freedesktop.login1.Session", "LockedHint")
    if hint:
        return True
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:
        return False
    iface = QDBusInterface("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                           "org.freedesktop.ScreenSaver", QDBusConnection.sessionBus())
    if not iface.isValid():
        return False
    reply = iface.call("GetActive")
    args = reply.arguments()
    return bool(args and args[0])
