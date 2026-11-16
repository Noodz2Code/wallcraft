"""Runs one live wallpaper player per monitor and applies play/pause/stop decisions.

Players are mpv processes (like Lively Wallpaper) when mpv is available, with an in-process
Qt player as fallback. Each player reports `ready` once its window exists; only then is it
attached behind the desktop icons. Players that fail, crash or lose their place on the
desktop (Explorer restart, display change) are recreated automatically.
"""

from __future__ import annotations

import logging
import os
from functools import partial

from PySide6.QtCore import QObject, QRect, QTimer, Signal

from ..config import FitMode, RuleAction
from ..library import Kind, MediaItem
from ..platform.base import Backend, Monitor
from .mpv import MpvPlayer, find_mpv
from .views import DesktopSurface, QtPlayer

log = logging.getLogger(__name__)

MAX_FAILURES = 3
RETRY_MS = 3000


class LiveHost(QObject):
    changed = Signal()

    def __init__(self, backend: Backend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._players: dict[str, MpvPlayer | QtPlayer] = {}
        self._attached: set[str] = set()
        # Players that were closed but whose mpv process may still be exiting. They have no Qt
        # parent: Python owns them, and they are released once the process is gone. (Mixing a Qt
        # parent with deleteLater() let a quitting app delete the same player twice and crash.)
        self._retired: list[MpvPlayer | QtPlayer] = []
        self._assign: dict[str, MediaItem] = {}
        self._monitors: dict[str, Monitor] = {}
        self._actions: dict[str, RuleAction] = {}
        self._fit = FitMode.FILL
        self._muted = True
        self._volume = 50
        self._failures: dict[str, int] = {}
        self._qt_only: set[str] = set()  # files mpv couldn't play
        self._mpv = find_mpv()
        self.error = ""
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self._reconcile)
        log.info("Live wallpaper player: %s", self._mpv or "built-in (mpv not found)")

    # Queries ---------------------------------------------------------------------- #
    @property
    def player_name(self) -> str:
        return "mpv" if self._mpv else "built-in"

    @property
    def has_assignments(self) -> bool:
        return bool(self._assign)

    def state(self, monitor_id: str) -> str:
        """"playing", "paused", "starting", "stopped" or "" when nothing live is assigned."""
        if monitor_id not in self._assign:
            return ""
        player = self._players.get(monitor_id)
        if player is None:
            return "stopped"
        if monitor_id not in self._attached:
            return "starting"
        return "playing" if player.playing else "paused"

    def current_item(self, monitor_id: str) -> MediaItem | None:
        player = self._players.get(monitor_id)
        return player.item if player else None

    # Updates ------------------------------------------------------------------------- #
    def set_assignments(self, assign: dict[str, MediaItem], monitors: list[Monitor], fit: FitMode) -> None:
        if assign != self._assign or {m.id: m for m in monitors} != self._monitors:
            self._failures.clear()
            self.error = ""
        self._assign = dict(assign)
        self._monitors = {m.id: m for m in monitors}
        if fit != self._fit:
            self._fit = fit
            for player in self._players.values():
                player.set_fit(fit)
        self._reconcile()

    def set_actions(self, actions: dict[str, RuleAction]) -> None:
        if actions != self._actions:
            self._actions = dict(actions)
            self._reconcile()

    def set_audio(self, muted: bool, volume: int) -> None:
        self._muted, self._volume = muted, volume
        self._update_audio()

    def stop_all(self, wait: bool = False) -> None:
        self._assign = {}
        self._reconcile()
        if wait:
            for p in self._retired:
                p.wait_closed()
            self._release_retired()

    def restart_all(self) -> None:
        """Close every player and start them again, forgetting earlier failures."""
        self._failures.clear()
        self._qt_only.clear()
        self.error = ""
        for mid in list(self._players):
            self._drop(mid)
        self._reconcile()

    def check_health(self) -> None:
        """Recreate players that crashed or lost their place on the desktop."""
        self._release_retired()
        broken = []
        for mid in list(self._attached):
            player = self._players.get(mid)
            mon = self._monitors.get(mid)
            if player is None or mon is None:
                continue
            if not player.alive():
                broken.append(mid)
            elif (self._backend.supports_desktop_embedding and player.hwnd
                  and not self._backend.ensure_live_window(player.hwnd, mon)):
                log.warning("Live wallpaper on %s lost its place on the desktop; re-attaching", mon.name)
                broken.append(mid)
        if broken:
            for mid in broken:
                self._drop(mid)
            self._reconcile()

    # Internals ------------------------------------------------------------------------- #
    def _reconcile(self) -> None:
        before = self._snapshot()
        had_players = bool(self._players)
        for mid in list(self._players):
            item = self._assign.get(mid)
            if (item is None or item != self._players[mid].item or mid not in self._monitors
                    or self._actions.get(mid) is RuleAction.STOP):
                self._drop(mid)

        strategy = self._backend.live_strategy
        if strategy == "none" and self._assign:
            # This system can't show animated wallpapers (e.g. GNOME on Wayland); say why.
            self.error = self._backend.live_unsupported_reason or "Animated wallpapers aren't supported here."
        for mid, item in self._assign.items():
            if strategy == "none":
                break
            if mid in self._players or self._actions.get(mid) is RuleAction.STOP:
                continue
            mon = self._monitors.get(mid)
            if mon is None or self._failures.get(mid, 0) >= MAX_FAILURES:
                continue
            self._create(mid, item, mon)

        self._apply_actions()
        if had_players and not self._players:
            self._backend.refresh_desktop()
        if before != self._snapshot():
            self.changed.emit()

    def _snapshot(self) -> dict[str, str]:
        return {mid: self.state(mid) for mid in self._assign}

    def _use_mpv(self, item: MediaItem) -> bool:
        if not self._mpv or item.path in self._qt_only:
            return False
        if item.kind is Kind.VIDEO:
            return True
        # GIF through mpv; animated WebP stays on Qt, which is known to decode it.
        return os.path.splitext(item.path)[1].lower() == ".gif"

    def _create(self, mid: str, item: MediaItem, mon: Monitor) -> None:
        strategy = self._backend.live_strategy
        embedded = strategy in ("attach", "surface", "external")
        common = dict(find_window=self._backend.find_process_window, adopt=self._backend.adopt_child_process)
        player: MpvPlayer | QtPlayer
        if strategy == "external":
            # A helper (mpvpaper) draws on the desktop layer itself; we only control it over IPC.
            player = MpvPlayer(self._mpv or "", item, self._fit, self._muted, self._volume, True,
                               launcher=self._backend.live_external_program(), output=mon.device, **common)
        elif strategy == "surface" and self._backend.mpv_embeds_by_wid and self._use_mpv(item):
            # Linux X11: our desktop-level window, mpv draws into it.
            player = MpvPlayer(self._mpv, item, self._fit, self._muted, self._volume, True,
                               surface=DesktopSurface(f"Live wallpaper - {mon.name}"), **common)
        elif strategy == "attach" and self._use_mpv(item):
            player = MpvPlayer(self._mpv, item, self._fit, self._muted, self._volume, True, **common)
        elif strategy == "preview" and self._use_mpv(item):
            player = MpvPlayer(self._mpv, item, self._fit, self._muted, self._volume, False, **common)
        else:
            player = QtPlayer(item, self._fit, embedded and strategy == "attach",
                              f"Live wallpaper preview - {mon.name}", surface=strategy == "surface")
        player.ready.connect(partial(self._on_ready, mid, player))
        player.failed.connect(partial(self._on_failed, mid, player))
        player.exited.connect(partial(self._on_failed, mid, player, "The player stopped unexpectedly."))
        self._players[mid] = player
        player.start()

    def _on_ready(self, mid: str, player) -> None:
        if self._players.get(mid) is not player:
            return
        mon = self._monitors.get(mid)
        if mon is None:
            return
        strategy = self._backend.live_strategy
        if strategy in ("attach", "surface"):
            hwnd = player.hwnd
            if not hwnd or not self._backend.attach_live_window(hwnd, mon):
                self._on_failed(mid, player, "Could not place the wallpaper behind the desktop icons.")
                return
            if strategy == "surface" and mon.logical:
                player.place(QRect(*mon.logical))
            player.show_embedded()
            self._backend.ensure_live_window(hwnd, mon)
            # Some players resize their window once the video loads; re-check shortly after.
            QTimer.singleShot(1500, self, self.check_health)
        self._attached.add(mid)
        self._failures[mid] = 0
        self.error = ""
        log.info("Live wallpaper running on %s (%s)", mon.name, type(player).__name__)
        self._apply_actions()
        self.changed.emit()

    def _on_failed(self, mid: str, player, reason: str) -> None:
        if self._players.get(mid) is not player:
            return
        log.error("Live wallpaper on %s failed: %s", mid, reason)
        self._drop(mid)
        if isinstance(player, MpvPlayer) and self._backend.live_strategy != "external":
            # Retry this file with the built-in player before giving up.
            self._qt_only.add(player.item.path)
        else:
            self._failures[mid] = self._failures.get(mid, 0) + 1
        self.error = reason
        self.changed.emit()
        if self._failures.get(mid, 0) < MAX_FAILURES:
            self._retry.start()

    def _drop(self, mid: str) -> None:
        player = self._players.pop(mid, None)
        self._attached.discard(mid)
        if player is not None:
            player.shutdown()
            self._retired.append(player)

    def _release_retired(self) -> None:
        """Drop closed players whose process has exited. Called from timers only, never from a
        player's own signal, so a player is never destroyed while one of its methods is running."""
        self._retired = [p for p in self._retired if p.alive()]

    def _apply_actions(self) -> None:
        for mid in self._attached:
            player = self._players[mid]
            if self._actions.get(mid) is RuleAction.PAUSE:
                player.pause()
            else:
                player.play()
        self._update_audio()

    def _update_audio(self) -> None:
        # Only one display plays sound, otherwise the same video echoes.
        audio_mid = next((m for m in sorted(self._attached) if self._players[m].playing), None)
        for mid in self._attached:
            self._players[mid].set_audio(not self._muted and mid == audio_mid, self._volume)
