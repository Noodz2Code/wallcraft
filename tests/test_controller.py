"""Engine tests with an in-memory backend (no real desktop is touched)."""

import os

import pytest

from conftest import pump, wait_until

pytest.importorskip("PySide6")

from wallcraft.config import FitMode, Mode, RuleAction  # noqa: E402
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

    media = tmp_path / "media"
    files = {name: make_image(media / f"{name}.png", c)
             for name, c in (("a", "#111111"), ("b", "#222222"), ("c", "#333333"))}
    for name in ("v1", "v2"):
        (media / f"{name}.mp4").write_bytes(b"\x00")  # classified by extension; content isn't decoded
        files[name] = str(media / f"{name}.mp4")
    backend = FakeBackend([Monitor("m1", "Display 1", 0, 0, 1920, 1080, True),
                           Monitor("m2", "Display 2", 1920, 0, 1920, 1080)])
    store = ConfigStore(paths.config_file())
    library = LibraryService(store)
    ctl = Controller(store, backend, library)
    library.add_paths([str(media)])
    assert wait_until(lambda: len(library.items) == 5)
    ctl.start()
    yield ctl, backend, store, files
    ctl.shutdown()


def test_manual_all_monitors_uses_single_call(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    assert backend.static[-1] == ("a.png", None)
    assert set(ctl.current_static.values()) == {files["a"]}


def test_manual_per_monitor(engine):
    ctl, backend, store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["b"], "m2")
    assert ctl.current_static == {"m1": files["a"], "m2": files["b"]}
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
    first = ctl.current_static["m1"]
    ctl.next_wallpaper(1)
    second = ctl.current_static["m1"]
    assert first != second
    ctl.next_wallpaper(-1)
    assert ctl.current_static["m1"] == first


def test_slideshow_advances_when_interval_elapsed(engine):
    ctl, _backend, store, _files = engine
    store.config.slideshow.shuffle = False
    ctl.set_mode(Mode.SLIDESHOW)
    pump(100)
    first = ctl.current_static["m1"]
    store.config.state.slideshow_changed_at -= store.config.slideshow.interval_minutes * 60 + 1
    ctl.refresh()
    assert ctl.current_static["m1"] != first


def test_theme_mode_follows_os_theme(engine):
    ctl, backend, store, files = engine
    store.config.theme.light_wallpaper = files["a"]
    store.config.theme.dark_wallpaper = files["c"]
    ctl.set_mode(Mode.THEME)
    pump(100)
    assert ctl.current_static["m1"] == files["a"]
    backend.theme = "dark"
    ctl._poll_system()
    pump(150)
    assert ctl.current_static["m1"] == files["c"]


def test_missing_file_is_skipped(engine):
    ctl, _backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["a"] + ".missing")
    assert ctl.current_static == {"m1": "", "m2": ""}


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


class SurfaceBackend(FakeBackend):
    """Like Linux X11 / macOS: Wallcraft's own window is turned into a desktop window."""

    def __init__(self):
        super().__init__([Monitor("m1", "Display 1", 0, 0, 2880, 1800, True, "eDP-1", (0, 0, 1440, 900))])
        self.attached: list[int] = []

    @property
    def live_strategy(self):
        return "surface"

    def attach_live_window(self, hwnd, monitor):
        self.attached.append(hwnd)
        return True


class NoLiveBackend(FakeBackend):
    @property
    def live_strategy(self):
        return "none"

    @property
    def live_unsupported_reason(self):
        return "GNOME on Wayland doesn't let apps draw behind the desktop."


def test_surface_strategy_places_window_in_logical_coordinates(qapp, tmp_path):
    from wallcraft.library import Kind, MediaItem
    from wallcraft.live.host import LiveHost

    clip = tmp_path / "clip.gif"
    clip.write_bytes(b"GIF89a")
    backend = SurfaceBackend()
    host = LiveHost(backend)
    host._mpv = None  # built-in player
    host.set_assignments({"m1": MediaItem(str(clip), Kind.ANIMATED)}, backend.monitors, FitMode.FILL)
    assert wait_until(lambda: host.state("m1") == "playing")
    win = host._players["m1"]._win
    assert backend.attached == [int(win.winId())]
    assert win.geometry().getRect() == (0, 0, 1440, 900)  # Qt units, not the 2880x1800 physical size
    host.stop_all(wait=True)


