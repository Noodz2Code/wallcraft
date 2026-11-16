"""Settings page: startup, tray behaviour, data and about."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QMessageBox

from ... import APP_NAME, REPO_URL, __version__
from ...config import FitMode
from ...paths import config_dir, is_portable, log_dir
from .. import style
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

        updates = Card("Updates")
        self._update_status = label("", "muted", wrap=True)
        updates.body.addWidget(self._update_status)
        row = QHBoxLayout()
        self._check_now = button("Check for updates", icon=style.icon("refresh"))
        self._check_now.clicked.connect(lambda: ctx.updates and ctx.updates.check(manual=True))
        self._whats_new = button("See what's new", primary=True)
        self._whats_new.clicked.connect(self._show_update)
        row.addWidget(self._check_now)
        row.addWidget(self._whats_new)
        row.addStretch(1)
        updates.body.addLayout(row)
        self._auto_updates = QCheckBox("Check for updates automatically (once a day)")
        updates.body.addWidget(self._auto_updates)
        updates.body.addWidget(label("Wallcraft only asks GitHub for the latest version number. Nothing about "
                                     "you or your computer is sent, and nothing is installed without you.",
                                     "small", wrap=True))
        self.content.addWidget(updates)

        about = Card(f"About {APP_NAME}")
        about.body.addWidget(label(f"Version {__version__} · Free and open source under the MIT License.",
                                   "muted"))
        row = QHBoxLayout()
        gh = button("Project on GitHub")
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        issue = button("Report a problem")
        issue.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"{REPO_URL}/issues/new/choose")))
        for b in (gh, issue):
            row.addWidget(b)
        row.addStretch(1)
        about.body.addLayout(row)
        self.content.addWidget(about)
        self.content.addStretch(1)

        self._autostart.toggled.connect(self._set_autostart)
        for w in (self._minimized, self._close_to_tray, self._jpeg):
            w.toggled.connect(self._save)
        self._fit.currentIndexChanged.connect(self._save)
        self._auto_updates.toggled.connect(self._save)
        if ctx.updates is not None:
            ctx.updates.checking.connect(self._refresh_update_status)
            ctx.updates.finished.connect(self._refresh_update_status)
        self._refresh_update_status()
        ctx.store.changed.connect(lambda s: self._load() if s in ("general", "") else None)
        self._load()

    def _widgets(self):
        return (self._autostart, self._minimized, self._close_to_tray, self._jpeg, self._fit,
                self._auto_updates)

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
        self._auto_updates.setChecked(g.check_updates)
        for w in self._widgets():
            w.blockSignals(False)

    def _save(self) -> None:
        g = self._ctx.store.config.general
        g.start_minimized = self._minimized.isChecked()
        g.close_to_tray = self._close_to_tray.isChecked()
        g.full_quality_jpeg = self._jpeg.isChecked()
        g.fit = self._fit.currentData()
        g.check_updates = self._auto_updates.isChecked()
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

    def _show_update(self) -> None:
        from ..update_dialog import UpdateDialog

        u = self._ctx.updates
        if u is not None and u.latest is not None:
            UpdateDialog(u.latest, u, self).exec()

    def _refresh_update_status(self) -> None:
        u = self._ctx.updates
        if u is None:
            self._update_status.setText("Update checks aren't available.")
            self._check_now.setEnabled(False)
            self._whats_new.setVisible(False)
            return
        self._check_now.setEnabled(not u.busy)
        self._whats_new.setVisible(u.update_available)
        last = self._ctx.store.config.state.last_update_check
        checked = (f" Last checked {datetime.fromtimestamp(last).strftime('%d %b %Y, %H:%M')}."
                   if last else "")
        if u.busy:
            text = "Checking for updates…"
        elif u.update_available:
            text = f"{APP_NAME} {u.latest.version} is available. You have {__version__}."
        elif u.last_error:
            text = u.last_error + checked
        elif u.latest is not None:
            text = f"You're up to date ({__version__}).{checked}"
        else:
            text = f"You have {APP_NAME} {__version__}." + (checked or " Not checked yet.")
        self._update_status.setText(text)

    def _clear_cache(self) -> None:
        self._ctx.thumbs.clear()
        self._ctx.controller.message.emit("Thumbnail cache cleared.")
        self._ctx.library.changed.emit()
