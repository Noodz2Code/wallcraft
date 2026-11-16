"""Configuration model and JSON persistence.

Loading is tolerant: unknown keys are ignored, missing keys take defaults and
invalid values fall back to the field default, so an old or hand-edited config
never prevents the app from starting.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import types
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

log = logging.getLogger(__name__)

CONFIG_VERSION = 1


class Mode(str, Enum):
    MANUAL = "manual"
    SLIDESHOW = "slideshow"
    TIME_OF_DAY = "time_of_day"
    THEME = "theme"

    @property
    def label(self) -> str:
        return {
            Mode.MANUAL: "Manual",
            Mode.SLIDESHOW: "Slideshow",
            Mode.TIME_OF_DAY: "Time of day",
            Mode.THEME: "Follow system theme",
        }[self]


class FitMode(str, Enum):
    FILL = "fill"
    FIT = "fit"
    STRETCH = "stretch"
    CENTER = "center"
    TILE = "tile"
    SPAN = "span"

    @property
    def label(self) -> str:
        return self.value.capitalize()


class RuleAction(str, Enum):
    NONE = "none"
    PAUSE = "pause"
    STOP = "stop"

    @property
    def severity(self) -> int:
        return {RuleAction.NONE: 0, RuleAction.PAUSE: 1, RuleAction.STOP: 2}[self]

    @property
    def label(self) -> str:
        return {
            RuleAction.NONE: "Keep playing",
            RuleAction.PAUSE: "Pause",
            RuleAction.STOP: "Stop and show still image",
        }[self]


class TriggerKind(str, Enum):
    TIME = "time"
    DAWN = "dawn"
    SUNRISE = "sunrise"
    NOON = "noon"
    SUNSET = "sunset"
    DUSK = "dusk"

    @property
    def label(self) -> str:
        return {
            TriggerKind.TIME: "Fixed time",
            TriggerKind.DAWN: "Dawn",
            TriggerKind.SUNRISE: "Sunrise",
            TriggerKind.NOON: "Solar noon",
            TriggerKind.SUNSET: "Sunset",
            TriggerKind.DUSK: "Dusk",
        }[self]

    @property
    def is_solar(self) -> bool:
        return self is not TriggerKind.TIME


class Appearance(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class ThemeSchedule(str, Enum):
    SUN = "sun"
    CUSTOM = "custom"


@dataclass
class ScheduleSlot:
    trigger: TriggerKind = TriggerKind.TIME
    time: str = "07:00"  # used when trigger == TIME
    offset_minutes: int = 0  # used for solar triggers
    wallpaper: str = ""


def default_slots() -> list[ScheduleSlot]:
    return [
        ScheduleSlot(TriggerKind.DAWN),
        ScheduleSlot(TriggerKind.SUNRISE, offset_minutes=60),
        ScheduleSlot(TriggerKind.SUNSET, offset_minutes=-60),
        ScheduleSlot(TriggerKind.DUSK),
    ]


@dataclass
class TimeOfDayConfig:
    latitude: float | None = None
    longitude: float | None = None
    location_name: str = ""
    slots: list[ScheduleSlot] = field(default_factory=default_slots)


@dataclass
class SlideshowConfig:
    use_library: bool = True
    items: list[str] = field(default_factory=list)
    interval_minutes: int = 30
    shuffle: bool = True
    include_live: bool = False


@dataclass
class ThemeConfig:
    light_wallpaper: str = ""
    dark_wallpaper: str = ""
    auto_switch: bool = False
    schedule: ThemeSchedule = ThemeSchedule.SUN
    light_time: str = "07:00"
    dark_time: str = "19:00"
    switch_apps: bool = True
    switch_system: bool = True
    appearance: Appearance = Appearance.SYSTEM


@dataclass
class PerformanceConfig:
    on_battery: RuleAction = RuleAction.PAUSE
    on_low_battery: RuleAction = RuleAction.STOP
    low_battery_percent: int = 20
    on_battery_saver: RuleAction = RuleAction.STOP
    on_fullscreen: RuleAction = RuleAction.PAUSE
    on_maximized: RuleAction = RuleAction.PAUSE
    on_locked: RuleAction = RuleAction.PAUSE
    muted: bool = True
    volume: int = 50
    poll_seconds: int = 2


@dataclass
class GeneralConfig:
    fit: FitMode = FitMode.FILL
    start_with_windows: bool = False
    start_minimized: bool = False
    close_to_tray: bool = True
    full_quality_jpeg: bool = False
    tray_hint_shown: bool = False
    check_updates: bool = True
    skipped_version: str = ""


@dataclass
class RuntimeState:
    """Small bits of state that should survive restarts."""

    slideshow_current: str = ""
    slideshow_changed_at: float = 0.0
    last_auto_theme: str = ""
    last_update_check: float = 0.0


@dataclass
class Config:
    version: int = CONFIG_VERSION
    mode: Mode = Mode.MANUAL
    # Manual assignments: monitor id -> path. The key "*" applies to every monitor.
    # Two independent layers: the static Windows wallpaper, and an animated one drawn on top.
    manual: dict[str, str] = field(default_factory=dict)
    manual_live: dict[str, str] = field(default_factory=dict)
    library_folders: list[str] = field(default_factory=list)
    library_files: list[str] = field(default_factory=list)
    library_excluded: list[str] = field(default_factory=list)
    favorites: list[str] = field(default_factory=list)
    slideshow: SlideshowConfig = field(default_factory=SlideshowConfig)
    time_of_day: TimeOfDayConfig = field(default_factory=TimeOfDayConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)
    state: RuntimeState = field(default_factory=RuntimeState)


# --------------------------------------------------------------------------- #
# Generic (de)serialisation
# --------------------------------------------------------------------------- #

_DROP = object()


def _field_default(f) -> Any:
    if f.default is not MISSING:
        return f.default
    if f.default_factory is not MISSING:  # type: ignore[misc]
        return f.default_factory()  # type: ignore[misc]
    return None


def _coerce(tp: Any, value: Any, default: Any) -> Any:
    origin = get_origin(tp)
    try:
        if origin in (Union, types.UnionType):
            if value is None:
                return None if type(None) in get_args(tp) else default
            for arg in get_args(tp):
                if arg is type(None):
                    continue
                result = _coerce(arg, value, _DROP)
                if result is not _DROP:
                    return result
            return default
        if is_dataclass(tp):
            return from_dict(tp, value) if isinstance(value, dict) else default
        if isinstance(tp, type) and issubclass(tp, Enum):
            return tp(value)
        if origin is list:
            if not isinstance(value, list):
                return default
            (item_tp,) = get_args(tp)
            items = (_coerce(item_tp, v, _DROP) for v in value)
            return [v for v in items if v is not _DROP]
        if origin is dict:
            if not isinstance(value, dict):
                return default
            _, val_tp = get_args(tp)
            out = {}
            for k, v in value.items():
                cv = _coerce(val_tp, v, _DROP)
                if cv is not _DROP:
                    out[str(k)] = cv
            return out
        if tp is bool:
            return value if isinstance(value, bool) else default
        if tp is int:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return default
            return int(value)
        if tp is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return default
            return float(value)
        if tp is str:
            return value if isinstance(value, str) else default
    except (TypeError, ValueError):
        return default
    return value


def from_dict(cls: type, data: dict) -> Any:
    hints = get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = _coerce(hints[f.name], data[f.name], _field_default(f))
    return cls(**kwargs)


def to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def normalize(cfg: Config) -> Config:
    """Clamp numeric values into sane ranges and migrate older settings."""
    from .library import is_live

    # Older versions stored animated wallpapers with static ones; move them to their own layer.
    for key, path in list(cfg.manual.items()):
        if path and is_live(path):
            cfg.manual_live.setdefault(key, path)
            del cfg.manual[key]
    cfg.version = CONFIG_VERSION
    cfg.slideshow.interval_minutes = _clamp(cfg.slideshow.interval_minutes, 1, 7 * 24 * 60)
    p = cfg.performance
    p.low_battery_percent = _clamp(p.low_battery_percent, 1, 99)
    p.volume = _clamp(p.volume, 0, 100)
    p.poll_seconds = _clamp(p.poll_seconds, 1, 30)
    tod = cfg.time_of_day
    if tod.latitude is not None:
        tod.latitude = max(-89.9, min(89.9, tod.latitude))
    if tod.longitude is not None:
        tod.longitude = max(-180.0, min(180.0, tod.longitude))
    for slot in tod.slots:
        slot.offset_minutes = _clamp(slot.offset_minutes, -720, 720)
    return cfg


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
    except (OSError, ValueError) as exc:
        backup = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        log.error("Could not read %s (%s); starting with defaults, backup at %s", path, exc, backup)
        try:
            path.replace(backup)
        except OSError:
            pass
        return Config()
    return normalize(from_dict(Config, data))


def save_config(cfg: Config, path: Path) -> None:
    """Write atomically so a crash mid-write never corrupts the config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_dict(cfg), indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
