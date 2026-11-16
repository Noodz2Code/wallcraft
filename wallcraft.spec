# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec for Wallcraft (Windows, Linux and macOS).
#
#   macOS always builds dist/Wallcraft.app (folder build inside an app bundle).
#
#   pyinstaller --noconfirm --clean wallcraft.spec          -> dist/Wallcraft.exe (single portable exe)
#   set WALLCRAFT_ONEFILE=0 && pyinstaller ... wallcraft.spec -> dist/Wallcraft/ (folder, used by the installer)

import os
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 - provided by PyInstaller
SRC = ROOT / "src"
PKG = SRC / "wallcraft"
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', (PKG / "__init__.py").read_text()).group(1)
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
# A single-file app makes no sense on macOS (apps are folders), so it's always a bundle there.
ONEFILE = os.environ.get("WALLCRAFT_ONEFILE", "1") == "1" and not IS_MAC

# mpv plays live wallpapers in its own process (fetched by scripts/fetch_mpv.py).
MPV_DIR = ROOT / "vendor" / "mpv"
# Bundled on Windows only; Linux uses the distribution's mpv, macOS plays video with Qt.
if IS_WIN and os.environ.get("WALLCRAFT_REQUIRE_MPV") == "1" and not (MPV_DIR / "mpv.exe").is_file():
    raise SystemExit("vendor/mpv/mpv.exe is missing. Run: python scripts/fetch_mpv.py")
MPV_DATAS = [(str(MPV_DIR), "mpv")] if IS_WIN and MPV_DIR.is_dir() else []

# Qt 6.5+ needs libxcb-cursor on X11, and many distributions (e.g. Linux Mint) don't install it.
# Ship it with the app so the download starts everywhere.
EXTRA_BINARIES = []
if sys.platform.startswith("linux"):
    import ctypes.util
    import glob

    found = sorted(glob.glob("/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0*")) or (
        [ctypes.util.find_library("xcb-cursor")] if ctypes.util.find_library("xcb-cursor") else [])
    if found:
        EXTRA_BINARIES.append((found[0], "."))
    elif os.environ.get("WALLCRAFT_REQUIRE_XCB_CURSOR") == "1":
        raise SystemExit("libxcb-cursor0 is not installed on the build machine (apt install libxcb-cursor0)")

HIDDEN = ["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtNetwork"]
if sys.platform.startswith("linux"):
    HIDDEN.append("PySide6.QtDBus")  # power profile, lock screen, Plasma wallpaper
if IS_MAC:
    HIDDEN += ["AppKit", "Foundation", "Quartz", "objc"]


def windows_version_file():
    """Write the Windows file-properties resource (version, product name) for the exe."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    nums = ([int(x) for x in re.findall(r"\d+", VERSION)[:3]] + [0, 0, 0, 0])[:4]
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=tuple(nums), prodvers=tuple(nums)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Wallcraft contributors"),
                StringStruct("FileDescription", "Wallcraft wallpaper manager"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "Wallcraft"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "Wallcraft.exe"),
                StringStruct("ProductName", "Wallcraft"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    path = Path(workpath) / "version_info.txt"  # noqa: F821
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(info), encoding="utf-8")
    return str(path)


# Qt modules Wallcraft never uses; excluding them keeps the download small.
EXCLUDES = [
    "tkinter", "unittest", "pydoc",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtHttpServer",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtSensors", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtUiTools",
]

a = Analysis(  # noqa: F821
    [str(PKG / "__main__.py")],
    pathex=[str(SRC)],
    binaries=EXTRA_BINARIES,
    datas=[(str(PKG / "resources"), "wallcraft/resources"), *MPV_DATAS],
    hiddenimports=HIDDEN,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

common = dict(
    name="Wallcraft",
    console=False,
    icon=str(PKG / "resources" / ("icon.icns" if IS_MAC else "icon.ico")),
    version=windows_version_file() if IS_WIN else None,
    upx=False,  # UPX-packed executables trigger more antivirus false positives
    disable_windowed_traceback=False,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)  # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="Wallcraft")  # noqa: F821
    if IS_MAC:
        app = BUNDLE(  # noqa: F821
            coll,
            name="Wallcraft.app",
            icon=str(PKG / "resources" / "icon.icns"),
            bundle_identifier="io.github.wallcraft",
            version=VERSION,
            info_plist={
                "CFBundleDisplayName": "Wallcraft",
                "CFBundleShortVersionString": VERSION,
                "CFBundleVersion": VERSION,
                "LSMinimumSystemVersion": "13.0",
                "NSHighResolutionCapable": True,
                "NSAppleEventsUsageDescription":
                    "Wallcraft switches macOS between light and dark mode when you ask it to.",
            },
        )
