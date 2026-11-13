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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.backend = backend
        self.library = library
        self.live = LiveHost(backend, self)
        self.live.changed.connect(self.liveStatusChanged)
        self.live.changed.connect(self._sync_statics)

        self.monitors: list[Monitor] = []
        # What each monitor should show, per layer (monitor id -> path, "" for nothing).
        self.current_static: dict[str, str] = {}
        self.current_live: dict[str, str] = {}
        self._static_applied: dict[str, tuple[str, object]] = {}  # monitor id -> (path, fit) on the desktop
        self._mode_layer: str | None = None  # which layer the automatic mode currently drives
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
        self.live.stop_all(wait=True)
        self._sync_statics()  # apply any static change that was waiting under the video
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

    @property
    def in_use(self) -> set[str]:
        """Normalised paths shown on any monitor, on either layer."""
        return {norm(p) for p in (*self.current_static.values(), *self.current_live.values()) if p}

    def set_wallpaper(self, path: str, monitor_id: str | None = None) -> None:
        """Show a wallpaper now. Static files go to the static layer, animated files to the animated
        layer; the other layer is left alone."""
        cfg = self.cfg
        live = is_live(path)
        layer_name, layer_kind = ("manual_live", "live") if live else ("manual", "static")
        current = self.current_live if live else self.current_static
        # An automatic mode that drives this layer would override the choice, so switch to Manual.
        takes_over = cfg.mode is not Mode.MANUAL and self._mode_layer == layer_kind
        if monitor_id is None or len(self.monitors) <= 1:
            layer = {ALL: path}
        else:
            layer = ({mid: p for mid, p in current.items() if p} if takes_over
                     else dict(getattr(cfg, layer_name)))
            layer[monitor_id] = path
        setattr(cfg, layer_name, layer)
        if takes_over:
            cfg.mode = Mode.MANUAL
        self.store.mark_dirty("manual")
        self.refresh()
        if not live:
            targets = [monitor_id] if monitor_id else [m.id for m in self.monitors]
            if any(self.current_live.get(mid) for mid in targets):
                self.message.emit("Static wallpaper set. It's underneath the animated wallpaper and shows "
                                  "when the animation is removed or stopped.")

    def clear_animated(self, monitor_id: str | None = None) -> None:
        """Remove the animated layer (everywhere, or on one monitor) to reveal the static wallpaper."""
        cfg = self.cfg
        if monitor_id is None or len(self.monitors) <= 1:
            cfg.manual_live = {}
        else:
            cfg.manual_live = {mid: p for mid, p in self.current_live.items() if p and mid != monitor_id}
        if cfg.mode is not Mode.MANUAL and self._mode_layer == "live":
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
            items = [i.path for i in self.library.items if not i.is_live]
            if not items:
                self.message.emit("There are no static wallpapers in your library.")
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
    def _mode_wallpaper(self) -> str | None:
        cfg = self.cfg
        if cfg.mode is Mode.SLIDESHOW:
            return self._slideshow_wallpaper()
        if cfg.mode is Mode.TIME_OF_DAY:
            return self._time_of_day_wallpaper()
        if cfg.mode is Mode.THEME:
            th = cfg.theme
            primary, other = ((th.dark_wallpaper, th.light_wallpaper) if self._os_theme == "dark"
                              else (th.light_wallpaper, th.dark_wallpaper))
            return primary or other or None
        return None

    def desired(self) -> tuple[dict[str, str], dict[str, str]]:
        """(static layer, animated layer); key "*" means every monitor.

        Manual choices are the base of both layers. An automatic mode replaces only the layer that
        matches the kind of wallpaper it picked, so an animated wallpaper never replaces the static
        one underneath it, and vice versa.
        """
        static, live = dict(self.cfg.manual), dict(self.cfg.manual_live)
        path = self._mode_wallpaper()
        self._mode_layer = None
        if path:
            if is_live(path):
                live, self._mode_layer = {ALL: path}, "live"
            else:
                static, self._mode_layer = {ALL: path}, "static"
        return static, live

    def refresh(self, force: bool = False) -> None:
        if not self._started:
            return
        self._apply_auto_theme()
        try:
            static, live = self.desired()
            self._apply(static, live, force)
        except Exception:  # noqa: BLE001 - keep the engine alive no matter what
            log.exception("Applying wallpaper failed")
            self.message.emit("Applying the wallpaper failed. See the log for details.")

    def _per_monitor(self, desired: dict[str, str]) -> dict[str, str]:
        per = {}
        for mon in self.monitors:
            path = desired.get(mon.id) or desired.get(ALL) or ""
            per[mon.id] = path if path and os.path.isfile(path) else ""
        return per

    def _apply(self, static_desired: dict[str, str], live_desired: dict[str, str], force: bool) -> None:
        if not self.monitors:
            self.monitors = self.backend.list_monitors()
        statics = self._per_monitor(static_desired)
        live_paths = self._per_monitor(live_desired)
        fit = self.cfg.general.fit
        sig = (tuple(sorted(statics.items())), tuple(sorted(live_paths.items())), fit,
               tuple((m.id, m.rect) for m in self.monitors))
        if sig == self._applied_sig and not force:
            return
        self._applied_sig = sig
        if force:
            self._static_applied.clear()
        for p in {p for p in (*static_desired.values(), *live_desired.values()) if p and not os.path.isfile(p)}:
            log.warning("Wallpaper file not found: %s", p)
            self.message.emit(f"File not found: {os.path.basename(p)}")

        lives: dict[str, MediaItem] = {}
        for mid, p in live_paths.items():
            item = (self.library.find(p) or MediaItem.from_path(p)) if p else None
            if item is not None and item.is_live:
                lives[mid] = item
        self.current_static = statics
        self.current_live = {mid: item.path for mid, item in lives.items()}

        self.live.set_audio(self.cfg.performance.muted, self.cfg.performance.volume)
        self.live.set_assignments(lives, self.monitors, fit)
        self._sync_statics()
        log.info("Applied wallpapers: static %s, animated %s",
                 {k: os.path.basename(v) for k, v in statics.items()},
                 {k: os.path.basename(v) for k, v in self.current_live.items()})
        self.wallpaperChanged.emit()
        self._poll_system()

    def _sync_statics(self) -> None:
        """Put the static layer on the desktop, except where an animated wallpaper covers it.

        Under a running animation the static wallpaper can't be seen, and on Windows 11 24H2
        changing it destroys the desktop layer the video sits in. Such changes wait until the
        animated layer is removed or stopped (or Wallcraft quits), then apply.
        """
        fit = self.cfg.general.fit
        todo = {}
        for mon in self.monitors:
            target = self.current_static.get(mon.id, "")
            if not target or self._static_applied.get(mon.id) == (target, fit):
                continue
            if self.live.state(mon.id) not in ("", "stopped"):
                continue
            todo[mon.id] = target
        if todo and self._set_statics(todo):
            for mid, path in todo.items():
                self._static_applied[mid] = (path, fit)

    def _set_statics(self, assign: dict[str, str]) -> bool:
        fit = self.cfg.general.fit
        all_ids = {m.id for m in self.monitors}
        paths = set(assign.values())
        try:
            if len(paths) == 1 and set(assign) == all_ids:
                self.backend.set_static_wallpaper(paths.pop(), fit, None)
            else:
                for mid, p in assign.items():
                    self.backend.set_static_wallpaper(p, fit, mid)
            return True
        except OSError as exc:
            log.error("Setting wallpaper failed: %s", exc)
            self.message.emit(f"Couldn't set wallpaper: {exc}")
            return False

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
            label = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped", "starting": "Starting"}[s]
            prefix = f"{mon.name}: " if len(self.monitors) > 1 else ""
            states.append(f"{prefix}{label}{reason}")
        return " · ".join(states) or "No live wallpaper active"
