"""Engine tests with an in-memory backend (no real desktop is touched)."""

import os

import pytest

from conftest import pump, wait_until

pytest.importorskip("PySide6")

from wallcraft.config import Mode, RuleAction  # noqa: E402
from wallcraft.platform.base import Backend, Monitor  # noqa: E402
from wallcraft.rules import SystemState  # noqa: E402


class FakeBackend(Backend):
    name = "fake"
    supports_per_monitor = True

    def __init__(self, monitors=None):
        self.monitors = monitors or [Monitor("m1", "Display 1", 0, 0, 1920, 1080, True)]
        self.static: list[tuple[str, str | None]] = []
        self.theme = "light"
        self.state = SystemState()

    def list_monitors(self):
        return list(self.monitors)

    def set_static_wallpaper(self, path, fit, monitor_id=None):
        self.static.append((os.path.basename(path), monitor_id))

    def os_theme(self):
        return self.theme

    def system_state(self, monitors):
        return self.state


def make_image(path, color="#336699"):
    from PySide6.QtGui import QColor, QImage

    img = QImage(64, 36, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return str(path)


@pytest.fixture
def engine(qapp, wallcraft_home, tmp_path):
    from wallcraft import paths
    from wallcraft.controller import Controller
    from wallcraft.services.config_store import ConfigStore
    from wallcraft.services.library_service import LibraryService
    from wallcraft.services.posters import PosterService

    media = tmp_path / "media"
    files = {name: make_image(media / f"{name}.png", c)
             for name, c in (("a", "#111111"), ("b", "#222222"), ("c", "#333333"))}
    backend = FakeBackend([Monitor("m1", "Display 1", 0, 0, 1920, 1080, True),
                           Monitor("m2", "Display 2", 1920, 0, 1920, 1080)])
    store = ConfigStore(paths.config_file())
    library = LibraryService(store)
    posters = PosterService(paths.poster_dir())
    ctl = Controller(store, backend, library, posters)
    library.add_paths([str(media)])
    assert wait_until(lambda: len(library.items) == 3)
    ctl.start()
    yield ctl, backend, store, files
    ctl.shutdown()


def test_manual_all_monitors_uses_single_call(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    assert backend.static[-1] == ("a.png", None)
    assert set(ctl.current.values()) == {files["a"]}


def test_manual_per_monitor(engine):
    ctl, backend, store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["b"], "m2")
    assert ctl.current == {"m1": files["a"], "m2": files["b"]}
    assert ("b.png", "m2") in backend.static
    assert store.config.mode is Mode.MANUAL


def test_unchanged_state_is_not_reapplied(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    count = len(backend.static)
    ctl.refresh()
    ctl.refresh()
    assert len(backend.static) == count


def test_slideshow_next_and_previous(engine):
    ctl, _backend, store, _files = engine
    store.config.slideshow.shuffle = False
    ctl.set_mode(Mode.SLIDESHOW)
    pump(100)
    first = ctl.current["m1"]
    ctl.next_wallpaper(1)
    second = ctl.current["m1"]
    assert first != second
    ctl.next_wallpaper(-1)
    assert ctl.current["m1"] == first


def test_slideshow_advances_when_interval_elapsed(engine):
    ctl, _backend, store, _files = engine
    store.config.slideshow.shuffle = False
    ctl.set_mode(Mode.SLIDESHOW)
    pump(100)
    first = ctl.current["m1"]
    store.config.state.slideshow_changed_at -= store.config.slideshow.interval_minutes * 60 + 1
    ctl.refresh()
    assert ctl.current["m1"] != first


def test_theme_mode_follows_os_theme(engine):
    ctl, backend, store, files = engine
    store.config.theme.light_wallpaper = files["a"]
    store.config.theme.dark_wallpaper = files["c"]
    ctl.set_mode(Mode.THEME)
    pump(100)
    assert ctl.current["m1"] == files["a"]
    backend.theme = "dark"
    ctl._poll_system()
    pump(150)
    assert ctl.current["m1"] == files["c"]


def test_missing_file_is_skipped(engine):
    ctl, _backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["a"] + ".missing")
    assert ctl.current == {"m1": "", "m2": ""}


def test_rules_produce_per_monitor_decisions(engine):
    ctl, backend, _store, _files = engine
    backend.state = SystemState(on_battery=True, has_battery=True, battery_percent=50,
                                fullscreen_monitors=frozenset({"m2"}))
    ctl._poll_system()
    assert ctl.decisions["m1"].action is RuleAction.PAUSE
    assert "fullscreen app" in ctl.decisions["m2"].reasons
    ctl.toggle_pause()
    assert "paused by you" in ctl.decisions["m1"].reasons


def test_config_is_persisted(engine):
    from wallcraft.config import load_config

    ctl, _backend, store, files = engine
    ctl.set_wallpaper(files["b"])
    store.save_now()
    assert load_config(store.path).manual == {"*": files["b"]}


def test_main_window_builds(engine):
    from wallcraft import paths
    from wallcraft.services.thumbnails import ThumbnailCache
    from wallcraft.ui import style
    from wallcraft.ui.context import AppContext
    from wallcraft.ui.main_window import PAGES, MainWindow

    ctl, backend, store, _files = engine
    from PySide6.QtWidgets import QApplication

    style.apply_theme(QApplication.instance(), dark=True)
    thumbs = ThumbnailCache(paths.thumbnail_dir(), ctl.posters)
    ctx = AppContext(store, backend, ctl.library, thumbs, ctl)
    win = MainWindow(ctx, lambda: None)
    win.show()
    for i in range(len(PAGES)):
        win.show_page(PAGES[i][0])
        pump(30)
    win.close()
