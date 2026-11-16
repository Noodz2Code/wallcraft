"""mpv-based live wallpaper player, the same design Lively Wallpaper uses.

Each live wallpaper runs in its own mpv process. mpv opens a borderless window that
the platform backend moves behind the desktop icons, and Wallcraft controls playback
(pause, volume, fit) over mpv's JSON IPC. Keeping the player out of process means video
decoding and GPU presentation never depend on Qt's rendering inside an embedded window,
and a crashing video can't take Wallcraft down with it.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from ..config import FitMode
from ..library import MediaItem

log = logging.getLogger(__name__)

EXE_NAME = "mpv.exe" if sys.platform == "win32" else "mpv"
START_TIMEOUT_MS = 15_000
_ids = itertools.count(1)

# mpv properties for each fit mode: (keepaspect, panscan, video-unscaled)
FIT_PROPERTIES: dict[FitMode, dict[str, object]] = {
    FitMode.FILL: {"keepaspect": True, "panscan": 1.0, "video-unscaled": "no"},
    FitMode.SPAN: {"keepaspect": True, "panscan": 1.0, "video-unscaled": "no"},
    FitMode.FIT: {"keepaspect": True, "panscan": 0.0, "video-unscaled": "no"},
    FitMode.TILE: {"keepaspect": True, "panscan": 0.0, "video-unscaled": "no"},
    FitMode.STRETCH: {"keepaspect": False, "panscan": 0.0, "video-unscaled": "no"},
    FitMode.CENTER: {"keepaspect": True, "panscan": 0.0, "video-unscaled": "downscale-big"},
}

# Options every supported mpv build has.
CORE_OPTIONS = [
    "--no-config",
    "--loop-file=inf",
    "--keep-open=yes",
    "--force-window=yes",
    "--hwdec=auto-safe",
    "--input-default-bindings=no",
    "--input-cursor=no",
    "--cursor-autohide=no",
    "--osd-level=0",
    "--stop-screensaver=no",
    "--msg-level=all=warn",
    "--title=Wallcraft live wallpaper",
]
# Options that only exist in newer or platform-specific builds; added only if supported.
OPTIONAL_OPTIONS = [
    "--osc=no",  # only in builds with Lua
    "--media-controls=no",
    "--auto-window-resize=no",
    "--keepaspect-window=no",
    "--input-vo-keyboard=no",
    "--snap-window=no",
    "--taskbar-progress=no",
    "--window-dragging=no",
]
EMBEDDED_OPTIONS = [
    "--border=no",
    "--ontop=no",
    "--window-minimized=yes",  # never steal focus; the backend un-minimizes after embedding
    "--geometry=-9999:0",      # and stay off-screen until then
]


def find_mpv() -> str | None:
    """Bundled mpv first, then $WALLCRAFT_MPV, then a dev copy in vendor/mpv, then PATH."""
    env = os.environ.get("WALLCRAFT_MPV")
    if env:
        return env if os.path.isfile(env) else None
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "mpv" / EXE_NAME)
        candidates.append(Path(sys.executable).resolve().parent / "mpv" / EXE_NAME)
    else:
        candidates.append(Path(__file__).resolve().parents[3] / "vendor" / "mpv" / EXE_NAME)
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("mpv")


def _no_window_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


@lru_cache(maxsize=4)
def supported_options(mpv: str) -> frozenset[str]:
    """Names of the options this mpv build accepts (unknown options make mpv refuse to start)."""
    try:
        out = subprocess.run([mpv, "--no-config", "--list-options"], capture_output=True, text=True,
                             timeout=15, creationflags=_no_window_flags()).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not query mpv options: %s", exc)
        return frozenset()
    names = set()
    for line in out.splitlines():
        token = line.strip().split(" ", 1)[0]
        if token.startswith("--"):
            names.add(token[2:])
    return frozenset(names)


def option_name(arg: str) -> str:
    name = arg[2:].split("=", 1)[0]
    return name[3:] if name.startswith("no-") else name


def build_args(path: str, ipc: str, fit: FitMode, muted: bool, volume: int, embedded: bool,
               supported: frozenset[str], wid: int = 0) -> list[str]:
    """mpv command line. ``wid``: draw into that existing window (X11) instead of opening one."""
    args = list(CORE_OPTIONS)
    args.append(f"--input-ipc-server={ipc}")
    args += [f"--volume={max(0, min(100, volume))}", f"--mute={'yes' if muted else 'no'}"]
    if muted:
        args.append("--aid=no")  # don't decode audio at all while muted
    if wid:
        args.append(f"--wid={wid}")
    elif embedded:
        args += EMBEDDED_OPTIONS
    else:
        args.append("--geometry=960x540")
    args += [a for a in OPTIONAL_OPTIONS if option_name(a) in supported]
    for name, value in FIT_PROPERTIES[fit].items():
        args.append(f"--{name}={_option_value(value)}")
    args += ["--", path]
    return args


def mpvpaper_args(path: str, ipc: str, fit: FitMode, muted: bool, volume: int, output: str,
                  supported: frozenset[str]) -> list[str]:
    """mpvpaper (Wayland layer-shell wallpaper) command line; mpv options go through -o."""
    opts = ["loop-file=inf", "hwdec=auto-safe", "input-default-bindings=no", "osd-level=0",
            "msg-level=all=warn", f"input-ipc-server={ipc}", f"volume={max(0, min(100, volume))}",
            f"mute={'yes' if muted else 'no'}"]
    if muted:
        opts.append("aid=no")
    opts += [f"{name}={_option_value(value)}" for name, value in FIT_PROPERTIES[fit].items()]
    return ["-o", " ".join(opts), output or "*", path]


def _option_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


class MpvPlayer(QObject):
    """One mpv process showing one wallpaper on one monitor."""

    ready = Signal()        # IPC connected and, when embedding, the player window exists
    failed = Signal(str)    # could not start
    exited = Signal()       # process ended unexpectedly after it was ready

    def __init__(
        self,
        mpv: str,
        item: MediaItem,
        fit: FitMode,
        muted: bool,
        volume: int,
        embedded: bool,
        find_window: Callable[[int], int | None],
        adopt: Callable[[int], None],
        parent: QObject | None = None,
        surface=None,
        launcher: str | None = None,
        output: str = "",
    ) -> None:
        super().__init__(parent)
        self.item = item
        self._mpv = mpv
        self._surface = surface      # DesktopSurface mpv draws into (--wid), Linux X11
        self._launcher = launcher    # e.g. mpvpaper on Wayland; it draws the wallpaper itself
        self._output = output
        self._fit = fit
        self._muted = muted
        self._volume = volume
        self._audio_on = not muted
        self._embedded = embedded
        self._find_window = find_window
        self._adopt = adopt
        self._playing = True
        self._closing = False
        self._ready = False
        self._hwnd: int | None = None
        self._queue: list[bytes] = []
        self._elapsed = 0

        name = f"wallcraft-mpv-{os.getpid()}-{next(_ids)}"
        if sys.platform == "win32":
            self._ipc_arg = rf"\\.\pipe\{name}"
            self._server = name  # QLocalSocket adds the \\.\pipe\ prefix itself
        else:
            self._ipc_arg = self._server = os.path.join(tempfile.gettempdir(), f"{name}.sock")

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._log_output)
        self._proc.finished.connect(self._on_finished)
        self._sock = QLocalSocket(self)
        self._sock.connected.connect(self._flush)
        self._sock.readyRead.connect(self._read_replies)
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._wait_until_ready)

    # Properties ------------------------------------------------------------------- #
    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    @property
    def playing(self) -> bool:
        return self._playing

    def alive(self) -> bool:
        return self._proc.state() != QProcess.ProcessState.NotRunning

    # Lifecycle -------------------------------------------------------------------- #
    def start(self) -> None:
        if self._launcher:
            program = self._launcher
            args = mpvpaper_args(self.item.path, self._ipc_arg, self._fit, self._muted, self._volume,
                                 self._output, frozenset())
        else:
            program = self._mpv
            wid = int(self._surface.winId()) if self._surface is not None else 0
            if wid:
                self._hwnd = wid
            args = build_args(self.item.path, self._ipc_arg, self._fit, self._muted, self._volume,
                              self._embedded, supported_options(self._mpv), wid=wid)
        log.info("Starting %s for %s", os.path.basename(program), self.item.path)
        log.debug("%s %s", program, " ".join(args))
        self._proc.start(program, args)
        if not self._proc.waitForStarted(5000):
            self.failed.emit(f"mpv did not start: {self._proc.errorString()}")
            return
        self._adopt(int(self._proc.processId()))
        self._poll.start()

    def _wait_until_ready(self) -> None:
        self._elapsed += self._poll.interval()
        if not self.alive():
            return  # _on_finished reports it
        if self._sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self._sock.connectToServer(self._server)
        # Only the Windows "attach" mode has to find mpv's own window; otherwise the window is
        # ours (--wid) or the helper's (mpvpaper), and a working IPC connection means ready.
        needs_window = self._embedded and self._surface is None and not self._launcher
        if needs_window and self._hwnd is None:
            self._hwnd = self._find_window(int(self._proc.processId()))
        connected = self._sock.state() == QLocalSocket.LocalSocketState.ConnectedState
        if connected and (self._hwnd is not None or not needs_window):
            self._poll.stop()
            self._ready = True
            self.ready.emit()
        elif self._elapsed >= START_TIMEOUT_MS:
            self._poll.stop()
            self.failed.emit("mpv window did not appear in time")
            self.shutdown()

    def show_embedded(self) -> None:
        """Show the surface mpv draws into; in "attach" mode the backend shows mpv's own window."""
        if self._surface is not None:
            self._surface.show()

    def place(self, rect) -> None:
        if self._surface is not None:
            self._surface.setGeometry(rect)

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._poll.stop()
        if self._surface is not None:
            self._surface.hide()  # released together with this player once mpv has exited
        if self.alive():
            self._send(["quit"])
            QTimer.singleShot(1500, self, self._kill)
        # Graceful close: pending writes (the quit command) are sent first.
        self._sock.disconnectFromServer()

    def _kill(self) -> None:
        if self.alive():
            self._proc.kill()

    def wait_closed(self, timeout_ms: int = 1500) -> None:
        """Block until the process has exited (used when Wallcraft quits)."""
        if self.alive() and not self._proc.waitForFinished(timeout_ms):
            self._proc.kill()
            self._proc.waitForFinished(500)

    def _on_finished(self, code: int, _status) -> None:
        if self._closing:
            return
        self._poll.stop()
        if self._ready:
            log.warning("mpv exited unexpectedly (code %s) while playing %s", code, self.item.path)
            self.exited.emit()
        else:
            self.failed.emit(f"mpv exited during startup (code {code})")

    # Control ---------------------------------------------------------------------- #
    def play(self) -> None:
        if not self._playing:
            self._playing = True
            self._set("pause", False)

    def pause(self) -> None:
        if self._playing:
            self._playing = False
            self._set("pause", True)

    def set_fit(self, fit: FitMode) -> None:
        if fit != self._fit:
            self._fit = fit
            for name, value in FIT_PROPERTIES[fit].items():
                self._set(name, value)

    def set_audio(self, enabled: bool, volume: int) -> None:
        if volume != self._volume:
            self._volume = volume
            self._set("volume", max(0, min(100, volume)))
        if enabled != self._audio_on:
            self._audio_on = enabled
            self._set("aid", "auto" if enabled else "no")
            self._set("mute", not enabled)

    def _set(self, prop: str, value: object) -> None:
        self._send(["set_property", prop, value])

    def _send(self, command: list) -> None:
        line = (json.dumps({"command": command}) + "\n").encode("utf-8")
        if self._sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self._sock.write(line)
        else:
            self._queue.append(line)

    def _flush(self) -> None:
        for line in self._queue:
            self._sock.write(line)
        self._queue.clear()

    def _read_replies(self) -> None:
        for raw in bytes(self._sock.readAll()).splitlines():
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("error") not in (None, "success"):
                log.warning("mpv rejected a command: %s", msg)

    def _log_output(self) -> None:
        text = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        for line in text.splitlines():
            if line.strip():
                log.warning("mpv: %s", line.strip())
