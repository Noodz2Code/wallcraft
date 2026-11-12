"""Performance and battery rules for live wallpapers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import PerformanceConfig, RuleAction


@dataclass(frozen=True)
class SystemState:
    has_battery: bool = False
    on_battery: bool = False
    battery_percent: int | None = None
    battery_saver: bool = False
    session_locked: bool = False
    fullscreen_monitors: frozenset[str] = field(default_factory=frozenset)
    maximized_monitors: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Decision:
    action: RuleAction = RuleAction.NONE
    reasons: tuple[str, ...] = ()

    def combine(self, action: RuleAction, reason: str) -> Decision:
        if action is RuleAction.NONE:
            return self
        if action.severity > self.action.severity:
            return Decision(action, (reason,))
        if action.severity == self.action.severity:
            return Decision(self.action, self.reasons + (reason,))
        return self


def evaluate(perf: PerformanceConfig, state: SystemState, monitor_id: str) -> Decision:
    """The strongest action among all matching rules (stop > pause > keep playing)."""
    d = Decision()
    if state.session_locked:
        d = d.combine(perf.on_locked, "screen locked")
    if state.on_battery:
        d = d.combine(perf.on_battery, "on battery")
        if state.battery_percent is not None and state.battery_percent <= perf.low_battery_percent:
            d = d.combine(perf.on_low_battery, f"battery at {state.battery_percent}%")
    if state.battery_saver:
        d = d.combine(perf.on_battery_saver, "battery saver on")
    if monitor_id in state.fullscreen_monitors:
        d = d.combine(perf.on_fullscreen, "fullscreen app")
    elif monitor_id in state.maximized_monitors:
        d = d.combine(perf.on_maximized, "window maximized")
    return d
