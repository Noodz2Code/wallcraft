"""Read-only checks of the macOS backend. Run on the macOS CI runners."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


def test_backend_is_selected(qapp):
    from wallcraft.platform import create_backend

    assert create_backend().name == "macos"


def test_reads_theme_monitors_and_state(qapp):
    from wallcraft.platform.macos.backend import MacBackend

    b = MacBackend()
    assert b.os_theme() in ("light", "dark")
    monitors = b.list_monitors()
    assert monitors and all(m.logical for m in monitors)
    state = b.system_state(monitors)
    assert isinstance(state.on_battery, bool) and isinstance(state.session_locked, bool)


def test_live_window_can_be_made_desktop_level(qapp):
    from PySide6.QtWidgets import QWidget

    from wallcraft.platform.macos.backend import MacBackend

    b = MacBackend()
    w = QWidget()
    mon = b.list_monitors()[0]
    assert b.attach_live_window(int(w.winId()), mon)
    w.close()
