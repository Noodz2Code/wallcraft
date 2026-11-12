"""Read-only checks of the Win32 bindings. Run on the Windows CI runner."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_monitors_are_listed(qapp):
    from wallcraft.platform.windows.backend import WindowsBackend

    monitors = WindowsBackend().list_monitors()
    assert monitors, "expected at least one display"
    assert all(m.width > 0 and m.height > 0 for m in monitors)
    assert sum(m.primary for m in monitors) == 1


def test_theme_and_wallpaper_can_be_read():
    from wallcraft.platform.windows import theme, wallpaper

    assert isinstance(theme.apps_use_light_theme(), bool)
    current = wallpaper.get_wallpaper(None)
    assert current is None or isinstance(current, str)


def test_system_state_reads(qapp):
    from wallcraft.platform.windows.backend import WindowsBackend

    backend = WindowsBackend()
    state = backend.system_state(backend.list_monitors())
    assert isinstance(state.on_battery, bool)
    assert state.battery_percent is None or 0 <= state.battery_percent <= 100


def test_desktop_host_is_found():
    from wallcraft.platform.windows import desktop

    host = desktop.find_desktop_host()
    assert host is not None and host.alive()


def test_autostart_command_is_quoted():
    from wallcraft.platform.windows import autostart

    cmd = autostart.launch_command()
    assert cmd.startswith('"') and autostart.AUTOSTART_FLAG in cmd
