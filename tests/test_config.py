import json

from wallcraft.config import (
    Config,
    FitMode,
    Mode,
    RuleAction,
    ScheduleSlot,
    TriggerKind,
    load_config,
    save_config,
    to_dict,
)


def test_roundtrip(tmp_path):
    cfg = Config()
    cfg.mode = Mode.TIME_OF_DAY
    cfg.manual = {"*": "C:/a.jpg"}
    cfg.general.fit = FitMode.SPAN
    cfg.time_of_day.latitude = 51.5
    cfg.time_of_day.slots = [ScheduleSlot(TriggerKind.SUNSET, offset_minutes=-30, wallpaper="x.mp4")]
    path = tmp_path / "config.json"
    save_config(cfg, path)
    loaded = load_config(path)
    assert to_dict(loaded) == to_dict(cfg)
    assert loaded.time_of_day.slots[0].trigger is TriggerKind.SUNSET


def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.mode is Mode.MANUAL
    assert len(cfg.time_of_day.slots) == 4


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "mode": "warp-speed",
        "manual": {"*": 5, "m1": "ok.png"},
        "favorites": ["a", 3, "b"],
        "slideshow": {"interval_minutes": "soon", "shuffle": "yes"},
        "performance": {"on_battery": "stop", "volume": 500, "poll_seconds": 0},
        "time_of_day": {"latitude": None, "longitude": 12, "slots": [{"trigger": "sunrise"}, "junk"]},
        "unknown_key": True,
    }))
    cfg = load_config(path)
    assert cfg.mode is Mode.MANUAL
    assert cfg.manual == {"m1": "ok.png"}
    assert cfg.favorites == ["a", "b"]
    assert cfg.slideshow.interval_minutes == 30
    assert cfg.slideshow.shuffle is True
    assert cfg.performance.on_battery is RuleAction.STOP
    assert cfg.performance.volume == 100
    assert cfg.performance.poll_seconds == 1
    assert cfg.time_of_day.latitude is None
    assert cfg.time_of_day.longitude == 12.0
    assert len(cfg.time_of_day.slots) == 1


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    cfg = load_config(path)
    assert isinstance(cfg, Config)
    assert not path.exists()
    assert len(list(tmp_path.glob("config.json.corrupt-*"))) == 1


def test_animated_manual_entries_migrate_to_their_own_layer(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"manual": {"*": "C:/w/a.jpg", "m2": "C:/w/loop.mp4"}}))
    cfg = load_config(path)
    assert cfg.manual == {"*": "C:/w/a.jpg"}
    assert cfg.manual_live == {"m2": "C:/w/loop.mp4"}
