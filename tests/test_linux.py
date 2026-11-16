"""Linux backend logic, tested with a recording command runner (no desktop is touched)."""

import pytest

from wallcraft.config import FitMode
from wallcraft.platform.linux import desktop
from wallcraft.platform.linux.desktop import (
    desktop_family,
    read_theme,
    session_type,
    set_wallpaper,
    theme_variant,
    write_theme,
)
from wallcraft.platform.linux.system import battery_status
from wallcraft.platform.macos.pmset import parse_pmset


class FakeRunner(desktop.Runner):
    def __init__(self, tools=("gsettings", "xfconf-query"), outputs=None):
        self.tools = set(tools)
        self.outputs = outputs or {}
        self.calls: list[list[str]] = []

    def which(self, name):
        return f"/usr/bin/{name}" if name in self.tools else None

    def run(self, cmd, check=True):
        self.calls.append(cmd)
        key = " ".join(cmd[1:])
        return next((out for pattern, out in self.outputs.items() if pattern in key), "")

    def cmds(self):
        return [" ".join([c[0].rsplit("/", 1)[-1], *c[1:]]) for c in self.calls]


# Desktop detection ---------------------------------------------------------------- #
@pytest.mark.parametrize("env, family", [
    ({"XDG_CURRENT_DESKTOP": "XFCE"}, "xfce"),
    ({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, "gnome"),
    ({"XDG_CURRENT_DESKTOP": "KDE"}, "kde"),
    ({"XDG_CURRENT_DESKTOP": "X-Cinnamon"}, "cinnamon"),
    ({"XDG_CURRENT_DESKTOP": "Budgie:GNOME"}, "budgie"),
    ({"XDG_CURRENT_DESKTOP": "sway"}, "sway"),
    ({"XDG_CURRENT_DESKTOP": "", "DESKTOP_SESSION": "mate"}, "mate"),
    ({}, "unknown"),
])
def test_desktop_family(env, family):
    assert desktop_family(env) == family


def test_session_type():
    assert session_type({"XDG_SESSION_TYPE": "wayland"}) == "wayland"
    assert session_type({"XDG_SESSION_TYPE": "x11"}) == "x11"
    assert session_type({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"


# Static wallpaper per desktop --------------------------------------------------------- #
def test_gnome_sets_light_and_dark_uris(tmp_path):
    img = tmp_path / "a b.jpg"
    img.write_bytes(b"x")
    r = FakeRunner()
    set_wallpaper(r, "gnome", str(img), FitMode.FILL, None)
    uri = img.resolve().as_uri()
    assert r.cmds() == [
        f"gsettings set org.gnome.desktop.background picture-uri {uri}",
        f"gsettings set org.gnome.desktop.background picture-uri-dark {uri}",
        "gsettings set org.gnome.desktop.background picture-options zoom",
    ]
    assert "%20" in uri  # spaces are URL-encoded


def test_xfce_sets_every_workspace_of_the_chosen_monitor():
    props = "\n".join([
        "/backdrop/screen0/monitoreDP-1/workspace0/last-image",
        "/backdrop/screen0/monitoreDP-1/workspace3/last-image",
        "/backdrop/screen0/monitorHDMI-1/workspace0/last-image",
    ])
    r = FakeRunner(outputs={"xfce4-desktop -l": props, "workspace_count": "2"})
    set_wallpaper(r, "xfce", "/w/a.jpg", FitMode.FIT, "eDP-1")
    sets = [c for c in r.cmds() if " -s " in c]
    targets = sorted({c.split(" -p ")[1].split(" ")[0].rsplit("/", 1)[0] for c in sets})
    assert targets == ["/backdrop/screen0/monitoreDP-1/workspace0", "/backdrop/screen0/monitoreDP-1/workspace1",
                       "/backdrop/screen0/monitoreDP-1/workspace3"]
    assert any(c.endswith("last-image -n -t string -s /w/a.jpg") for c in sets)
    assert any(c.endswith("image-style -n -t int -s 4") for c in sets)  # 4 = scaled (fit)


def test_xfce_all_monitors_includes_ones_not_configured_yet():
    r = FakeRunner(outputs={"xfce4-desktop -l": "/backdrop/screen0/monitoreDP-1/workspace0/last-image",
                            "workspace_count": "1"})
    set_wallpaper(r, "xfce", "/w/a.jpg", FitMode.FILL, None, all_monitors=["eDP-1", "HDMI-1"])
    monitors = {c.split("/backdrop/screen0/")[1].split("/")[0] for c in r.cmds() if " -s " in c}
    assert monitors == {"monitoreDP-1", "monitorHDMI-1"}


def test_kde_uses_plasma_script():
    scripts = []
    set_wallpaper(FakeRunner(), "kde", "/w/a.jpg", FitMode.FILL, None, plasma_script=scripts.append)
    assert 'd.writeConfig("Image", "file:///w/a.jpg")' in scripts[0]
    assert 'd.writeConfig("FillMode", 2)' in scripts[0]


def test_sway_targets_one_output():
    r = FakeRunner(tools={"swaymsg"})
    set_wallpaper(r, "sway", "/w/a.jpg", FitMode.CENTER, "DP-1")
    assert r.cmds() == ["swaymsg output DP-1 bg /w/a.jpg center"]


def test_unknown_desktop_uses_feh_or_explains():
    r = FakeRunner(tools={"feh"})
    set_wallpaper(r, "unknown", "/w/a.jpg", FitMode.FILL, None)
    assert r.cmds() == ["feh --bg-fill /w/a.jpg"]
    with pytest.raises(OSError, match="feh"):
        set_wallpaper(FakeRunner(tools=()), "unknown", "/w/a.jpg", FitMode.FILL, None)


def test_missing_tool_is_a_clear_error():
    with pytest.raises(OSError, match="xfconf-query"):
        set_wallpaper(FakeRunner(tools=()), "xfce", "/w/a.jpg", FitMode.FILL, None)


# Theme ----------------------------------------------------------------------------------- #
AVAILABLE = {"Mint-Y-Aqua", "Mint-Y-Dark-Aqua", "Adwaita", "Adwaita-dark", "Yaru", "Yaru-dark", "Daloa",
             "Mint-L-Aqua", "Mint-L-Darker-Aqua"}


@pytest.mark.parametrize("name, dark, expected", [
    ("Mint-Y-Aqua", True, "Mint-Y-Dark-Aqua"),
    ("Mint-Y-Dark-Aqua", False, "Mint-Y-Aqua"),
    ("Adwaita", True, "Adwaita-dark"),
    ("Yaru-dark", False, "Yaru"),
    ("Mint-L-Darker-Aqua", False, "Mint-L-Aqua"),
    ("Daloa", True, None),  # no dark sibling: leave it alone
    ("Adwaita-dark", True, "Adwaita-dark"),
])
def test_theme_variant(name, dark, expected):
    assert theme_variant(name, dark, AVAILABLE) == expected


def test_xfce_dark_mode_switches_gtk_and_window_themes():
    r = FakeRunner(outputs={"/Net/ThemeName": "Mint-Y-Aqua\n", "/general/theme": "Mint-Y-Aqua\n"})
    write_theme(r, "xfce", dark=True, available=AVAILABLE)
    cmds = r.cmds()
    assert "gsettings set org.gnome.desktop.interface color-scheme prefer-dark" in cmds
    assert "xfconf-query -c xsettings -p /Net/ThemeName -s Mint-Y-Dark-Aqua" in cmds
    assert "xfconf-query -c xfwm4 -p /general/theme -s Mint-Y-Dark-Aqua" in cmds


def test_read_theme():
    assert read_theme(FakeRunner(outputs={"/Net/ThemeName": "Mint-Y-Dark-Aqua"}), "xfce") == "dark"
    assert read_theme(FakeRunner(outputs={"color-scheme": "'prefer-dark'"}), "gnome") == "dark"
    assert read_theme(FakeRunner(outputs={"color-scheme": "'default'", "gtk-theme": "'Yaru'"}), "gnome") == "light"
    assert read_theme(FakeRunner(tools=()), "sway") is None


# System state ------------------------------------------------------------------------------ #
def make_supply(root, name, **files):
    d = root / name
    d.mkdir(parents=True)
    for key, value in files.items():
        (d / key).write_text(value + "\n")


def test_battery_from_sysfs(tmp_path):
    make_supply(tmp_path, "AC", type="Mains", online="0")
    make_supply(tmp_path, "BAT0", type="Battery", capacity="42", status="Discharging")
    make_supply(tmp_path, "hidpp_battery_0", type="Battery", scope="Device", capacity="5", status="Discharging")
    assert battery_status(tmp_path) == (True, True, 42)  # the mouse battery is ignored
    (tmp_path / "AC" / "online").write_text("1\n")
    assert battery_status(tmp_path) == (True, False, 42)


def test_desktop_pc_has_no_battery(tmp_path):
    make_supply(tmp_path, "AC", type="Mains", online="1")
    assert battery_status(tmp_path) == (False, False, None)


def test_parse_pmset():
    on_battery = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t73%; discharging; 4:12 remaining"
    assert parse_pmset(on_battery) == (True, True, 73)
    assert parse_pmset("Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged")[1] is False
    assert parse_pmset("Now drawing from 'AC Power'") == (False, False, None)  # desktop Mac


# Backend choices ------------------------------------------------------------------------------ #
@pytest.mark.parametrize("env, tools, strategy", [
    ({"XDG_CURRENT_DESKTOP": "XFCE", "XDG_SESSION_TYPE": "x11"}, (), "surface"),
    ({"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}, ("mpvpaper",), "none"),
    ({"XDG_CURRENT_DESKTOP": "sway", "XDG_SESSION_TYPE": "wayland"}, ("mpvpaper",), "external"),
    ({"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"}, (), "none"),
])
def test_live_strategy(env, tools, strategy):
    from wallcraft.platform.linux.backend import LinuxBackend

    b = LinuxBackend(runner=FakeRunner(tools=tools), env=env)
    assert b.live_strategy == strategy
    assert bool(b.live_unsupported_reason) == (strategy == "none")
    if env["XDG_CURRENT_DESKTOP"] == "GNOME":
        assert "Xorg" in b.live_unsupported_reason


def test_autostart_entry(tmp_path, monkeypatch):
    from wallcraft.platform.linux import autostart

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPIMAGE", "/home/me/Apps/Wallcraft x86_64.AppImage")
    autostart.set_enabled(True)
    text = (tmp_path / "autostart" / "wallcraft.desktop").read_text()
    assert "Exec='/home/me/Apps/Wallcraft x86_64.AppImage' --autostart" in text
    assert autostart.is_enabled()
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
