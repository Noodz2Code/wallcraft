"""Widgets that render live wallpapers: videos, and animated images (GIF, animated WebP)."""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QImageReader, QMovie, QPainter, QPalette
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..config import FitMode
from ..library import Kind, MediaItem

log = logging.getLogger(__name__)


def _black(widget: QWidget) -> None:
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)


class _VideoView(QWidget):
    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget

        _black(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._video = QVideoWidget(self)
        _black(self._video)
        layout.addWidget(self._video)

        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.errorOccurred.connect(lambda _e, msg: log.error("Video playback error (%s): %s", path, msg))
        self._player.setSource(QUrl.fromLocalFile(path))

    def set_fit(self, fit: FitMode) -> None:
        mode = {
            FitMode.STRETCH: Qt.AspectRatioMode.IgnoreAspectRatio,
            FitMode.FIT: Qt.AspectRatioMode.KeepAspectRatio,
            FitMode.CENTER: Qt.AspectRatioMode.KeepAspectRatio,
            FitMode.TILE: Qt.AspectRatioMode.KeepAspectRatio,
        }.get(fit, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        self._video.setAspectRatioMode(mode)

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def set_audio(self, enabled: bool, volume: int) -> None:
        self._audio.setMuted(not enabled)
        self._audio.setVolume(max(0.0, min(1.0, volume / 100)))

    def shutdown(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())


class _AnimatedImageView(QWidget):
    """Plays animated GIF and WebP files with QMovie."""

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _black(self)
        self._fit = FitMode.FILL
        self._native = QImageReader(path).size()
        self._movie = QMovie(path, parent=self)
        self._movie.setCacheMode(QMovie.CacheMode.CacheNone)
        self._movie.frameChanged.connect(lambda _n: self.update())
        self._movie.error.connect(lambda _e: log.error("Animated image error (%s): %s", path, self._movie.lastErrorString()))

    def set_fit(self, fit: FitMode) -> None:
        self._fit = fit
        self._rescale()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rescale()

    def _target_size(self) -> QSize:
        native = self._native if self._native.isValid() else self.size()
        if self._fit is FitMode.STRETCH:
            return self.size()
        if self._fit in (FitMode.CENTER, FitMode.TILE):
            return native
        mode = (Qt.AspectRatioMode.KeepAspectRatio if self._fit is FitMode.FIT
                else Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        return native.scaled(self.size(), mode)

    def _rescale(self) -> None:
        # Let the decoder scale once per frame instead of scaling again in paintEvent.
        self._movie.setScaledSize(self._target_size())
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        pix = self._movie.currentPixmap()
        if pix.isNull():
            return
        painter = QPainter(self)
        if self._fit is FitMode.TILE:
            painter.drawTiledPixmap(self.rect(), pix)
            return
        r = QRect(QPoint(0, 0), pix.size())
        r.moveCenter(self.rect().center())
        painter.drawPixmap(r.topLeft(), pix)

    def play(self) -> None:
        if self._movie.state() == QMovie.MovieState.NotRunning:
            self._movie.start()
        else:
            self._movie.setPaused(False)

    def pause(self) -> None:
        if self._movie.state() == QMovie.MovieState.Running:
            self._movie.setPaused(True)

    def set_audio(self, enabled: bool, volume: int) -> None:
        pass

    def shutdown(self) -> None:
        self._movie.stop()


class LiveWindow(QWidget):
    """A borderless window showing one live wallpaper on one monitor."""

    def __init__(self, item: MediaItem, embedded: bool, title: str = "") -> None:
        if embedded:
            flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                     | Qt.WindowType.WindowDoesNotAcceptFocus)
        else:
            flags = Qt.WindowType.Window
        super().__init__(None, flags)
        self.item = item
        self.setWindowTitle(title or f"Live wallpaper - {item.name}")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        _black(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view = _VideoView(item.path, self) if item.kind is Kind.VIDEO else _AnimatedImageView(item.path, self)
        layout.addWidget(self._view)
        self._playing = False

    @property
    def playing(self) -> bool:
        return self._playing

    def set_fit(self, fit: FitMode) -> None:
        self._view.set_fit(fit)

    def play(self) -> None:
        if not self._playing:
            self._playing = True
            self._view.play()

    def pause(self) -> None:
        if self._playing:
            self._playing = False
            self._view.pause()

    def set_audio(self, enabled: bool, volume: int) -> None:
        self._view.set_audio(enabled, volume)

    def shutdown(self) -> None:
        self._playing = False
        self._view.shutdown()
        self.hide()
        self.deleteLater()
