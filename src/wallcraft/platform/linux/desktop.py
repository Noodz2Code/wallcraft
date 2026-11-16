"""Static wallpaper and light/dark theme for the common Linux desktops.

Every desktop environment stores its wallpaper differently, so each gets a small
adapter that drives the desktop's own tool (gsettings, xfconf-query, Plasma's
scripting interface, swaymsg…). All commands go through ``Runner`` so tests can
check them without touching the real desktop.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from ...config import FitMode

log = logging.getLogger(__name__)

GNOME_LIKE = ("gnome", "budgie")


def desktop_family(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    names = (env.get("XDG_CURRENT_DESKTOP", "") + ":" + env.get("DESKTOP_SESSION", "")).lower()
    tokens = set(filter(None, re.split(r"[:;,\s]+", names)))
    for family, keys in (
        ("kde", {"kde", "plasma", "plasmawayland"}),
        ("xfce", {"xfce", "xubuntu"}),
        ("cinnamon", {"x-cinnamon", "cinnamon"}),
        ("mate", {"mate"}),
        ("lxqt", {"lxqt", "lubuntu"}),
        ("budgie", {"budgie", "budgie-desktop"}),
        ("sway", {"sway"}),
        ("hyprland", {"hyprland"}),
        ("gnome", {"gnome", "ubuntu", "unity", "pop", "gnome-xorg", "gnome-classic"}),
    ):
        if tokens & keys:
            return family
    return "unknown"


def session_type(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    kind = env.get("XDG_SESSION_TYPE", "").lower()
    if kind in ("x11", "wayland"):
        return kind
    return "wayland" if env.get("WAYLAND_DISPLAY") else "x11"


class Runner:
    """Runs desktop commands. Tests replace this with a recorder."""

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, cmd: list[str], check: bool = True) -> str:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError(f"{cmd[0]} failed: {exc}") from exc
        if check and proc.returncode != 0:
            raise OSError(f"{cmd[0]} failed: {(proc.stderr or proc.stdout).strip()[:200]}")
        return proc.stdout


def _require(runner: Runner, tool: str) -> str:
    exe = runner.which(tool)
    if not exe:
        raise OSError(f"'{tool}' is needed to change the wallpaper on this desktop but wasn't found.")
    return exe


# --------------------------------------------------------------------------- #
# Static wallpaper
# --------------------------------------------------------------------------- #

GNOME_OPTIONS = {FitMode.FILL: "zoom", FitMode.FIT: "scaled", FitMode.STRETCH: "stretched",
                 FitMode.CENTER: "centered", FitMode.TILE: "wallpaper", FitMode.SPAN: "spanned"}
XFCE_STYLES = {FitMode.CENTER: 1, FitMode.TILE: 2, FitMode.STRETCH: 3, FitMode.FIT: 4, FitMode.FILL: 5,
               FitMode.SPAN: 6}
KDE_FILL = {FitMode.STRETCH: 0, FitMode.FIT: 1, FitMode.FILL: 2, FitMode.TILE: 3, FitMode.CENTER: 6,
            FitMode.SPAN: 2}
LXQT_MODES = {FitMode.STRETCH: "stretch", FitMode.FIT: "fit", FitMode.FILL: "zoom", FitMode.CENTER: "center",
              FitMode.TILE: "tile", FitMode.SPAN: "zoom"}
SWAY_MODES = {FitMode.STRETCH: "stretch", FitMode.FIT: "fit", FitMode.FILL: "fill", FitMode.CENTER: "center",
              FitMode.TILE: "tile", FitMode.SPAN: "fill"}
FEH_MODES = {FitMode.STRETCH: "--bg-scale", FitMode.FIT: "--bg-max", FitMode.FILL: "--bg-fill",
             FitMode.CENTER: "--bg-center", FitMode.TILE: "--bg-tile", FitMode.SPAN: "--bg-fill"}


def set_wallpaper(runner: Runner, family: str, path: str, fit: FitMode, monitor: str | None,
                  all_monitors: Iterable[str] = (), plasma_script=None) -> None:
    """Set the static wallpaper. ``monitor`` is a connector name (eDP-1) or None for all."""
    uri = Path(path).resolve().as_uri()
    if family in GNOME_LIKE:
        gs = _require(runner, "gsettings")
        for key in ("picture-uri", "picture-uri-dark"):
            runner.run([gs, "set", "org.gnome.desktop.background", key, uri], check=key == "picture-uri")
        runner.run([gs, "set", "org.gnome.desktop.background", "picture-options", GNOME_OPTIONS[fit]])
    elif family == "cinnamon":
        gs = _require(runner, "gsettings")
        runner.run([gs, "set", "org.cinnamon.desktop.background", "picture-uri", uri])
        runner.run([gs, "set", "org.cinnamon.desktop.background", "picture-options", GNOME_OPTIONS[fit]])
    elif family == "mate":
        gs = _require(runner, "gsettings")
        runner.run([gs, "set", "org.mate.background", "picture-filename", path])
        runner.run([gs, "set", "org.mate.background", "picture-options", GNOME_OPTIONS[fit]])
    elif family == "xfce":
        _set_xfce(runner, path, fit, monitor, all_monitors)
    elif family == "kde":
        (plasma_script or _plasma_script)(_kde_script(path, fit))
    elif family == "lxqt":
        exe = _require(runner, "pcmanfm-qt")
        runner.run([exe, f"--set-wallpaper={path}", f"--wallpaper-mode={LXQT_MODES[fit]}"])
    elif family == "sway":
        exe = _require(runner, "swaymsg")
        runner.run([exe, "output", monitor or "*", "bg", path, SWAY_MODES[fit]])
    elif family == "hyprland":
        exe = _require(runner, "hyprctl")
        runner.run([exe, "hyprpaper", "preload", path])
        runner.run([exe, "hyprpaper", "wallpaper", f"{monitor or ''},{path}"])
    elif runner.which("feh"):
        runner.run([runner.which("feh"), FEH_MODES[fit], path])
    else:
        raise OSError("Wallcraft doesn't know how to set the wallpaper on this desktop yet "
                      f"(XDG_CURRENT_DESKTOP={os.environ.get('XDG_CURRENT_DESKTOP', 'unset')}). "
                      "Installing 'feh' works on most X11 window managers.")


def _set_xfce(runner: Runner, path: str, fit: FitMode, monitor: str | None, all_monitors: Iterable[str]) -> None:
    q = _require(runner, "xfconf-query")
    props = runner.run([q, "-c", "xfce4-desktop", "-l"], check=False).split()
    existing = sorted({m.group(1) for p in props if (m := re.match(r"/backdrop/screen0/(monitor[^/]+)/", p))})
    if monitor:
        monitors = [f"monitor{monitor}"]
    else:
        monitors = sorted(set(existing) | {f"monitor{m}" for m in all_monitors})
    try:
        count = int(runner.run([q, "-c", "xfwm4", "-p", "/general/workspace_count"], check=False).strip() or 4)
    except ValueError:
        count = 4
    for mon in monitors:
        workspaces = {f"workspace{i}" for i in range(max(1, count))}
        workspaces |= {m.group(1) for p in props if (m := re.match(rf"/backdrop/screen0/{re.escape(mon)}/(workspace\d+)/", p))}
        for ws in sorted(workspaces):
            base = f"/backdrop/screen0/{mon}/{ws}"
            runner.run([q, "-c", "xfce4-desktop", "-p", f"{base}/last-image", "-n", "-t", "string", "-s", path])
            runner.run([q, "-c", "xfce4-desktop", "-p", f"{base}/image-style", "-n", "-t", "int",
                        "-s", str(XFCE_STYLES[fit])])


def _kde_script(path: str, fit: FitMode) -> str:
    uri = json.dumps(Path(path).resolve().as_uri())
    return (
        "var all = desktops();\n"
        "for (var i = 0; i < all.length; i++) {\n"
        "  var d = all[i];\n"
        '  d.wallpaperPlugin = "org.kde.image";\n'
        '  d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];\n'
        f'  d.writeConfig("Image", {uri});\n'
        f'  d.writeConfig("FillMode", {KDE_FILL[fit]});\n'
        "}\n"
    )


def _plasma_script(script: str) -> None:
    from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

    iface = QDBusInterface("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell",
                           QDBusConnection.sessionBus())
    reply = iface.call("evaluateScript", script)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise OSError(f"Plasma refused the wallpaper change: {reply.errorMessage()}")


# --------------------------------------------------------------------------- #
# Light / dark theme
# --------------------------------------------------------------------------- #

def theme_dirs() -> list[Path]:
    home = Path.home()
    return [Path("/usr/share/themes"), home / ".themes", home / ".local/share/themes"]


def installed_themes() -> set[str]:
    names: set[str] = set()
    for d in theme_dirs():
        try:
            names |= {p.name for p in d.iterdir() if p.is_dir()}
        except OSError:
            continue
    return names


def is_dark_name(name: str) -> bool:
    return "dark" in name.lower()


def theme_variant(name: str, dark: bool, available: set[str]) -> str | None:
    """The light or dark sibling of a GTK theme, e.g. Mint-Y-Aqua <-> Mint-Y-Dark-Aqua."""
    if not name:
        return None
    if dark:
        if is_dark_name(name):
            return name
        parts = name.split("-")
        candidates = [f"{name}-dark", f"{name}-Dark"]
        candidates += ["-".join(parts[:i] + ["Dark"] + parts[i:]) for i in range(len(parts) - 1, 0, -1)]
        return next((c for c in candidates if c in available), None)
    if not is_dark_name(name):
        return name
    light = re.sub(r"-(dark|darker)(?=-|$)", "", name, flags=re.IGNORECASE)
    return light if light in available and light != name else None


def _gsettings_get(runner: Runner, schema: str, key: str) -> str:
    gs = runner.which("gsettings")
    if not gs:
        return ""
    return runner.run([gs, "get", schema, key], check=False).strip().strip("'")


def read_theme(runner: Runner, family: str) -> str | None:
    """"light"/"dark" from the desktop's own settings, or None if unknown."""
    try:
        if family in GNOME_LIKE:
            scheme = _gsettings_get(runner, "org.gnome.desktop.interface", "color-scheme")
            if scheme == "prefer-dark":
                return "dark"
            return "dark" if is_dark_name(_gsettings_get(runner, "org.gnome.desktop.interface", "gtk-theme")) else "light"
        if family == "cinnamon":
            return "dark" if is_dark_name(_gsettings_get(runner, "org.cinnamon.desktop.interface", "gtk-theme")) else "light"
        if family == "mate":
            return "dark" if is_dark_name(_gsettings_get(runner, "org.mate.interface", "gtk-theme")) else "light"
        if family == "xfce" and runner.which("xfconf-query"):
            name = runner.run([runner.which("xfconf-query"), "-c", "xsettings", "-p", "/Net/ThemeName"], check=False)
            return "dark" if is_dark_name(name) else "light"
        if family == "kde":
            for tool in ("kreadconfig6", "kreadconfig5"):
                if runner.which(tool):
                    scheme = runner.run([runner.which(tool), "--group", "General", "--key", "ColorScheme"], check=False)
                    return "dark" if is_dark_name(scheme) else "light"
    except OSError:
        pass
    return None


