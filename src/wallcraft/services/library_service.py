"""Library management: folders, files, favourites and background scanning."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QFileSystemWatcher, QObject, QRunnable, QThreadPool, QTimer, Signal

from ..library import MediaItem, classify, norm, scan
from .config_store import ConfigStore

log = logging.getLogger(__name__)


class _ScanSignals(QObject):
    finished = Signal(int, list)


class _ScanJob(QRunnable):
    def __init__(self, generation: int, folders, files, excluded) -> None:
        super().__init__()
        self.signals = _ScanSignals()
        self._args = (list(folders), list(files), list(excluded))
        self._generation = generation

    def run(self) -> None:
        try:
            items = scan(*self._args)
        except Exception:  # noqa: BLE001 - never let a scan crash the app
            log.exception("Library scan failed")
            items = []
        self.signals.finished.emit(self._generation, items)


class LibraryService(QObject):
    changed = Signal()
    scanningChanged = Signal(bool)

    def __init__(self, store: ConfigStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._items: list[MediaItem] = []
        self._by_norm: dict[str, MediaItem] = {}
        self._generation = 0
        self._scanning = False
        self._jobs: list[_ScanJob] = []
        self._fav_keys: set[str] | None = None
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _p: self._rescan_timer.start())
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.setInterval(1500)
        self._rescan_timer.timeout.connect(self.rescan)

    @property
    def cfg(self):
        return self._store.config

    @property
    def items(self) -> list[MediaItem]:
        return self._items

    @property
    def scanning(self) -> bool:
        return self._scanning

    def find(self, path: str) -> MediaItem | None:
        return self._by_norm.get(norm(path)) if path else None

    # Scanning -------------------------------------------------------------- #
    def rescan(self) -> None:
        self._generation += 1
        job = _ScanJob(self._generation, self.cfg.library_folders, self.cfg.library_files,
                       self.cfg.library_excluded)
        job.signals.finished.connect(self._on_scanned)
        self._jobs.append(job)  # keep the signals object alive until it reports
        self._set_scanning(True)
        QThreadPool.globalInstance().start(job)
        self._update_watcher()

    def _on_scanned(self, generation: int, items: list) -> None:
        self._jobs = [j for j in self._jobs if j._generation > generation]
        if generation != self._generation:
            return
        self._items = items
        self._by_norm = {norm(i.path): i for i in items}
        self._set_scanning(False)
        log.info("Library: %d items", len(items))
        self.changed.emit()

    def _set_scanning(self, value: bool) -> None:
        if value != self._scanning:
            self._scanning = value
            self.scanningChanged.emit(value)

    def _update_watcher(self) -> None:
        current = set(self._watcher.directories())
        wanted = {f for f in self.cfg.library_folders if os.path.isdir(f)}
        if current - wanted:
            self._watcher.removePaths(list(current - wanted))
        if wanted - current:
            self._watcher.addPaths(list(wanted - current))

    # Editing ---------------------------------------------------------------- #
    def add_paths(self, paths: list[str]) -> int:
        """Add folders and/or files. Returns how many were accepted."""
        cfg = self.cfg
        folders = {norm(f) for f in cfg.library_folders}
        files = {norm(f) for f in cfg.library_files}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            key = norm(p)
            if key in {norm(x) for x in cfg.library_excluded}:
                cfg.library_excluded = [x for x in cfg.library_excluded if norm(x) != key]
                added += 1
                continue
            if os.path.isdir(p) and key not in folders:
                cfg.library_folders.append(p)
                folders.add(key)
                added += 1
            elif os.path.isfile(p) and classify(p) and key not in files:
                cfg.library_files.append(p)
                files.add(key)
                added += 1
        if added:
            self._store.mark_dirty("library")
            self.rescan()
        return added

    def remove_folder(self, folder: str) -> None:
        key = norm(folder)
        self.cfg.library_folders = [f for f in self.cfg.library_folders if norm(f) != key]
        self._store.mark_dirty("library")
        self.rescan()

    def remove_items(self, paths: list[str]) -> None:
        keys = {norm(p) for p in paths}
        cfg = self.cfg
        cfg.library_files = [f for f in cfg.library_files if norm(f) not in keys]
        folder_keys = [norm(f) for f in cfg.library_folders]
        for p in paths:
            k = norm(p)
            if any(k.startswith(fk.rstrip("\\/") + os.sep) for fk in folder_keys):
                cfg.library_excluded.append(p)
        self._store.mark_dirty("library")
        self.rescan()

    # Favourites --------------------------------------------------------------- #
    def is_favorite(self, path: str) -> bool:
        if self._fav_keys is None:
            self._fav_keys = {norm(f) for f in self.cfg.favorites}
        return norm(path) in self._fav_keys

    def set_favorite(self, path: str, value: bool) -> None:
        key = norm(path)
        favs = [f for f in self.cfg.favorites if norm(f) != key]
        if value:
            favs.append(path)
        self.cfg.favorites = favs
        self._fav_keys = None
        self._store.mark_dirty("favorites")
        self.changed.emit()
