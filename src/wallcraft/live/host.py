"""Manages one LiveWindow per monitor and applies play/pause/stop decisions."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ..config import FitMode, RuleAction
from ..library import MediaItem
from ..platform.base import Backend, Monitor
from .views import LiveWindow

log = logging.getLogger(__name__)

MAX_ATTACH_FAILURES = 3


class LiveHost(QObject):
    changed = Signal()

    def __init__(self, backend: Backend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._windows: dict[str, LiveWindow] = {}
        self._assign: dict[str, MediaItem] = {}
        self._monitors: dict[str, Monitor] = {}
        self._actions: dict[str, RuleAction] = {}
        self._fit = FitMode.FILL
        self._muted = True
        self._volume = 50
        self._attach_failures = 0
        self.error: str = ""

    # Queries ------------------------------------------------------------------ #
    @property
    def has_assignments(self) -> bool:
        return bool(self._assign)

    def state(self, monitor_id: str) -> str:
        """"playing", "paused", "stopped" or "" when nothing live is assigned."""
        if monitor_id not in self._assign:
            return ""
        win = self._windows.get(monitor_id)
        if win is None:
            return "stopped"
        return "playing" if win.playing else "paused"

    # Updates ------------------------------------------------------------------ #
    def set_assignments(self, assign: dict[str, MediaItem], monitors: list[Monitor], fit: FitMode) -> None:
        changed = assign != self._assign or {m.id: m for m in monitors} != self._monitors
        self._assign = dict(assign)
        self._monitors = {m.id: m for m in monitors}
        if changed:
            self._attach_failures = 0
            self.error = ""
        if fit != self._fit:
            self._fit = fit
            for win in self._windows.values():
                win.set_fit(fit)
        self._reconcile()

    def set_actions(self, actions: dict[str, RuleAction]) -> None:
        if actions != self._actions:
            self._actions = dict(actions)
            self._reconcile()

    def set_audio(self, muted: bool, volume: int) -> None:
        self._muted, self._volume = muted, volume
        self._update_audio()

    def stop_all(self) -> None:
        self._assign = {}
        self._reconcile()

    def check_health(self) -> None:
        """Recreate windows that lost their place on the desktop (e.g. Explorer restarted)."""
        if not self._backend.supports_desktop_embedding:
            return
        broken = []
        for mid, win in self._windows.items():
            mon = self._monitors.get(mid)
            if mon is None or not self._backend.ensure_live_window(int(win.winId()), mon):
                broken.append(mid)
        if broken:
            log.warning("Re-attaching live wallpaper on %s", ", ".join(broken))
            for mid in broken:
                self._windows.pop(mid).shutdown()
            self._reconcile()

    # Internals ---------------------------------------------------------------- #
    def _reconcile(self) -> None:
        before = {mid: w.playing for mid, w in self._windows.items()}
        for mid in list(self._windows):
            win = self._windows[mid]
            item = self._assign.get(mid)
            if (item is None or item != win.item or mid not in self._monitors
                    or self._actions.get(mid) is RuleAction.STOP):
                self._windows.pop(mid).shutdown()

        for mid, item in self._assign.items():
            if mid in self._windows or self._actions.get(mid) is RuleAction.STOP:
                continue
            mon = self._monitors.get(mid)
            if mon is None or self._attach_failures >= MAX_ATTACH_FAILURES:
                continue
            win = self._create(item, mon)
            if win is not None:
                self._windows[mid] = win

        for mid, win in self._windows.items():
            if self._actions.get(mid) is RuleAction.PAUSE:
                win.pause()
            else:
                win.play()
        self._update_audio()
        if before and not self._windows:
            # Last live window gone: make Explorer repaint the still wallpaper underneath.
            self._backend.refresh_desktop()
        if before != {mid: w.playing for mid, w in self._windows.items()}:
            self.changed.emit()

    def _create(self, item: MediaItem, mon: Monitor) -> LiveWindow | None:
        embedded = self._backend.supports_desktop_embedding
        win = LiveWindow(item, embedded=embedded, title=f"Live wallpaper preview - {mon.name}")
        win.set_fit(self._fit)
        if not embedded:
            win.resize(960, 540)
            win.show()
            return win
        hwnd = int(win.winId())
        if not self._backend.attach_live_window(hwnd, mon):
            self._attach_failures += 1
            self.error = "Could not attach to the desktop. Try restarting Explorer or Wallcraft."
            log.error("Attaching live window to desktop failed (%d)", self._attach_failures)
            win.shutdown()
            return None
        self._attach_failures = 0
        self.error = ""
        win.show()
        self._backend.ensure_live_window(hwnd, mon)  # Qt may move the window when showing it
        return win

    def _update_audio(self) -> None:
        # Only one display plays sound, otherwise the same video echoes.
        audio_mid = next((mid for mid in sorted(self._windows) if self._windows[mid].playing), None)
        for mid, win in self._windows.items():
            win.set_audio(not self._muted and mid == audio_mid, self._volume)
