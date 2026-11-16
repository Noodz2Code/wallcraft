"""Thumbnail generation with memory + disk caching.

Images are decoded on a thread pool at reduced size (QImageReader.setScaledSize
lets the JPEG decoder skip work). Videos and animated images go through the PosterService.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

from ..library import Kind, classify
from .posters import PosterService, cache_key

log = logging.getLogger(__name__)

THUMB_SIZE = QSize(320, 200)
MEMORY_LIMIT = 800


def crop_to(image: QImage, size: QSize) -> QImage:
    scaled = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - size.width()) // 2
    y = (scaled.height() - size.height()) // 2
    return scaled.copy(QRect(x, y, size.width(), size.height()))


class _Signals(QObject):
    done = Signal(str, QImage)


class _ImageJob(QRunnable):
    def __init__(self, path: str, out: Path, signals: _Signals) -> None:
        super().__init__()
        self._path, self._out, self._signals = path, out, signals

    def run(self) -> None:
        image = QImage()
        try:
            reader = QImageReader(self._path)
            reader.setAutoTransform(True)
            src = reader.size()
            if src.isValid():
                reader.setScaledSize(src.scaled(THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
            image = reader.read()
            if not image.isNull():
                image = crop_to(image, THUMB_SIZE)
                self._out.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(self._out), "JPG", 85)
        except Exception:  # noqa: BLE001
            log.exception("Thumbnail failed for %s", self._path)
        self._signals.done.emit(self._path, image)


class ThumbnailCache(QObject):
    ready = Signal(str)

    def __init__(self, out_dir: Path, posters: PosterService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dir = out_dir
        self._posters = posters
        self._memory: OrderedDict[str, QPixmap] = OrderedDict()
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, QThreadPool.globalInstance().maxThreadCount() // 2))

    def get(self, path: str) -> QPixmap | None:
        """Return the thumbnail if available; otherwise start generating it and return None."""
        pix = self._memory.get(path)
        if pix is not None:
            self._memory.move_to_end(path)
            return pix
        if path in self._pending or path in self._failed:
            return None
        key = cache_key(path)
        if key is None:
            self._failed.add(path)
            return None
        disk = self._dir / f"{key}.jpg"
        if disk.exists():
            pix = QPixmap(str(disk))
            if not pix.isNull():
                self._remember(path, pix)
                return pix
        self._pending.add(path)
        if classify(path) in (Kind.VIDEO, Kind.ANIMATED):
            self._posters.request(path, lambda poster, p=path, d=disk: self._from_poster(p, d, poster))
        else:
            self._pool.start(_ImageJob(path, disk, self._signals))
        return None

    def _from_poster(self, path: str, disk: Path, poster: str | None) -> None:
        image = QImage(poster) if poster else QImage()
        if not image.isNull():
            image = crop_to(image, THUMB_SIZE)
            disk.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(disk), "JPG", 85)
        self._on_done(path, image)

    def _on_done(self, path: str, image: QImage) -> None:
        self._pending.discard(path)
        if image.isNull():
            self._failed.add(path)
        else:
            self._remember(path, QPixmap.fromImage(image))
        self.ready.emit(path)

    def _remember(self, path: str, pix: QPixmap) -> None:
        self._memory[path] = pix
        self._memory.move_to_end(path)
        while len(self._memory) > MEMORY_LIMIT:
            self._memory.popitem(last=False)

    def retry_failed(self) -> None:
        """Try again for files whose thumbnail couldn't be made (e.g. they were still being copied)."""
        self._failed.clear()

    def clear(self) -> None:
        self._memory.clear()
        self._failed.clear()
        for f in self._dir.glob("*.jpg"):
            try:
                f.unlink()
            except OSError:
                pass
