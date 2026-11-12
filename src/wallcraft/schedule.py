"""Time-of-day scheduling: which slot is active right now and when the next change happens."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .config import ScheduleSlot, ThemeSchedule, TriggerKind
from .solar import solar_times, sun_always_up

APPROX_LATITUDE = 40.0


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    approximate: bool = False


def effective_location(lat: float | None, lon: float | None, now: datetime | None = None) -> Location:
    """Use the configured location, or estimate one from the UTC offset."""
    if lat is not None and lon is not None:
        return Location(lat, lon)
    now = now or datetime.now().astimezone()
    offset = now.utcoffset() or timedelta(0)
    est_lon = max(-180.0, min(180.0, offset.total_seconds() / 3600 * 15))
    return Location(APPROX_LATITUDE, est_lon, approximate=True)


def parse_hhmm(value: str) -> time | None:
    try:
        hh, mm = value.strip().split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def _local(day: date, t: time, tz: tzinfo | None) -> datetime:
    if tz is not None:
        return datetime.combine(day, t, tzinfo=tz)
    return datetime.combine(day, t).astimezone()  # system local, DST-aware


def trigger_time(slot: ScheduleSlot, day: date, loc: Location, tz: tzinfo | None = None) -> datetime | None:
    if slot.trigger is TriggerKind.TIME:
        t = parse_hhmm(slot.time)
        return _local(day, t, tz) if t else None
    st = solar_times(day, loc.latitude, loc.longitude, tz)
    base = getattr(st, slot.trigger.value)
    if base is None:
        return None
    return base + timedelta(minutes=slot.offset_minutes)


@dataclass(frozen=True)
class Resolution:
    index: int
    started: datetime
    next_change: datetime | None
    next_index: int | None


def resolve(
    slots: Sequence[ScheduleSlot],
    now: datetime,
    loc: Location,
    tz: tzinfo | None = None,
    include: Callable[[ScheduleSlot], bool] = lambda s: True,
) -> Resolution | None:
    """Find the slot whose trigger most recently fired.

    Looks at yesterday/today/tomorrow so schedules wrap around midnight correctly.
    Returns None when no slot fired in that window (e.g. only sun triggers during polar night).
    """
    events: list[tuple[datetime, int]] = []
    for shift in (-1, 0, 1):
        day = now.date() + timedelta(days=shift)
        for i, slot in enumerate(slots):
            if not include(slot):
                continue
            t = trigger_time(slot, day, loc, tz)
            if t is not None:
                events.append((t, i))
    events.sort(key=lambda e: (e[0], e[1]))
    past = [e for e in events if e[0] <= now]
    if not past:
        return None
    current = past[-1]
    future = [e for e in events if e[0] > now]
    nxt = future[0] if future else None
    return Resolution(
        index=current[1],
        started=current[0],
        next_change=nxt[0] if nxt else None,
        next_index=nxt[1] if nxt else None,
    )


def theme_at(
    now: datetime,
    schedule: ThemeSchedule,
    light_time: str,
    dark_time: str,
    loc: Location,
    tz: tzinfo | None = None,
) -> str:
    """Return "light" or "dark" for the automatic Windows theme switch."""
    if schedule is ThemeSchedule.SUN:
        slots = [ScheduleSlot(TriggerKind.SUNRISE, wallpaper="light"),
                 ScheduleSlot(TriggerKind.SUNSET, wallpaper="dark")]
    else:
        slots = [ScheduleSlot(TriggerKind.TIME, time=light_time, wallpaper="light"),
                 ScheduleSlot(TriggerKind.TIME, time=dark_time, wallpaper="dark")]
    res = resolve(slots, now, loc, tz)
    if res is not None and schedule is ThemeSchedule.SUN:
        # Near the poles the last event may be days old; trust the sun's actual state.
        up = sun_always_up(now.date(), loc.latitude, loc.longitude)
        if up is not None:
            return "light" if up else "dark"
    if res is None:
        up = sun_always_up(now.date(), loc.latitude, loc.longitude)
        return "dark" if up is False else "light"
    return slots[res.index].wallpaper
