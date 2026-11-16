"""Theme page: wallpapers that follow light/dark mode, and automatic theme switching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QRadioButton,
    QTimeEdit,
    QWidget,
)

from ...config import Appearance, Mode, ThemeSchedule
from ...osinfo import IS_WINDOWS, SYSTEM_NAME
from ..widgets import Card, ModeBanner, Page, WallpaperSlot, button, label

if TYPE_CHECKING:
    from ..context import AppContext


class ThemePage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Theme sync", "Pair wallpapers with light and dark mode, and switch the system "
                                       "theme on a schedule.")
        self._ctx = ctx
        self.content.addWidget(ModeBanner(
            ctx, Mode.THEME,
            "Follow-theme mode is off. Turn it on to swap wallpapers whenever the system changes between "
            "light and dark."))

        # Wallpapers ------------------------------------------------------------------ #
        walls = Card("Wallpapers")
        self._os_state = label("", "muted")
        walls.body.addWidget(self._os_state)
        row = QHBoxLayout()
        row.setSpacing(28)
        self._light = WallpaperSlot(ctx, "Light mode")
        self._dark = WallpaperSlot(ctx, "Dark mode")
        self._light.changed.connect(lambda p: self._set_wallpaper("light", p))
        self._dark.changed.connect(lambda p: self._set_wallpaper("dark", p))
        row.addWidget(self._light)
        row.addWidget(self._dark)
        row.addStretch(1)
        walls.body.addLayout(row)
        self.content.addWidget(walls)

        # Auto switch -------------------------------------------------------------------- #
        auto = Card("Switch the system theme automatically",
                    "Wallcraft switches only at the scheduled times, so you can still change the theme by "
                    "hand in between.")
        self._auto = QCheckBox("Switch between light and dark automatically")
        auto.body.addWidget(self._auto)
        self._sun = QRadioButton("Light from sunrise to sunset")
        self._custom = QRadioButton("Custom times")
        group = QButtonGroup(self)
        group.addButton(self._sun)
        group.addButton(self._custom)
        auto.body.addWidget(self._sun)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self._custom)
        custom_row.addSpacing(12)
        custom_row.addWidget(label("Light at"))
        self._light_time = QTimeEdit()
        self._light_time.setDisplayFormat("HH:mm")
        custom_row.addWidget(self._light_time)
        custom_row.addWidget(label("Dark at"))
        self._dark_time = QTimeEdit()
        self._dark_time.setDisplayFormat("HH:mm")
        custom_row.addWidget(self._dark_time)
        custom_row.addStretch(1)
        auto.body.addLayout(custom_row)
        # Only Windows has separate app and taskbar themes; elsewhere it's one switch.
        apply_box = QWidget()
        apply_row = QHBoxLayout(apply_box)
        apply_row.setContentsMargins(0, 0, 0, 0)
        apply_row.addWidget(label("Apply to:"))
        self._apps = QCheckBox("Apps")
        self._system = QCheckBox("Windows (taskbar and Start)")
        apply_row.addWidget(self._apps)
        apply_row.addWidget(self._system)
        apply_row.addStretch(1)
        apply_box.setVisible(IS_WINDOWS)
        auto.body.addWidget(apply_box)
        now_row = QHBoxLayout()
        to_light = button("Switch to light now")
        to_light.clicked.connect(lambda: ctx.controller.set_os_theme("light"))
        to_dark = button("Switch to dark now")
        to_dark.clicked.connect(lambda: ctx.controller.set_os_theme("dark"))
        now_row.addWidget(to_light)
        now_row.addWidget(to_dark)
        now_row.addStretch(1)
        auto.body.addLayout(now_row)
        if not ctx.backend.supports_os_theme_write:
            auto.setEnabled(False)
            auto.body.addWidget(label("Not available on this platform.", "muted"))
        self.content.addWidget(auto)

        # App appearance ------------------------------------------------------------------- #
        appearance = Card("Wallcraft appearance")
        row = QHBoxLayout()
        self._appearance = QComboBox()
        for value, text in ((Appearance.SYSTEM, "Match system"), (Appearance.LIGHT, "Light"),
                            (Appearance.DARK, "Dark")):
            self._appearance.addItem(text, value)
        row.addWidget(self._appearance)
        row.addStretch(1)
        appearance.body.addLayout(row)
        self.content.addWidget(appearance)
        self.content.addStretch(1)

        for w in (self._auto, self._sun, self._custom, self._apps, self._system):
            w.toggled.connect(self._save)
        self._light_time.timeChanged.connect(self._save)
        self._dark_time.timeChanged.connect(self._save)
        self._appearance.currentIndexChanged.connect(self._save)
        ctx.store.changed.connect(lambda s: self._load() if s in ("theme", "") else None)
        ctx.controller.osThemeChanged.connect(lambda _t: self._update_os_state())
        self._load()

    @property
    def cfg(self):
        return self._ctx.store.config.theme

    def _widgets(self):
        return (self._auto, self._sun, self._custom, self._apps, self._system, self._light_time,
                self._dark_time, self._appearance)

    def _load(self) -> None:
        cfg = self.cfg
        for w in self._widgets():
            w.blockSignals(True)
        self._light.set_path(cfg.light_wallpaper)
        self._dark.set_path(cfg.dark_wallpaper)
        self._auto.setChecked(cfg.auto_switch)
        self._sun.setChecked(cfg.schedule is ThemeSchedule.SUN)
        self._custom.setChecked(cfg.schedule is ThemeSchedule.CUSTOM)
        self._light_time.setTime(QTime.fromString(cfg.light_time, "HH:mm"))
        self._dark_time.setTime(QTime.fromString(cfg.dark_time, "HH:mm"))
        self._apps.setChecked(cfg.switch_apps)
        self._system.setChecked(cfg.switch_system)
        self._appearance.setCurrentIndex(self._appearance.findData(cfg.appearance))
        for w in self._widgets():
            w.blockSignals(False)
        self._sync_enabled()
        self._update_os_state()

    def _sync_enabled(self) -> None:
        on = self._auto.isChecked()
        for w in (self._sun, self._custom, self._apps, self._system):
            w.setEnabled(on)
        custom = on and self._custom.isChecked()
        self._light_time.setEnabled(custom)
        self._dark_time.setEnabled(custom)

    def _save(self) -> None:
        cfg = self.cfg
        was_auto = cfg.auto_switch
        before = (cfg.schedule, cfg.light_time, cfg.dark_time)
        cfg.auto_switch = self._auto.isChecked()
        cfg.schedule = ThemeSchedule.SUN if self._sun.isChecked() else ThemeSchedule.CUSTOM
        cfg.light_time = self._light_time.time().toString("HH:mm")
        cfg.dark_time = self._dark_time.time().toString("HH:mm")
        cfg.switch_apps = self._apps.isChecked()
        cfg.switch_system = self._system.isChecked()
        cfg.appearance = self._appearance.currentData()
        if cfg.auto_switch and (not was_auto or before != (cfg.schedule, cfg.light_time, cfg.dark_time)):
            # Apply the schedule right away when it's turned on or changed.
            self._ctx.store.config.state.last_auto_theme = ""
        self._sync_enabled()
        self._ctx.store.mark_dirty("theme-options")

    def _set_wallpaper(self, which: str, path: str) -> None:
        if which == "light":
            self.cfg.light_wallpaper = path
        else:
            self.cfg.dark_wallpaper = path
        self._ctx.store.mark_dirty("theme-wallpapers")
        self._update_os_state()

    def _update_os_state(self) -> None:
        theme = self._ctx.controller.os_theme
        self._os_state.setText(f"{SYSTEM_NAME} is in {theme} mode right now, so the {theme} wallpaper applies.")
        self._light.set_in_use(theme == "light")
        self._dark.set_in_use(theme == "dark")