def write_theme(runner: Runner, family: str, dark: bool, available: set[str] | None = None) -> None:
    available = installed_themes() if available is None else available
    gs = runner.which("gsettings")
    # libadwaita/GTK4 apps everywhere follow this key, so set it whenever gsettings exists.
    if gs:
        runner.run([gs, "set", "org.gnome.desktop.interface", "color-scheme",
                    "prefer-dark" if dark else "default"], check=False)
    if family in GNOME_LIKE:
        _swap_gsettings_theme(runner, "org.gnome.desktop.interface", dark, available)
    elif family == "cinnamon":
        _swap_gsettings_theme(runner, "org.cinnamon.desktop.interface", dark, available)
        if gs:
            runner.run([gs, "set", "org.x.apps.portal", "color-scheme", "prefer-dark" if dark else "default"],
                       check=False)
    elif family == "mate":
        _swap_gsettings_theme(runner, "org.mate.interface", dark, available)
    elif family == "xfce":
        q = _require(runner, "xfconf-query")
        current = runner.run([q, "-c", "xsettings", "-p", "/Net/ThemeName"], check=False).strip()
        target = theme_variant(current, dark, available)
        if target and target != current:
            runner.run([q, "-c", "xsettings", "-p", "/Net/ThemeName", "-s", target])
        wm = runner.run([q, "-c", "xfwm4", "-p", "/general/theme"], check=False).strip()
        wm_target = theme_variant(wm, dark, available)
        if wm_target and wm_target != wm:
            runner.run([q, "-c", "xfwm4", "-p", "/general/theme", "-s", wm_target], check=False)
    elif family == "kde":
        exe = _require(runner, "plasma-apply-colorscheme")
        runner.run([exe, "BreezeDark" if dark else "BreezeLight"])
    elif not gs:
        raise OSError("Switching the theme isn't supported on this desktop.")


def _swap_gsettings_theme(runner: Runner, schema: str, dark: bool, available: set[str]) -> None:
    current = _gsettings_get(runner, schema, "gtk-theme")
    target = theme_variant(current, dark, available)
    if target and target != current:
        runner.run([runner.which("gsettings"), "set", schema, "gtk-theme", target], check=False)