def test_unsupported_live_shows_reason_and_keeps_static(qapp, wallcraft_home, tmp_path):
    from wallcraft import paths
    from wallcraft.controller import Controller
    from wallcraft.services.config_store import ConfigStore
    from wallcraft.services.library_service import LibraryService

    img = make_image(tmp_path / "s.png")
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"\x00")
    backend = NoLiveBackend()
    store = ConfigStore(paths.config_file())
    ctl = Controller(store, backend, LibraryService(store))
    ctl.start()
    ctl.set_wallpaper(img)
    ctl.set_wallpaper(str(vid))
    assert not ctl.live._players
    assert "GNOME on Wayland" in ctl.live_status()
    assert backend.static[-1][0] == "s.png"
    ctl.shutdown()


def static_calls(backend):
    return [name for name, _mid in backend.static]


def test_animated_wallpaper_never_replaces_the_static_one(engine):
    ctl, backend, store, files = engine
    ctl.set_wallpaper(files["a"])
    before = list(backend.static)
    ctl.set_wallpaper(files["v1"])
    pump(200)
    assert backend.static == before, "setting an animated wallpaper must not touch the static wallpaper"
    assert set(ctl.current_static.values()) == {files["a"]}
    assert set(ctl.current_live.values()) == {files["v1"]}
    assert store.config.manual == {"*": files["a"]} and store.config.manual_live == {"*": files["v1"]}
    assert ctl.live.state("m1") in ("starting", "playing")


def test_static_changes_wait_under_a_running_animation(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["v1"])
    assert wait_until(lambda: ctl.live.state("m1") == "playing")
    ctl.set_wallpaper(files["b"])
    pump(100)
    assert "b.png" not in static_calls(backend), "hidden static change should be deferred"
    assert set(ctl.current_static.values()) == {files["b"]}  # but it is the new target
    ctl.clear_animated()
    pump(100)
    assert static_calls(backend)[-1] == "b.png"
    assert not any(ctl.current_live.values())


def test_stop_rule_reveals_the_pending_static_wallpaper(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["v1"])
    assert wait_until(lambda: ctl.live.state("m1") == "playing")
    ctl.set_wallpaper(files["c"])
    assert "c.png" not in static_calls(backend)
    backend.state = SystemState(battery_saver=True)  # default rule: stop
    ctl._poll_system()
    assert ctl.live.state("m1") == "stopped"
    assert "c.png" in static_calls(backend)


def test_slideshow_of_animated_items_keeps_manual_static_layer(engine):
    ctl, _backend, store, files = engine
    ctl.set_wallpaper(files["a"])
    store.config.slideshow.use_library = False
    store.config.slideshow.items = [files["v1"], files["v2"]]
    store.config.slideshow.include_live = True
    store.config.slideshow.shuffle = False
    ctl.set_mode(Mode.SLIDESHOW)
    pump(150)
    assert set(ctl.current_live.values()) == {files["v1"]}
    assert set(ctl.current_static.values()) == {files["a"]}


def test_setting_static_in_slideshow_switches_to_manual(engine):
    ctl, _backend, store, files = engine
    store.config.slideshow.shuffle = False
    ctl.set_mode(Mode.SLIDESHOW)
    pump(100)
    ctl.set_wallpaper(files["c"])
    assert store.config.mode is Mode.MANUAL


def test_reload_all_reapplies_static_and_restarts_animation(engine):
    ctl, backend, _store, files = engine
    ctl.set_wallpaper(files["a"])
    ctl.set_wallpaper(files["v1"], "m2")
    assert wait_until(lambda: ctl.live.state("m2") == "playing")
    old_player = ctl.live._players["m2"]
    calls = len(backend.static)
    ctl.reload_all()
    assert len(backend.static) > calls, "static wallpaper should be applied again"
    assert backend.static[-1] == ("a.png", "m1")  # m2 is covered by the animation, so it waits
    assert wait_until(lambda: ctl.live.state("m2") == "playing")
    assert ctl.live._players["m2"] is not old_player, "animated wallpaper should be restarted"


def test_main_window_builds(engine):
    from wallcraft import paths
    from wallcraft.services.thumbnails import ThumbnailCache
    from wallcraft.ui import style
    from wallcraft.ui.context import AppContext
    from wallcraft.ui.main_window import PAGES, MainWindow

    ctl, backend, store, _files = engine
    from PySide6.QtWidgets import QApplication

    style.apply_theme(QApplication.instance(), dark=True)
    from wallcraft.services.posters import PosterService

    thumbs = ThumbnailCache(paths.thumbnail_dir(), PosterService(paths.poster_dir()))
    ctx = AppContext(store, backend, ctl.library, thumbs, ctl)
    win = MainWindow(ctx, lambda: None)
    win.show()
    for i in range(len(PAGES)):
        win.show_page(PAGES[i][0])
        pump(30)
    library_page = win._stack.widget(0)
    library_page.show_tab("animated")
    assert library_page._proxy.rowCount() == 2
    library_page.show_tab("static")
    assert library_page._proxy.rowCount() == 3
    win.close()
