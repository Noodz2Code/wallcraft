from datetime import date, datetime, timedelta, timezone

import pytest

from wallcraft.solar import solar_times, sun_always_up


def tz(hours: float) -> timezone:
    return timezone(timedelta(hours=hours))


def assert_close(actual: datetime, hh: int, mm: int, tolerance_min: int = 4) -> None:
    expected = actual.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff = abs((actual - expected).total_seconds()) / 60
    assert diff <= tolerance_min, f"{actual:%H:%M} vs expected {hh:02d}:{mm:02d}"


@pytest.mark.parametrize(
    "name, lat, lon, day, offset, sunrise, sunset",
    [
        ("London midsummer", 51.5074, -0.1278, date(2024, 6, 21), 1, (4, 43), (21, 21)),
        ("New York midwinter", 40.7128, -74.0060, date(2024, 12, 21), -5, (7, 16), (16, 32)),
        ("Sydney June", -33.8688, 151.2093, date(2024, 6, 21), 10, (7, 0), (16, 54)),
        ("Singapore equinox", 1.3521, 103.8198, date(2024, 3, 20), 8, (7, 9), (19, 15)),
    ],
)
def test_sunrise_sunset_known_values(name, lat, lon, day, offset, sunrise, sunset):
    st = solar_times(day, lat, lon, tz(offset))
    assert st.sunrise is not None and st.sunset is not None, name
    assert st.sunrise.date() == day and st.sunset.date() == day
    assert_close(st.sunrise, *sunrise)
    assert_close(st.sunset, *sunset)
    assert st.dawn < st.sunrise < st.noon < st.sunset < st.dusk


def test_events_land_on_requested_local_day_far_from_utc():
    # Auckland is UTC+13 in summer: the UTC calculation crosses the date line.
    day = date(2024, 1, 15)
    st = solar_times(day, -36.8485, 174.7633, tz(13))
    assert st.sunrise.date() == day
    assert st.sunset.date() == day
    assert_close(st.sunrise, 6, 15, tolerance_min=6)
    assert_close(st.sunset, 20, 40, tolerance_min=6)


def test_polar_day_and_night():
    tromso = (69.6492, 18.9553)
    summer = solar_times(date(2024, 6, 21), *tromso, tz(2))
    assert summer.sunrise is None and summer.sunset is None
    assert sun_always_up(date(2024, 6, 21), *tromso) is True
    assert sun_always_up(date(2024, 12, 21), *tromso) is False
    assert sun_always_up(date(2024, 3, 20), *tromso) is None
