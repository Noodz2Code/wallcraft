"""Background update checks: automatically once a day, or when the user asks."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from .. import __version__
from ..updates import Release, UpdateError, fetch_latest, is_newer
from .config_store import ConfigStore

log = logging.getLogger(__name__)

AUTO_INTERVAL_S = 24 * 3600
FIRST_CHECK_DELAY_MS = 20_000  # don't compete with startup work


class _Signals(QObject):
    done = Signal(object, str, bool)  # Release | None, error text, manual


class _CheckJob(QRunnable):
    def __init__(self, signals: _Signals, manual: bool, url: str | None) -> None:
        super().__init__()
        self._signals, self._manual, self._url = signals, manual, url

    def run(self) -> None:
        try:
            self._signals.done.emit(fetch_latest(self._url), "", self._manual)
        except UpdateError as exc:
            self._signals.done.emit(None, str(exc), self._manual)
        except Exception as exc:  # noqa: BLE001 - never crash over an update check
            log.exception("Update check failed")
            self._signals.done.emit(None, f"Update check failed: {exc}", self._manual)


class UpdateChecker(QObject):
    checking = Signal()
    available = Signal(object, bool)   # Release, manual
    up_to_date = Signal(object, bool)  # latest published Release, manual
    failed = Signal(str, bool)         # message, manual
    finished = Signal()                # after every check, whatever the outcome

    def __init__(self, store: ConfigStore, url: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._url = url
        self._busy = False
        self._job: _CheckJob | None = None
        self.latest: Release | None = None
        self.last_error = ""
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._timer = QTimer(self)
        self._timer.setInterval(3600 * 1000)  # re-evaluate hourly; checks at most daily
        self._timer.timeout.connect(self._auto_check)

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def update_available(self) -> bool:
        return self.latest is not None and is_newer(self.latest.version)

    def start(self) -> None:
        QTimer.singleShot(FIRST_CHECK_DELAY_MS, self, self._auto_check)
        self._timer.start()

    def _auto_check(self) -> None:
        cfg = self._store.config
        if cfg.general.check_updates and time.time() - cfg.state.last_update_check >= AUTO_INTERVAL_S:
            self.check(manual=False)

    def check(self, manual: bool = True) -> None:
        if self._busy:
            return
        self._busy = True
        self.checking.emit()
        # Keep a Python reference while the job runs; otherwise PySide may collect the wrapper
        # under the running thread and crash.
        self._job = _CheckJob(self._signals, manual, self._url)
        self._job.setAutoDelete(False)
        QThreadPool.globalInstance().start(self._job)

    def skip(self, release: Release) -> None:
        self._store.config.general.skipped_version = release.version
        self._store.mark_dirty("updates")

    def _on_done(self, release: Release | None, error: str, manual: bool) -> None:
        try:
            self._report(release, error, manual)
        finally:
            self.finished.emit()

    def _report(self, release: Release | None, error: str, manual: bool) -> None:
        self._busy = False
        self._job = None
        self._store.config.state.last_update_check = time.time()
        self._store.save_later()
        if release is None:
            self.last_error = error
            log.info("Update check failed: %s", error)
            self.failed.emit(error, manual)
            return
        self.last_error = ""
        self.latest = release
        if is_newer(release.version):
            log.info("Update available: %s (running %s)", release.version, __version__)
            skipped = release.version == self._store.config.general.skipped_version
            if manual or not skipped:
                self.available.emit(release, manual)
        else:
            log.info("Wallcraft is up to date (%s)", __version__)
            self.up_to_date.emit(release, manual)
