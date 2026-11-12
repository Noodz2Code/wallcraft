"""Offline sunrise/sunset calculation (no network or location services needed).

Based on the Almanac for Computers algorithm (U.S. Naval Observatory, 1990),
accurate to within a couple of minutes for latitudes below the polar circles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

ZENITH_OFFICIAL = 90.833  # sunrise / sunset
ZENITH_CIVIL = 96.0  # dawn / dusk (civil twilight)

ALWAYS_UP = "always_up"
ALWAYS_DOWN = "always_down"


def _sin(d: float) -> float:
    return math.sin(math.radians(d))


def _cos(d: float) -> float:
    return math.cos(math.radians(d))


def _sun_event_utc(day: date, lat: float, lon: float, zenith: float, rising: bool):
    """Return a UTC datetime, or ALWAYS_UP / ALWAYS_DOWN when the event doesn't happen."""
    lat = max(-89.9, min(89.9, lat))
    n = day.timetuple().tm_yday
    lng_hour = lon / 15.0
    t = n + ((6 - lng_hour) / 24) if rising else n + ((18 - lng_hour) / 24)

    m = 0.9856 * t - 3.289  # sun's mean anomaly
    lon_sun = (m + 1.916 * _sin(m) + 0.020 * _sin(2 * m) + 282.634) % 360

    ra = math.degrees(math.atan(0.91764 * math.tan(math.radians(lon_sun)))) % 360
    ra += math.floor(lon_sun / 90) * 90 - math.floor(ra / 90) * 90
    ra /= 15

    sin_dec = 0.39782 * _sin(lon_sun)
    cos_dec = math.cos(math.asin(sin_dec))
    cos_h = (_cos(zenith) - sin_dec * _sin(lat)) / (cos_dec * _cos(lat))
    if cos_h > 1:
        return ALWAYS_DOWN
    if cos_h < -1:
        return ALWAYS_UP

    h = 360 - math.degrees(math.acos(cos_h)) if rising else math.degrees(math.acos(cos_h))
    h /= 15
    local_mean = h + ra - 0.06571 * t - 6.622
    ut = (local_mean - lng_hour) % 24
    return datetime.combine(day, time(0), tzinfo=timezone.utc) + timedelta(hours=ut)


def _to_local(dt: datetime, tz: tzinfo | None) -> datetime:
    return dt.astimezone(tz) if tz is not None else dt.astimezone()


def sun_event(
    day: date, lat: float, lon: float, zenith: float, rising: bool, tz: tzinfo | None = None
) -> datetime | None:
    """Local time of the event on the given local calendar day, or None if it doesn't occur."""
    for shift in (0, -1, 1):
        ev = _sun_event_utc(day + timedelta(days=shift), lat, lon, zenith, rising)
        if not isinstance(ev, datetime):
            continue
        local = _to_local(ev, tz)
        if local.date() == day:
            return local
    return None


def sun_always_up(day: date, lat: float, lon: float) -> bool | None:
    """True for midnight sun, False for polar night, None when the sun rises and sets normally."""
    ev = _sun_event_utc(day, lat, lon, ZENITH_OFFICIAL, rising=True)
    if ev == ALWAYS_UP:
        return True
    if ev == ALWAYS_DOWN:
        return False
    return None


@dataclass(frozen=True)
class SolarTimes:
    dawn: datetime | None
    sunrise: datetime | None
    noon: datetime | None
    sunset: datetime | None
    dusk: datetime | None


def solar_times(day: date, lat: float, lon: float, tz: tzinfo | None = None) -> SolarTimes:
    sunrise = sun_event(day, lat, lon, ZENITH_OFFICIAL, True, tz)
    sunset = sun_event(day, lat, lon, ZENITH_OFFICIAL, False, tz)
    noon = sunrise + (sunset - sunrise) / 2 if sunrise and sunset and sunset > sunrise else None
    return SolarTimes(
        dawn=sun_event(day, lat, lon, ZENITH_CIVIL, True, tz),
        sunrise=sunrise,
        noon=noon,
        sunset=sunset,
        dusk=sun_event(day, lat, lon, ZENITH_CIVIL, False, tz),
    )
