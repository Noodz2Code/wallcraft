"""Time-of-day page: switch wallpapers at fixed times or with the sun."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTime, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import Mode, ScheduleSlot, TriggerKind, default_slots
from ...locations import CITIES
from ...schedule import effective_location, resolve, trigger_time
from ...solar import solar_times
from .. import style
from ..picker import pick_wallpaper
from ..widgets import Card, ModeBanner, Page, ThumbLabel, button, icon_button, label, separator

if TYPE_CHECKING:
    from ..context import AppContext

THUMB = QSize(96, 54)


class SlotRow(QFrame):
    def __init__(self, page: TimeOfDayPage, index: int, slot: ScheduleSlot) -> None:
        super().__init__()
        self._page = page
        self.index = index
        self.slot = slot
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(10)

        self.trigger = QComboBox()
        for kind in TriggerKind:
            self.trigger.addItem(kind.label, kind)
        self.trigger.setCurrentIndex(self.trigger.findData(slot.trigger))
        self.trigger.setFixedWidth(130)
        lay.addWidget(self.trigger)

        self.when = QStackedWidget()
        self.when.setFixedWidth(120)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        t = QTime.fromString(slot.time, "HH:mm")
        self.time_edit.setTime(t if t.isValid() else QTime(7, 0))
        self.offset = QSpinBox()
        self.offset.setRange(-720, 720)
        self.offset.setSingleStep(15)
        self.offset.setSuffix(" min")
        self.offset.setPrefix("")
        self.offset.setValue(slot.offset_minutes)
        self.offset.setToolTip("Minutes before (−) or after (+) the sun event")
        self.when.addWidget(self.time_edit)
        self.when.addWidget(self.offset)
        self.when.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.when, 0, Qt.AlignmentFlag.AlignVCenter)

        self.today = label("", "muted")
        self.today.setFixedWidth(110)
        lay.addWidget(self.today)

        self.thumb = ThumbLabel(page.ctx, THUMB)
        self.thumb.set_path(slot.wallpaper)
        lay.addWidget(self.thumb)
        self.choose = button("Choose…" if not slot.wallpaper else "Change…")
        self.choose.clicked.connect(self._choose)
        lay.addWidget(self.choose)
        lay.addStretch(1)
        remove = icon_button("close", "Remove this time")
        remove.clicked.connect(lambda: page.remove_slot(self.index))
        lay.addWidget(remove)

        self._sync_stack()
        self.trigger.currentIndexChanged.connect(self._changed)
        self.time_edit.timeChanged.connect(self._changed)
        self.offset.valueChanged.connect(self._changed)

    def _sync_stack(self) -> None:
        self.when.setCurrentIndex(0 if self.slot.trigger is TriggerKind.TIME else 1)

    def _changed(self) -> None:
        self.slot.trigger = self.trigger.currentData()
        self.slot.time = self.time_edit.time().toString("HH:mm")
        self.slot.offset_minutes = self.offset.value()
        self._sync_stack()
        self._page.slots_edited()

    def _choose(self) -> None:
        path = pick_wallpaper(self._page.ctx, self, current=self.slot.wallpaper)
        if path:
            self.slot.wallpaper = path
            self.thumb.set_path(path)
            self.choose.setText("Change…")
            self._page.slots_edited()


class TimeOfDayPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Time of day", "Change wallpaper at set times or follow the sun: "
                                        "dawn, sunrise, sunset and dusk are calculated offline for your location.")
        self.ctx = ctx
        self._rows: list[SlotRow] = []
        self.content.addWidget(ModeBanner(ctx, Mode.TIME_OF_DAY,
                                          "Time of day mode is off. Turn it on to switch wallpapers on this schedule."))

        # Location -------------------------------------------------------------- #
        loc = Card("Location", "Used for sun-based times here and for automatic theme switching.")
        self._exact = QCheckBox("Use a specific location")
        loc.body.addWidget(self._exact)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self._city = QComboBox()
        self._city.addItem("Pick a city…", None)
        for name, lat, lon in CITIES:
            self._city.addItem(name, (lat, lon))
        self._lat = QDoubleSpinBox()
        self._lat.setRange(-89.9, 89.9)
        self._lat.setDecimals(4)
        self._lat.setSuffix("°")
        self._lon = QDoubleSpinBox()
        self._lon.setRange(-180, 180)
        self._lon.setDecimals(4)
        self._lon.setSuffix("°")
        grid.addWidget(label("City", "small"), 0, 0)
        grid.addWidget(label("Latitude", "small"), 0, 1)
        grid.addWidget(label("Longitude", "small"), 0, 2)
        grid.addWidget(self._city, 1, 0)
        grid.addWidget(self._lat, 1, 1)
        grid.addWidget(self._lon, 1, 2)
        grid.setColumnStretch(3, 1)
        self._loc_fields = QWidget()
        self._loc_fields.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        loc.body.addWidget(self._loc_fields)
        self._sun_info = label("", "muted", wrap=True)
        loc.body.addWidget(self._sun_info)
        self.content.addWidget(loc)

        # Schedule -------------------------------------------------------------- #
        sched = Card("Schedule", "Each wallpaper stays until the next time in the list. "
                                 "Times without a wallpaper are skipped.")
        presets = QHBoxLayout()
        presets.addWidget(label("Presets:", "muted"))
        for text, fn in (("Day && night", self._preset_day_night), ("Four phases", self._preset_four),
                         ("Morning · Afternoon · Evening · Night", self._preset_fixed)):
            b = button(text, flat=True)
            b.clicked.connect(fn)
            presets.addWidget(b)
        presets.addStretch(1)
        sched.body.addLayout(presets)
        header = QHBoxLayout()
        header.setSpacing(10)
        for text, width in (("Starts at", 130), ("Time / offset", 120), ("Today", 110), ("Wallpaper", 0)):
            h = label(text, "small")
            if width:
                h.setFixedWidth(width)
            header.addWidget(h)
        header.addStretch(1)
        sched.body.addLayout(header)
        sched.body.addWidget(separator())
        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(0)
        sched.body.addLayout(self._rows_box)
        add = button("Add time", icon=style.icon("plus"))
        add.clicked.connect(self._add_slot)
        sched.body.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        self.content.addWidget(sched)
        self.content.addStretch(1)

        self._exact.toggled.connect(self._location_changed)
        self._lat.valueChanged.connect(self._location_changed)
        self._lon.valueChanged.connect(self._location_changed)
        self._city.currentIndexChanged.connect(self._city_chosen)
        ctx.store.changed.connect(lambda s: self._load() if s in ("time_of_day", "") else None)
        ctx.controller.wallpaperChanged.connect(self._update_times)
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._update_times)
        self._timer.start()
        self._load()

    @property
    def cfg(self):
        return self.ctx.store.config.time_of_day

    # Loading ---------------------------------------------------------------- #
    def _load(self) -> None:
        cfg = self.cfg
        for w in (self._exact, self._lat, self._lon, self._city):
            w.blockSignals(True)
        exact = cfg.latitude is not None and cfg.longitude is not None
        self._exact.setChecked(exact)
        loc = effective_location(cfg.latitude, cfg.longitude)
        self._lat.setValue(loc.latitude)
        self._lon.setValue(loc.longitude)
        idx = self._city.findText(cfg.location_name) if cfg.location_name else 0
        self._city.setCurrentIndex(max(0, idx))
        for w in (self._exact, self._lat, self._lon, self._city):
            w.blockSignals(False)
        self._loc_fields.setEnabled(exact)
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for i, slot in enumerate(self.cfg.slots):
            row = SlotRow(self, i, slot)
            self._rows.append(row)
            self._rows_box.addWidget(row)
        self._update_times()

    # Location ----------------------------------------------------------------- #
    def _city_chosen(self) -> None:
        data = self._city.currentData()
        if data is None:
            return
        for w in (self._lat, self._lon):
            w.blockSignals(True)
        self._lat.setValue(data[0])
        self._lon.setValue(data[1])
        for w in (self._lat, self._lon):
            w.blockSignals(False)
        self.cfg.location_name = self._city.currentText()
        self._location_changed(from_city=True)

    def _location_changed(self, *_args, from_city: bool = False) -> None:
        cfg = self.cfg
        exact = self._exact.isChecked()
        self._loc_fields.setEnabled(exact)
        if exact:
            cfg.latitude = self._lat.value()
            cfg.longitude = self._lon.value()
            if not from_city:
                cfg.location_name = ""
                self._city.blockSignals(True)
                self._city.setCurrentIndex(0)
                self._city.blockSignals(False)
        else:
            cfg.latitude = cfg.longitude = None
        self.ctx.store.mark_dirty("tod-location")
        self._update_times()

    # Slots ---------------------------------------------------------------------- #
    def slots_edited(self) -> None:
        self.ctx.store.mark_dirty("tod-slots")
        self._update_times()

    def remove_slot(self, index: int) -> None:
        if 0 <= index < len(self.cfg.slots):
            del self.cfg.slots[index]
            self.ctx.store.mark_dirty("tod-slots")
            self._rebuild_rows()

    def _add_slot(self) -> None:
        self.cfg.slots.append(ScheduleSlot(TriggerKind.TIME, time="12:00"))
        self.ctx.store.mark_dirty("tod-slots")
        self._rebuild_rows()

    def _apply_preset(self, slots: list[ScheduleSlot]) -> None:
        # Reuse wallpapers already chosen, in order, so switching presets isn't destructive.
        old = [s.wallpaper for s in self.cfg.slots if s.wallpaper]
        for slot, wp in zip(slots, old, strict=False):
            slot.wallpaper = wp
        self.cfg.slots = slots
        self.ctx.store.mark_dirty("tod-slots")
        self._rebuild_rows()

    def _preset_day_night(self) -> None:
        self._apply_preset([ScheduleSlot(TriggerKind.SUNRISE), ScheduleSlot(TriggerKind.SUNSET)])

    def _preset_four(self) -> None:
        self._apply_preset(default_slots())

    def _preset_fixed(self) -> None:
        self._apply_preset([ScheduleSlot(TriggerKind.TIME, time=t) for t in ("06:00", "12:00", "18:00", "22:00")])

    # Status ---------------------------------------------------------------------- #
    def _update_times(self) -> None:
        cfg = self.cfg
        now = datetime.now().astimezone()
        loc = effective_location(cfg.latitude, cfg.longitude, now)
        st = solar_times(now.date(), loc.latitude, loc.longitude)

        def fmt(dt):
            return dt.strftime("%H:%M") if dt else "—"

        info = (f"Today: dawn {fmt(st.dawn)} · sunrise {fmt(st.sunrise)} · "
                f"sunset {fmt(st.sunset)} · dusk {fmt(st.dusk)}")
        if loc.approximate:
            info += ("\nUsing an estimate from your time zone. Set a specific location for accurate sun times.")
        self._sun_info.setText(info)

        res = resolve(cfg.slots, now, loc, include=lambda s: bool(s.wallpaper))
        active = res.index if res else None
        for row in self._rows:
            t = trigger_time(row.slot, now.date(), loc)
            text = fmt(t) if t else "Doesn't occur"
            if row.index == active:
                row.today.setText(f"{text}  ● now")
                row.today.setStyleSheet("color: palette(highlight); font-weight: 600;")
            else:
                row.today.setText(text)
                row.today.setStyleSheet("")
