"""Parse `pmset -g batt` (kept separate from the PyObjC backend so it can be tested anywhere)."""

from __future__ import annotations

import re


def parse_pmset(text: str) -> tuple[bool, bool, int | None]:
    """(has_battery, on_battery, percent)."""
    m = re.search(r"InternalBattery[^\n]*?(\d+)%", text)
    if not m:
        return False, False, None
    return True, "Battery Power" in text, int(m.group(1))
