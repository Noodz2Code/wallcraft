"""Dialog shown when a newer Wallcraft release is available."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QTextBrowser, QVBoxLayout, QWidget

from .. import APP_NAME, __version__
from ..updates import Release, install_kind
from .widgets import button, label

if TYPE_CHECKING:
    from ..services.updater import UpdateChecker

DOWNLOAD_LABELS = {
    "installer": "Download installer",
    "portable": "Download portable exe",
    "zip": "Download zip",
}


class UpdateDialog(QDialog):
    def __init__(self, release: Release, updates: UpdateChecker, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} update")
        self.resize(560, 460)
        kind = install_kind()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(label(f"{APP_NAME} {release.version} is available", "h2"))
        released = f"Released {release.published} · " if release.published else ""
        lay.addWidget(label(f"{released}You have {__version__}.", "muted"))

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or "No release notes were published for this version.")
        lay.addWidget(notes, 1)
        hint = {
            "installer": "Run the downloaded installer; it updates Wallcraft in place and keeps your settings.",
            "portable": "Replace your old Wallcraft exe with the downloaded one. Your settings are kept.",
            "zip": "Unpack the zip over your current Wallcraft folder. Your settings are kept.",
        }.get(kind, "You're running from source: update with git pull.")
        lay.addWidget(label(hint, "small", wrap=True))

        row = QHBoxLayout()
        skip = button("Skip this version", flat=True)
        skip.clicked.connect(lambda: (updates.skip(release), self.reject()))
        row.addWidget(skip)
        row.addStretch(1)
        page = button("View on GitHub")
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.page_url)))
        later = button("Later")
        later.clicked.connect(self.reject)
        row.addWidget(page)
        row.addWidget(later)
        if kind in DOWNLOAD_LABELS:
            download = button(DOWNLOAD_LABELS[kind], primary=True)
            download.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(release.download_url(kind))),
                                              self.accept()))
            row.addWidget(download)
            download.setDefault(True)
        lay.addLayout(row)


def show_update_result(parent: QWidget | None, updates: UpdateChecker) -> None:
    """After a manual check: the update dialog, or a short 'up to date' / error message."""
    if updates.update_available and updates.latest is not None:
        UpdateDialog(updates.latest, updates, parent).exec()
    elif updates.last_error:
        QMessageBox.warning(parent, f"{APP_NAME} update", updates.last_error)
    else:
        QMessageBox.information(parent, f"{APP_NAME} update",
                                f"You're up to date. {APP_NAME} {__version__} is the latest version.")
