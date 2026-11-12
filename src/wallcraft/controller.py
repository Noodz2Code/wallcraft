"""The engine: decides which wallpaper each monitor shows and keeps it applied."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from .config import Config, Mode, RuleAction
from .library import MediaItem, is_live, norm
from .live.host import LiveHost
from .platform.base import Backend, Monitor
from .rules import Decision, SystemState, evaluate
from .schedule import Resolution, effective_location, resolve, theme_at
from .services.config_store import ConfigStore
from .services.library_service import LibraryService
from .services.posters import PosterService
from .slideshow import Slideshow

log = logging.getLogger(__name__)

ALL = "*"
TICK_MS = 10_000


class Controller(QObject):
    wallpaperChanged = Signal()
    liveStatusChanged = Signal()
    osThemeChanged = Signal(str)
    systemStateChanged = Signal()
    message = Signal(str)

    def __init__(
        self,
        store: ConfigStore,
        backend: Backend,
        library: LibraryService,
        posters: PosterService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.backend = backend
        self.library = library
        self.posters = posters
        self.live = LiveHost(backend, self)
        self.live.changed.connect(self.liveStatusChanged)

        self.monitors: list[Monitor] = []
        self.current: dict[str, str] = {}  # monitor id -> path actually applied
        self.system_state = SystemState()
        self.decisions: dict[str, Decision] = {}
        self.tod_resolution: Resolution | None = None
        self._os_theme = "light"
        self._user_paused = False
        self._applied_sig: tuple | None = None
        self._slideshow = Slideshow()
        self._started = False

        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self.refresh)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_system)
        self._refresh_soon = QTimer(self)
        self._refresh_soon.setSingleShot(True)
        self._refresh_soon.setInterval(50)
        self._refresh_soon.timeout.connect(self.refresh)
        self._screens_soon = QTimer(self)
        self._screens_soon.setSingleShot(True)
        self._screens_soon.setInterval(1500)
        self._screens_soon.timeout.connect(self._on_screens_changed)

        store.changed.connect(self._on_config_changed)
        library.changed.connect(self._refresh_soon.start)

    # ------------------------------------------------------------------------ #
    @property
    def cfg(self) -> Config:
        return self.store.config

    @property
    def os_theme(self) -> str:
        return self._os_theme

    @property
    def user_paused(self) -> bool:
        return self._user_paused

    def start(self) -> None:
        self._started = True
        self._os_theme = self.backend.os_theme()
        self.monitors = self.backend.list_monitors()
        self.backend.set_full_quality_jpeg(self.cfg.general.full_quality_jpeg)
        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._watch_screen)
            app.screenRemoved.connect(lambda _s: self._screens_soon.start())
            for screen in app.screens():
                self._watch_screen(screen, initial=True)
        self._poll.setInterval(self.cfg.performance.poll_seconds * 1000)
        self.refresh()
        self._tick.start()
        self._poll.start()

    def shutdown(self) -> None:
        self._tick.stop()
        self._poll.stop()
        self.live.stop_all()
        self.store.save_now()

    def _watch_screen(self, screen, initial: bool = False) -> None:
        screen.geometryChanged.connect(lambda _g: self._screens_soon.start())
        if not initial:
            self._screens_soon.start()

    def _on_screens_changed(self) -> None:
        self.monitors = self.backend.list_monitors()
        log.info("Displays changed: %s", ", ".join(f"{m.name} {m.width}x{m.height}" for m in self.monitors))
        self.refresh(force=True)

    def _on_config_changed(self, section: str) -> None:
        if section == "performance":
            self._poll.setInterval(self.cfg.performance.poll_seconds * 1000)
            self.live.set_audio(self.cfg.performance.muted, self.cfg.performance.volume)
            self._poll_system()
        if section == "general":
            self.backend.set_full_quality_jpeg(self.cfg.general.full_quality_jpeg)
        self._refresh_soon.start()

    # Public actions ----------------------------------------------------------- #
    def set_mode(self, mode: Mode) -> None:
        if self.cfg.mode is not mode:
            self.cfg.mode = mode
            self.store.mark_dirty("mode")

    def set_wallpaper(self, path: str, monitor_id: str | None = None) -> None:
        """Apply a wallpaper now (switches to Manual mode)."""
        cfg = self.cfg
        if monitor_id is None or len(self.monitors) <= 1:
            cfg.manual = {ALL: path}
        else:
            if cfg.mode is not Mode.MANUAL:
                # Keep what the other displays show right now.
                cfg.manual = {mid: p for mid, p in self.current.items() if p}
            cfg.manual[monitor_id] = path
        cfg.mode = Mode.MANUAL
        self.store.mark_dirty("manual")
        self.refresh()

    def next_wallpaper(self, step: int = 1) -> None:
        cfg = self.cfg
        if cfg.mode is Mode.SLIDESHOW:
            self._advance_slideshow(step)
            self.refresh()
            return
        if cfg.mode is Mode.MANUAL:
            items = [i.path for i in self.library.items]
            if not items:
                self.message.emit("Your library is empty.")
                return
            cur = cfg.manual.get(ALL) or next(iter(cfg.manual.values()), "")
            keys = [norm(p) for p in items]
            idx = keys.index(norm(cur)) if cur and norm(cur) in keys else -1
            self.set_wallpaper(items[(idx + step) % len(items)])
            return
        self.message.emit(f"Next/previous isn't available in {cfg.mode.label} mode.")

    def toggle_pause(self) -> None:
        self._user_paused = not self._user_paused
        self._poll_system()

    def set_os_theme(self, theme: str) -> None:
        """Switch Windows light/dark mode (in a thread: the broadcast can block)."""
        if not self.backend.supports_os_theme_write:
            self.message.emit("Changing the system theme isn't supported on this platform.")
            return
        th = self.cfg.theme
        light = theme == "light"
        apps = light if th.switch_apps else None
        system = light if th.switch_system else None

        def work() -> None:
            try:
                self.backend.set_os_theme(apps, system)
            except OSError:
                log.exception("Failed to switch Windows theme")

        threading.Thread(target=work, name="theme-switch", daemon=True).start()
        QTimer.singleShot(800, self._poll_system)

    # Slideshow ------------------------------------------------------------------ #
    def slideshow_items(self) -> list[str]:
        ss = self.cfg.slideshow
        if ss.use_library or not ss.items:
            paths = [i.path for i in self.library.items]
        else:
            paths = []
            for p in ss.items:
                if os.path.isdir(p):
                    paths.extend(i.path for i in self.library.items if norm(i.path).startswith(norm(p)))
                else:
                    paths.append(p)
        if not ss.include_live:
            def live(p: str) -> bool:
                item = self.library.find(p)
                return item.is_live if item else is_live(p)

            paths = [p for p in paths if not live(p)]
        return paths

    def slideshow_next_change(self) -> float | None:
        if self.cfg.mode is not Mode.SLIDESHOW or not self.cfg.state.slideshow_current:
            return None
        return self.cfg.state.slideshow_changed_at + self.cfg.slideshow.interval_minutes * 60

    def _sync_slideshow(self) -> None:
        st = self.cfg.state
        self._slideshow.configure(self.slideshow_items(), self.cfg.slideshow.shuffle,
                                  current=st.slideshow_current or None)

    def _advance_slideshow(self, step: int) -> str | None:
        self._sync_slideshow()
        cur = self._slideshow.next() if step >= 0 else self._slideshow.previous()
        st = self.cfg.state
        st.slideshow_current = cur or ""
        st.slideshow_changed_at = time.time()
        self.store.save_later()
        return cur

    def _slideshow_wallpaper(self) -> str | None:
        st = self.cfg.state
        if not self.slideshow_items():
            # Library not scanned yet (or empty): keep the saved position and timer untouched.
            return st.slideshow_current or None
        self._sync_slideshow()
        cur = self._slideshow.current
        due = time.time() - st.slideshow_changed_at >= self.cfg.slideshow.interval_minutes * 60
        if cur is None or due:
            cur = self._advance_slideshow(1)
        return cur

    # Time of day ---------------------------------------------------------------- #
    def location(self):
        tod = self.cfg.time_of_day
        return effective_location(tod.latitude, tod.longitude)

    def _time_of_day_wallpaper(self) -> str | None:
        slots = self.cfg.time_of_day.slots
        now = datetime.now().astimezone()
        res = resolve(slots, now, self.location(), include=lambda s: bool(s.wallpaper))
        self.tod_resolution = res
        if res is not None:
            return slots[res.index].wallpaper
        return next((s.wallpaper for s in slots if s.wallpaper), None)

    def _apply_auto_theme(self) -> None:
        th = self.cfg.theme
        if not th.auto_switch or not self.backend.supports_os_theme_write:
            return
        want = theme_at(datetime.now().astimezone(), th.schedule, th.light_time, th.dark_time, self.location())
        # Act only on transitions so a manual change in Windows Settings isn't fought every tick.
        if want != self.cfg.state.last_auto_theme:
            self.cfg.state.last_auto_theme = want
            self.store.save_later()
            log.info("Automatic theme switch -> %s", want)
            self.set_os_theme(want)

    # Core ----------------------------------------------------------------------- #
    def desired(self) -> dict[str, str]:
        cfg = self.cfg
        if cfg.mode is Mode.MANUAL:
            return dict(cfg.manual)
        if cfg.mode is Mode.SLIDESHOW:
            path = self._slideshow_wallpaper()
        elif cfg.mode is Mode.TIME_OF_DAY:
            path = self._time_of_day_wallpaper()
        else:
            th = cfg.theme
            primary, other = ((th.dark_wallpaper, th.light_wallpaper) if self._os_theme == "dark"
                              else (th.light_wallpaper, th.dark_wallpaper))
            path = primary or other
        return {ALL: path} if path else {}

    def refresh(self, force: bool = False) -> None:
        if not self._started:
            return
        self._apply_auto_theme()
        try:
            self._apply(self.desired(), force)
        except Exception:  # noqa: BLE001 - keep the engine alive no matter what
            log.exception("Applying wallpaper failed")
            self.message.emit("Applying the wallpaper failed. See the log for details.")

    def _apply(self, desired: dict[str, str], force: bool) -> None:
        if not self.monitors:
            self.monitors = self.backend.list_monitors()
        per: dict[str, str] = {}
        for mon in self.monitors:
            path = desired.get(mon.id) or desired.get(ALL) or ""
            per[mon.id] = path if path and os.path.isfile(path) else ""
        missing = {p for p in desired.values() if p and not os.path.isfile(p)}
        fit = self.cfg.general.fit
        sig = (tuple(sorted(per.items())), fit, tuple((m.id, m.rect) for m in self.monitors))
        if sig == self._applied_sig and not force:
            return
        self._applied_sig = sig
        for p in missing:
            log.warning("Wallpaper file not found: %s", p)
            self.message.emit(f"File not found: {os.path.basename(p)}")

        statics = {mid: p for mid, p in per.items() if p and not is_live(p)}
        lives: dict[str, MediaItem] = {}
        for mid, p in per.items():
            if p and is_live(p):
                item = self.library.find(p) or MediaItem.from_path(p)
                if item is not None:
                    lives[mid] = item

        # Under each live wallpaper, set its still frame as the real Windows wallpaper. When the
        # frame is cached, do it now (before the video window attaches) so Explorer's wallpaper
        # fade doesn't run over a freshly embedded window.
        groups: dict[str, list[str]] = {}
        for mid, item in lives.items():
            groups.setdefault(item.path, []).append(mid)
        for path, mids in groups.items():
            cached = self.posters.cached(path)
            if cached:
                statics.update({mid: cached for mid in mids})
            else:
                self.posters.request(path, lambda poster, p=path, m=tuple(mids): self._on_poster(p, m, poster))
        self._set_statics(statics)

        self.live.set_audio(self.cfg.performance.muted, self.cfg.performance.volume)
        self.live.set_assignments(lives, self.monitors, fit)
        self.current = per
        log.info("Applied wallpapers: %s", {k: os.path.basename(v) for k, v in per.items()})
        self.wallpaperChanged.emit()
        self._poll_system()

    def _set_statics(self, assign: dict[str, str]) -> None:
        if not assign:
            return
        fit = self.cfg.general.fit
        all_ids = {m.id for m in self.monitors}
        paths = set(assign.values())
        try:
            if len(paths) == 1 and set(assign) == all_ids:
                self.backend.set_static_wallpaper(paths.pop(), fit, None)
            else:
                for mid, p in assign.items():
                    self.backend.set_static_wallpaper(p, fit, mid)
        except OSError as exc:
            log.error("Setting wallpaper failed: %s", exc)
            self.message.emit(f"Couldn't set wallpaper: {exc}")

    def _on_poster(self, path: str, mids: tuple[str, ...], poster: str | None) -> None:
        if not poster:
            return
        still_live = [mid for mid in mids if self.current.get(mid) == path]
        if still_live:
            self._set_statics({mid: poster for mid in still_live})

    # Rules ---------------------------------------------------------------------- #
    def _poll_system(self) -> None:
        if not self._started:
            return
        theme = self.backend.os_theme()
        if theme != self._os_theme:
            self._os_theme = theme
            log.info("Windows theme is now %s", theme)
            self.osThemeChanged.emit(theme)
            if self.cfg.mode is Mode.THEME:
                self._refresh_soon.start()

        try:
            state = self.backend.system_state(self.monitors)
        except OSError:
            log.exception("Reading system state failed")
            state = SystemState()
        self.system_state = state
        perf = self.cfg.performance
        decisions = {}
        for mon in self.monitors:
            d = evaluate(perf, state, mon.id)
            if self._user_paused:
                d = d.combine(RuleAction.PAUSE, "paused by you")
            decisions[mon.id] = d
        if decisions != self.decisions:
            self.decisions = decisions
            self.liveStatusChanged.emit()
        self.live.set_actions({mid: d.action for mid, d in decisions.items()})
        self.live.check_health()
        self.systemStateChanged.emit()

    def live_status(self) -> str:
        """One-line, human readable status of live wallpaper playback."""
        if not self.live.has_assignments:
            return "No live wallpaper active"
        if self.live.error:
            return self.live.error
        states = []
        for mon in self.monitors:
            s = self.live.state(mon.id)
            if not s:
                continue
            d = self.decisions.get(mon.id)
            reason = f" ({', '.join(d.reasons)})" if d and d.reasons and s != "playing" else ""
            label = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped"}[s]
            prefix = f"{mon.name}: " if len(self.monitors) > 1 else ""
            states.append(f"{prefix}{label}{reason}")
        return " · ".join(states) or "No live wallpaper active"
