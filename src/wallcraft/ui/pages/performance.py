"""Performance page: battery and fullscreen rules for live wallpapers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QSlider, QSpinBox

from ...config import RuleAction
from ..widgets import Card, Page, button, label

if TYPE_CHECKING:
    from ..context import AppContext

RULES = (
    ("on_battery", "On battery power", ""),
    ("on_low_battery", "Battery is low", "low_battery"),
    ("on_battery_saver", "Battery saver is on", ""),
    ("on_fullscreen", "An app is fullscreen", "Games, videos and presentations. Only affects that display."),
    ("on_maximized", "A window is maximized", "The desktop is hidden anyway. Only affects that display."),
    ("on_locked", "The screen is locked", ""),
)


class PerformancePage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Performance", "Live wallpapers use the GPU's video decoder. These rules pause or "
                                        "stop them when they'd waste power or nobody can see them.")
        self._ctx = ctx

        # Status ------------------------------------------------------------------- #
        status = Card("Status")
        self._live = label("", wrap=True)
        self._power = label("", "muted", wrap=True)
        status.body.addWidget(self._live)
        status.body.addWidget(self._power)
        row = QHBoxLayout()
        self._pause = button("Pause live wallpapers")
        self._pause.setCheckable(True)
        self._pause.toggled.connect(self._toggle_pause)
        row.addWidget(self._pause)
        row.addStretch(1)
        status.body.addLayout(row)
        self.content.addWidget(status)

        # Rules ---------------------------------------------------------------------- #
        rules = Card("Rules", "When several rules match, the strongest action wins.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(2, 1)
        self._combos: dict[str, QComboBox] = {}
        for r, (attr, text, hint) in enumerate(RULES):
            name_box = QHBoxLayout()
            name_box.setSpacing(8)
            name_box.addWidget(label(text))
            if hint == "low_battery":
                name_box.addWidget(label("at or below"))
                self._threshold = QSpinBox()
                self._threshold.setRange(1, 99)
                self._threshold.setSuffix(" %")
                self._threshold.valueChanged.connect(self._save)
                name_box.addWidget(self._threshold)
            name_box.addStretch(1)
            grid.addLayout(name_box, r, 0)
            combo = QComboBox()
            for action in RuleAction:
                combo.addItem(action.label, action)
            combo.setMinimumWidth(200)
            combo.currentIndexChanged.connect(self._save)
            self._combos[attr] = combo
            grid.addWidget(combo, r, 1)
            if hint and hint != "low_battery":
                grid.addWidget(label(hint, "small", wrap=True), r, 2)
        rules.body.addLayout(grid)
        rules.body.addWidget(label("“Pause” freezes the current frame and frees the decoder. “Stop” unloads the "
                                   "video and shows its still image, which saves the most memory.",
                                   "small", wrap=True))
        self.content.addWidget(rules)

        # Playback ------------------------------------------------------------------- #
        playback = Card("Sound")
        self._mute = QCheckBox("Mute live wallpapers")
        self._mute.toggled.connect(self._save)
        playback.body.addWidget(self._mute)
        row = QHBoxLayout()
        row.addWidget(label("Volume"))
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setMaximumWidth(260)
        self._volume.valueChanged.connect(self._save)
        row.addWidget(self._volume)
        self._volume_label = label("", "muted")
        row.addWidget(self._volume_label)
        row.addStretch(1)
        playback.body.addLayout(row)
        playback.body.addWidget(label("With several displays, only one plays sound.", "small"))
        self.content.addWidget(playback)

        adv = Card("Advanced")
        row = QHBoxLayout()
        row.addWidget(label("Check system state every"))
        self._poll = QSpinBox()
        self._poll.setRange(1, 30)
        self._poll.setSuffix(" s")
        self._poll.valueChanged.connect(self._save)
        row.addWidget(self._poll)
        row.addStretch(1)
        adv.body.addLayout(row)
        self.content.addWidget(adv)
        self.content.addStretch(1)

        ctx.controller.systemStateChanged.connect(self._update_status)
        ctx.controller.liveStatusChanged.connect(self._update_status)
        ctx.store.changed.connect(lambda s: self._load() if s == "" else None)
        self._load()
        self._update_status()

    def _widgets(self):
        return (*self._combos.values(), self._threshold, self._mute, self._volume, self._poll)

    def _load(self) -> None:
        p = self._ctx.store.config.performance
        for w in self._widgets():
            w.blockSignals(True)
        for attr, combo in self._combos.items():
            combo.setCurrentIndex(combo.findData(getattr(p, attr)))
        self._threshold.setValue(p.low_battery_percent)
        self._mute.setChecked(p.muted)
        self._volume.setValue(p.volume)
        self._volume_label.setText(f"{p.volume}%")
        self._volume.setEnabled(not p.muted)
        self._poll.setValue(p.poll_seconds)
        for w in self._widgets():
            w.blockSignals(False)

    def _save(self) -> None:
        p = self._ctx.store.config.performance
        for attr, combo in self._combos.items():
            setattr(p, attr, combo.currentData())
        p.low_battery_percent = self._threshold.value()
        p.muted = self._mute.isChecked()
        p.volume = self._volume.value()
        p.poll_seconds = self._poll.value()
        self._volume_label.setText(f"{p.volume}%")
        self._volume.setEnabled(not p.muted)
        self._ctx.store.mark_dirty("performance")

    def _toggle_pause(self, checked: bool) -> None:
        if checked != self._ctx.controller.user_paused:
            self._ctx.controller.toggle_pause()

    def _update_status(self) -> None:
        c = self._ctx.controller
        self._live.setText(c.live_status())
        s = c.system_state
        if s.has_battery:
            pct = f"{s.battery_percent}%" if s.battery_percent is not None else "unknown"
            power = f"On battery ({pct})" if s.on_battery else f"Plugged in ({pct})"
            if s.battery_saver:
                power += " · battery saver on"
        else:
            power = "Plugged in (no battery)"
        extras = []
        if s.fullscreen_monitors:
            extras.append("fullscreen app open")
        if s.maximized_monitors:
            extras.append("maximized window open")
        if s.session_locked:
            extras.append("screen locked")
        self._power.setText(power + ("" if not extras else " · " + " · ".join(extras)))
        self._pause.blockSignals(True)
        self._pause.setChecked(c.user_paused)
        self._pause.setText("Resume live wallpapers" if c.user_paused else "Pause live wallpapers")
        self._pause.blockSignals(False)
