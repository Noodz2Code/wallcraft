"""mpv player tests: argument building, and IPC control against a fake mpv process."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from conftest import wait_until

pytest.importorskip("PySide6")

from wallcraft.config import FitMode, RuleAction  # noqa: E402
from wallcraft.library import Kind, MediaItem  # noqa: E402
from wallcraft.live.mpv import build_args, option_name, supported_options  # noqa: E402

FAKE = Path(__file__).with_name("fake_mpv.py")
needs_unix = pytest.mark.skipif(sys.platform == "win32", reason="fake mpv uses a Unix socket")


def test_option_name():
    assert option_name("--osc=no") == "osc"
    assert option_name("--no-config") == "config"
    assert option_name("--media-controls=no") == "media-controls"


def test_build_args_fill_muted_embedded():
    args = build_args("C:/v/a.mp4", r"\\.\pipe\x", FitMode.FILL, muted=True, volume=40, embedded=True,
                      supported=frozenset({"osc", "auto-window-resize"}))
    assert args[-2:] == ["--", "C:/v/a.mp4"]  # "--" so file names starting with "-" are safe
    assert "--panscan=1.0" in args and "--keepaspect=yes" in args
    assert "--aid=no" in args and "--mute=yes" in args and "--volume=40" in args
    assert "--window-minimized=yes" in args and "--border=no" in args
    assert "--loop-file=inf" in args and "--hwdec=auto-safe" in args
    assert "--osc=no" in args and "--auto-window-resize=no" in args
    assert "--media-controls=no" not in args  # unsupported by this (pretend) build


def test_build_args_stretch_unmuted_preview():
    args = build_args("a.webm", "/tmp/s", FitMode.STRETCH, muted=False, volume=150, embedded=False,
                      supported=frozenset())
    assert "--keepaspect=no" in args and "--aid=no" not in args and "--volume=100" in args
    assert "--geometry=960x540" in args and "--window-minimized=yes" not in args


@pytest.fixture
def fake_mpv(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("fake mpv uses a Unix socket")
    exe = tmp_path / "mpv"
    exe.write_text(f"#!{sys.executable}\n" + FAKE.read_text())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "mpv-log.jsonl"
    monkeypatch.setenv("FAKE_MPV_LOG", str(log))
    monkeypatch.setenv("WALLCRAFT_MPV", str(exe))
    supported_options.cache_clear()
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")

    def events():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    return exe, video, events


def commands(events):
    return [e["command"] for e in events() if "command" in e]


@needs_unix
def test_player_starts_and_is_controlled_over_ipc(qapp, fake_mpv):
    from wallcraft.live.mpv import MpvPlayer

    exe, video, events = fake_mpv
    item = MediaItem(str(video), Kind.VIDEO)
    player = MpvPlayer(str(exe), item, FitMode.FILL, muted=True, volume=50, embedded=False,
                       find_window=lambda pid: None, adopt=lambda pid: None)
    ready = []
    player.ready.connect(lambda: ready.append(True))
    player.start()
    assert wait_until(lambda: ready, 8000), "player never became ready"
    argv = next(e["argv"] for e in events() if "argv" in e)
    assert argv[-1] == str(video) and "--osc=no" in argv

    player.pause()
    player.set_audio(True, 70)
    player.set_fit(FitMode.STRETCH)
    player.play()
    assert wait_until(lambda: ["set_property", "pause", False] in commands(events))
    cmds = commands(events)
    assert ["set_property", "pause", True] in cmds
    assert ["set_property", "volume", 70] in cmds
    assert ["set_property", "aid", "auto"] in cmds and ["set_property", "mute", False] in cmds
    assert ["set_property", "keepaspect", False] in cmds

    player.shutdown()
    assert wait_until(lambda: not player.alive(), 5000)
    assert ["quit"] in commands(events)


@needs_unix
def test_live_host_runs_pauses_and_recovers_from_a_crash(qapp, fake_mpv, monkeypatch):
    from test_controller import FakeBackend
    from wallcraft.live.host import LiveHost
    from wallcraft.live.mpv import MpvPlayer
    from wallcraft.live.views import QtPlayer

    exe, video, events = fake_mpv
    backend = FakeBackend()
    host = LiveHost(backend)
    assert host.player_name == "mpv"
    item = MediaItem(str(video), Kind.VIDEO)
    mon = backend.monitors[0]

    host.set_assignments({mon.id: item}, backend.monitors, FitMode.FILL)
    assert host.state(mon.id) == "starting"
    assert wait_until(lambda: host.state(mon.id) == "playing", 8000)
    assert isinstance(host._players[mon.id], MpvPlayer)

    host.set_actions({mon.id: RuleAction.PAUSE})
    assert host.state(mon.id) == "paused"
    assert wait_until(lambda: ["set_property", "pause", True] in commands(events))

    host.set_actions({mon.id: RuleAction.STOP})
    assert host.state(mon.id) == "stopped" and not host._players

    # Simulate mpv crashing: the host retries the file with the built-in player.
    monkeypatch.setenv("FAKE_MPV_EXIT_AFTER", "0.8")
    host.set_actions({})
    assert wait_until(lambda: host.state(mon.id) == "playing", 8000)
    assert wait_until(lambda: isinstance(host._players.get(mon.id), QtPlayer), 10000)
    assert wait_until(lambda: host.state(mon.id) == "playing", 5000)
    host.stop_all(wait=True)
    assert not host._players
    os.environ.pop("FAKE_MPV_EXIT_AFTER", None)
