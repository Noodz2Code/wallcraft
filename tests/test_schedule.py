from datetime import datetime, timedelta, timezone

from wallcraft.config import ScheduleSlot, ThemeSchedule, TriggerKind
from wallcraft.schedule import Location, effective_location, parse_hhmm, resolve, theme_at

TZ = timezone(timedelta(hours=1))
LONDON = Location(51.5074, -0.1278)


def at(h: int, m: int = 0, day: int = 21) -> datetime:
    return datetime(2024, 6, day, h, m, tzinfo=TZ)


def fixed(t: str, wp: str) -> ScheduleSlot:
    return ScheduleSlot(TriggerKind.TIME, time=t, wallpaper=wp)


def test_parse_hhmm():
    assert parse_hhmm("07:30").hour == 7
    assert parse_hhmm("bad") is None
    assert parse_hhmm("25:00") is None


def test_fixed_slots_pick_latest_past_trigger():
    slots = [fixed("07:00", "morning"), fixed("12:00", "noon"), fixed("20:00", "night")]
    res = resolve(slots, at(13), LONDON, TZ)
    assert slots[res.index].wallpaper == "noon"
    assert res.next_change == at(20)
    assert res.next_index == 2


def test_schedule_wraps_past_midnight():
    slots = [fixed("07:00", "day"), fixed("20:00", "night")]
    res = resolve(slots, at(3), LONDON, TZ)
    assert slots[res.index].wallpaper == "night"
    assert res.started == at(20, day=20)
    assert res.next_change == at(7)


def test_slot_order_in_list_does_not_matter():
    slots = [fixed("20:00", "night"), fixed("07:00", "day")]
    assert slots[resolve(slots, at(10), LONDON, TZ).index].wallpaper == "day"


def test_solar_slots_with_offsets():
    slots = [
        ScheduleSlot(TriggerKind.SUNRISE, wallpaper="day"),
        ScheduleSlot(TriggerKind.SUNSET, offset_minutes=-60, wallpaper="evening"),
        ScheduleSlot(TriggerKind.DUSK, wallpaper="night"),
    ]
    # London sunset on 21 June is ~21:21 BST, so the evening slot starts ~20:21.
    assert slots[resolve(slots, at(12), LONDON, TZ).index].wallpaper == "day"
    assert slots[resolve(slots, at(20, 40), LONDON, TZ).index].wallpaper == "evening"
    assert slots[resolve(slots, at(23, 30), LONDON, TZ).index].wallpaper == "night"
    assert slots[resolve(slots, at(2), LONDON, TZ).index].wallpaper == "night"


def test_include_filter_skips_empty_slots():
    slots = [fixed("07:00", ""), fixed("20:00", "night")]
    res = resolve(slots, at(10), LONDON, TZ, include=lambda s: bool(s.wallpaper))
    assert slots[res.index].wallpaper == "night"


def test_resolve_returns_none_without_events():
    polar = Location(78.2, 15.6)  # Svalbard, polar day in June
    slots = [ScheduleSlot(TriggerKind.SUNRISE, wallpaper="x")]
    assert resolve(slots, at(12), polar, TZ) is None


def test_theme_by_custom_times():
    assert theme_at(at(8), ThemeSchedule.CUSTOM, "07:00", "19:00", LONDON, TZ) == "light"
    assert theme_at(at(22), ThemeSchedule.CUSTOM, "07:00", "19:00", LONDON, TZ) == "dark"
    assert theme_at(at(5), ThemeSchedule.CUSTOM, "07:00", "19:00", LONDON, TZ) == "dark"


def test_theme_by_sun():
    assert theme_at(at(12), ThemeSchedule.SUN, "", "", LONDON, TZ) == "light"
    assert theme_at(at(23), ThemeSchedule.SUN, "", "", LONDON, TZ) == "dark"
    svalbard = Location(78.2, 15.6)
    assert theme_at(at(1), ThemeSchedule.SUN, "", "", svalbard, TZ) == "light"
    winter = datetime(2024, 12, 21, 12, tzinfo=TZ)
    assert theme_at(winter, ThemeSchedule.SUN, "", "", svalbard, TZ) == "dark"


def test_effective_location_estimates_from_utc_offset():
    loc = effective_location(None, None, datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=-5))))
    assert loc.approximate
    assert loc.longitude == -75
    exact = effective_location(10.0, 20.0)
    assert not exact.approximate and exact.latitude == 10.0
