"""Qt wrapper around the config: change notifications and debounced saving."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ..config import Config, load_config, normalize, save_config

log = logging.getLogger(__name__)


class ConfigStore(QObject):
    # Emitted with a section name ("library", "slideshow", "time_of_day", "theme",
    # "performance", "general", "mode", "manual") whenever settings change.
    changed = Signal(str)

    def __init__(self, path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.config: Config = load_config(path)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_now)

    def mark_dirty(self, section: str = "") -> None:
        """Settings changed: notify listeners and schedule a save."""
        normalize(self.config)
        self._save_timer.start()
        self.changed.emit(section)

    def save_later(self) -> None:
        """Persist without notifying (runtime state such as slideshow position)."""
        self._save_timer.start()

    def save_now(self) -> None:
        self._save_timer.stop()
        try:
            save_config(self.config, self.path)
        except OSError as exc:
            log.error("Failed to save config: %s", exc)
