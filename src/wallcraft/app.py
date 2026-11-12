"""Application bootstrap."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import APP_ID, APP_NAME, APP_USER_MODEL_ID, __version__, paths

log = logging.getLogger("wallcraft")


def _ensure_std_streams() -> None:
    # Windowed (no console) builds have no stdout/stderr; give them somewhere harmless to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def _setup_logging(debug: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        file_handler = RotatingFileHandler(paths.log_dir() / "wallcraft.log", maxBytes=1_000_000,
                                           backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook


def _install_qt_message_handler() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    qt_log = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, _context, message):
        qt_log.log(levels.get(mode, logging.INFO), message)

    qInstallMessageHandler(handler)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} wallpaper manager")
    p.add_argument("--minimized", action="store_true", help="start in the system tray")
    p.add_argument("--autostart", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--debug", action="store_true", help="verbose logging")
    p.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return p.parse_args(argv)


def _smoke_check() -> int:
    """Used by CI on the packaged exe: verify bundled Qt plugins load. 0 = OK."""
    from PySide6.QtGui import QImageReader
    from PySide6.QtMultimedia import QMediaFormat

    decoders = QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode)
    images = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
    log.info("Smoke test: %d video container formats, image formats: %s", len(decoders), sorted(images))
    if not decoders:
        log.error("Smoke test: no video decoders (multimedia plugin missing?)")
        return 3
    if not {"jpeg", "png", "gif", "webp"} <= images:
        log.error("Smoke test: image format plugins missing")
        return 4
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        from .live.mpv import CORE_OPTIONS, EMBEDDED_OPTIONS, find_mpv, option_name, supported_options

        mpv = find_mpv()
        if not mpv:
            log.error("Smoke test: bundled mpv not found")
            return 5
        supported = supported_options(mpv)
        missing = [a for a in CORE_OPTIONS + EMBEDDED_OPTIONS if option_name(a) not in supported]
        if missing:
            log.error("Smoke test: mpv at %s doesn't accept %s", mpv, missing)
            return 6
        log.info("Smoke test: mpv OK (%s, %d options)", mpv, len(supported))
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_std_streams()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths.ensure_dirs()
    _setup_logging(args.debug)
    log.info("%s %s starting (Python %s, %s)", APP_NAME, __version__, sys.version.split()[0], sys.platform)

    if sys.platform == "win32":
        # Own taskbar identity (icon/grouping) instead of python.exe's.
        from .platform.windows import win32

        win32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from .config import Appearance
    from .controller import Controller
    from .platform import create_backend
    from .services.config_store import ConfigStore
    from .services.library_service import LibraryService
    from .services.posters import PosterService
    from .services.thumbnails import ThumbnailCache
    from .single_instance import SingleInstance
    from .ui import style
    from .ui.context import AppContext
    from .ui.main_window import MainWindow
    from .ui.tray import Tray

    _install_qt_message_handler()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    icon = QIcon(str(paths.resource("icon.png")))
    app.setWindowIcon(icon)

    instance = SingleInstance(APP_ID)
    if not instance.acquire():
        log.info("Another instance is running; asked it to show its window")
        return 0

    store = ConfigStore(paths.config_file())
    backend = create_backend()
    posters = PosterService(paths.poster_dir())
    thumbs = ThumbnailCache(paths.thumbnail_dir(), posters)
    library = LibraryService(store)
    controller = Controller(store, backend, library, posters)
    ctx = AppContext(store=store, backend=backend, library=library, thumbs=thumbs, controller=controller)

    dark_now: list[bool | None] = [None]

    def restyle() -> None:
        appearance = store.config.theme.appearance
        if appearance is Appearance.SYSTEM:
            dark = backend.os_theme() == "dark"
        else:
            dark = appearance is Appearance.DARK
        if dark != dark_now[0]:
            dark_now[0] = dark
            style.apply_theme(app, dark)

    restyle()
    store.changed.connect(lambda section: restyle() if section.startswith("theme") else None)
    controller.osThemeChanged.connect(lambda _t: restyle())

    def quit_app() -> None:
        log.info("Quitting")
        app.quit()

    window = MainWindow(ctx, quit_app)
    tray = Tray(ctx, window, icon, quit_app) if QSystemTrayIcon.isSystemTrayAvailable() else None
    if tray is not None:
        tray.show()
    instance.activated.connect(window.show_and_raise)
    app.aboutToQuit.connect(controller.shutdown)

    library.rescan()
    controller.start()

    if args.smoke_test:
        from PySide6.QtCore import QTimer

        result = [0]

        def finish() -> None:
            result[0] = _smoke_check()
            app.quit()

        QTimer.singleShot(3000, finish)
        app.exec()
        log.info("Smoke test finished with %s", result[0])
        return result[0]

    hidden = (args.minimized or args.autostart or store.config.general.start_minimized) and tray is not None
    if not hidden:
        window.show()
    code = app.exec()
    log.info("Exited with code %s", code)
    return code
