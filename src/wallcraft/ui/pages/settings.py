"""Settings page: startup, tray behaviour, data and about."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QMessageBox

from ... import APP_NAME, REPO_URL, __version__
from ...config import FitMode
from ...paths import config_dir, is_portable, log_dir
from ..widgets import Card, Page, button, label

if TYPE_CHECKING:
    from ..context import AppContext

log = logging.getLogger(__name__)


class SettingsPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Settings")
        self._ctx = ctx

        startup = Card("Startup and tray")
        self._autostart = QCheckBox("Start Wallcraft when I sign in to Windows")
        self._minimized = QCheckBox("Start minimized to the tray")
        self._close_to_tray = QCheckBox("Keep running in the tray when the window is closed")
        for w in (self._autostart, self._minimized, self._close_to_tray):
            startup.body.addWidget(w)
        if not ctx.backend.supports_autostart:
            self._autostart.setEnabled(False)
            self._autostart.setToolTip("Not available on this platform")
        self.content.addWidget(startup)

        display = Card("Display")
        row = QHBoxLayout()
        row.addWidget(label("Fit wallpapers"))
        self._fit = QComboBox()
        for fit in FitMode:
            self._fit.addItem(fit.label, fit)
        row.addWidget(self._fit)
        row.addStretch(1)
        display.body.addLayout(row)
        self._jpeg = QCheckBox("Keep JPEG wallpapers at full quality")
        display.body.addWidget(self._jpeg)
        display.body.addWidget(label("Windows normally re-compresses JPEG wallpapers to 85% quality. Takes "
                                     "effect the next time a wallpaper is set.", "small", wrap=True))
        self.content.addWidget(display)

        data = Card("Data")
        where = "portable folder next to the app" if is_portable() else str(config_dir())
        data.body.addWidget(label(f"Settings are stored in {where}.", "muted", wrap=True))
        row = QHBoxLayout()
        open_cfg = button("Open settings folder")
        open_cfg.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir()))))
        open_logs = button("Open logs")
        open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        clear = button("Clear thumbnail cache")
        clear.clicked.connect(self._clear_cache)
        rescan = button("Rescan library")
        rescan.clicked.connect(ctx.library.rescan)
        for b in (open_cfg, open_logs, clear, rescan):
            row.addWidget(b)
        row.addStretch(1)
        data.body.addLayout(row)
        self.content.addWidget(data)

        about = Card(f"About {APP_NAME}")
        about.body.addWidget(label(f"Version {__version__} · Free and open source under the MIT License.",
                                   "muted"))
        row = QHBoxLayout()
        gh = button("Project on GitHub")
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        issue = button("Report a problem")
        issue.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"{REPO_URL}/issues/new/choose")))
        releases = button("Check for updates")
        releases.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"{REPO_URL}/releases/latest")))
        for b in (gh, issue, releases):
            row.addWidget(b)
        row.addStretch(1)
        about.body.addLayout(row)
        self.content.addWidget(about)
        self.content.addStretch(1)

        self._autostart.toggled.connect(self._set_autostart)
        for w in (self._minimized, self._close_to_tray, self._jpeg):
            w.toggled.connect(self._save)
        self._fit.currentIndexChanged.connect(self._save)
        ctx.store.changed.connect(lambda s: self._load() if s in ("general", "") else None)
        self._load()

    def _widgets(self):
        return (self._autostart, self._minimized, self._close_to_tray, self._jpeg, self._fit)

    def _load(self) -> None:
        g = self._ctx.store.config.general
        for w in self._widgets():
            w.blockSignals(True)
        actual = self._ctx.backend.autostart_enabled() if self._ctx.backend.supports_autostart else False
        self._autostart.setChecked(actual)
        self._minimized.setChecked(g.start_minimized)
        self._close_to_tray.setChecked(g.close_to_tray)
        self._jpeg.setChecked(g.full_quality_jpeg)
        self._fit.setCurrentIndex(self._fit.findData(g.fit))
        for w in self._widgets():
            w.blockSignals(False)

    def _save(self) -> None:
        g = self._ctx.store.config.general
        g.start_minimized = self._minimized.isChecked()
        g.close_to_tray = self._close_to_tray.isChecked()
        g.full_quality_jpeg = self._jpeg.isChecked()
        g.fit = self._fit.currentData()
        self._ctx.store.mark_dirty("general")

    def _set_autostart(self, enabled: bool) -> None:
        try:
            self._ctx.backend.set_autostart(enabled)
            self._ctx.store.config.general.start_with_windows = enabled
            self._ctx.store.mark_dirty("general")
        except (OSError, NotImplementedError) as exc:
            log.error("Changing autostart failed: %s", exc)
            QMessageBox.warning(self, APP_NAME, f"Couldn't change the startup setting:\n{exc}")
            self._load()

    def _clear_cache(self) -> None:
        self._ctx.thumbs.clear()
        self._ctx.controller.message.emit("Thumbnail cache cleared.")
        self._ctx.library.changed.emit()
