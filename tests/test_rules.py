from wallcraft.config import PerformanceConfig, RuleAction
from wallcraft.rules import SystemState, evaluate


def test_nothing_matches_keeps_playing():
    d = evaluate(PerformanceConfig(), SystemState(), "m1")
    assert d.action is RuleAction.NONE and d.reasons == ()


def test_on_battery_pauses():
    d = evaluate(PerformanceConfig(), SystemState(has_battery=True, on_battery=True, battery_percent=80), "m1")
    assert d.action is RuleAction.PAUSE
    assert d.reasons == ("on battery",)


def test_low_battery_escalates_to_stop():
    state = SystemState(has_battery=True, on_battery=True, battery_percent=15)
    d = evaluate(PerformanceConfig(low_battery_percent=20), state, "m1")
    assert d.action is RuleAction.STOP
    assert d.reasons == ("battery at 15%",)


def test_low_battery_ignored_when_plugged_in():
    state = SystemState(has_battery=True, on_battery=False, battery_percent=5)
    assert evaluate(PerformanceConfig(), state, "m1").action is RuleAction.NONE


def test_fullscreen_is_per_monitor():
    state = SystemState(fullscreen_monitors=frozenset({"m2"}))
    perf = PerformanceConfig()
    assert evaluate(perf, state, "m1").action is RuleAction.NONE
    assert evaluate(perf, state, "m2").action is RuleAction.PAUSE


def test_maximized_rule_can_be_disabled():
    state = SystemState(maximized_monitors=frozenset({"m1"}))
    assert evaluate(PerformanceConfig(on_maximized=RuleAction.NONE), state, "m1").action is RuleAction.NONE


def test_same_severity_collects_reasons():
    state = SystemState(on_battery=True, battery_percent=90, session_locked=True)
    d = evaluate(PerformanceConfig(), state, "m1")
    assert d.action is RuleAction.PAUSE
    assert set(d.reasons) == {"on battery", "screen locked"}


def test_battery_saver_stop():
    d = evaluate(PerformanceConfig(), SystemState(battery_saver=True), "m1")
    assert d.action is RuleAction.STOP
