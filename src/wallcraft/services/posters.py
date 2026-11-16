"""Still frames ("posters") for live wallpapers.

A poster is used as the library thumbnail and as the static desktop wallpaper
underneath a live wallpaper, so the desktop looks right when playback is
stopped by a battery rule or when Wallcraft exits.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import deque
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QImage, QImageReader

from ..library import Kind, classify

log = logging.getLogger(__name__)

PosterCallback = Callable[[str | None], None]
SEEK_MS = 1000  # skip the first second, which is often a black fade-in
TIMEOUT_MS = 10_000


def cache_key(path: str) -> str | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    raw = f"{os.path.normcase(os.path.abspath(path))}|{st.st_mtime}|{st.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class PosterService(QObject):
    def __init__(self, out_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dir = out_dir
        self._queue: deque[str] = deque()
        self._callbacks: dict[str, list[PosterCallback]] = {}
        self._player = None
        self._sink = None
        self._current: str | None = None
        self._target_us = 0
        self._frames_seen = 0
        self._job = 0
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(lambda: self._finish(None))

    def poster_path(self, path: str) -> Path | None:
        key = cache_key(path)
        return self._dir / f"{key}.jpg" if key else None

    def cached(self, path: str) -> str | None:
        p = self.poster_path(path)
        return str(p) if p and p.exists() else None

    def request(self, path: str, callback: PosterCallback) -> None:
        hit = self.cached(path)
        if hit:
            QTimer.singleShot(0, self, lambda: callback(hit))
            return
        if path in self._callbacks:
            self._callbacks[path].append(callback)
            return
        self._callbacks[path] = [callback]
        self._queue.append(path)
        QTimer.singleShot(0, self, self._next)

    # Worker ------------------------------------------------------------------- #
    def _next(self) -> None:
        if self._current is not None or not self._queue:
            return
        path = self._queue.popleft()
        self._current = path
        kind = classify(path)
        if kind is Kind.ANIMATED or kind is Kind.IMAGE:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            self._finish(self._save(reader.read()))
            return
        self._start_video(path)

    def _start_video(self, path: str) -> None:
        from PySide6.QtMultimedia import QMediaPlayer, QVideoSink

        self._frames_seen = 0
        self._target_us = 0
        self._job += 1
        job = self._job
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        # Frames may arrive queued from a decoder thread; tag them with the job id.
        self._sink.videoFrameChanged.connect(partial(self._on_frame, job))
        self._player.mediaStatusChanged.connect(partial(self._on_status, job))
        self._player.errorOccurred.connect(partial(self._on_error, job))
        self._timeout.start(TIMEOUT_MS)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _on_error(self, job: int, _error, message: str) -> None:
        if job == self._job and self._current is not None:
            log.warning("Poster extraction error: %s", message)
            self._finish(None)

    def _on_status(self, job: int, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if job != self._job or self._current is None:
            return
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._finish(None)
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if self._player and self._target_us == 0 and self._player.duration() > SEEK_MS * 3:
                self._target_us = SEEK_MS * 1000
                self._player.setPosition(SEEK_MS)

    def _on_frame(self, job: int, frame) -> None:
        if job != self._job or self._current is None or not frame.isValid():
            return
        self._frames_seen += 1
        if self._target_us and frame.startTime() < self._target_us - 200_000 and self._frames_seen < 90:
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._finish(self._save(image))

    def _save(self, image: QImage) -> str | None:
        if self._current is None or image.isNull():
            return None
        out = self.poster_path(self._current)
        if out is None:
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        if image.hasAlphaChannel():
            image = image.convertToFormat(QImage.Format.Format_RGB32)
        return str(out) if image.save(str(out), "JPG", 92) else None

    def _finish(self, result: str | None) -> None:
        path = self._current
        if path is None:
            return
        self._current = None
        self._timeout.stop()
        if self._player is not None:
            player, sink = self._player, self._sink
            self._player = self._sink = None
            for signal in (sink.videoFrameChanged, player.mediaStatusChanged, player.errorOccurred):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            player.stop()
            player.deleteLater()
            sink.deleteLater()
        if result is None:
            log.warning("Could not extract a still frame from %s", path)
        for cb in self._callbacks.pop(path, []):
            try:
                cb(result)
            except Exception:  # noqa: BLE001
                log.exception("Poster callback failed")
        QTimer.singleShot(0, self, self._next)
