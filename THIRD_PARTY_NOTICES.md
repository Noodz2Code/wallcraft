# Third-party software

Wallcraft's own code is MIT licensed. Release builds include the following third-party software,
each under its own license.

| Component | License | Source |
| --- | --- | --- |
| [mpv](https://mpv.io) (bundled in Windows builds; build by [shinchiro](https://github.com/shinchiro/mpv-winbuild-cmake)) | GPL-2.0-or-later | https://github.com/mpv-player/mpv. The exact commit and build scripts are listed in `mpv/VERSION.txt` inside each build. |
| [Qt 6](https://www.qt.io) via [PySide6](https://doc.qt.io/qtforpython/) | LGPL-3.0 | https://code.qt.io |
| [FFmpeg](https://ffmpeg.org) (inside Qt Multimedia) | LGPL-2.1-or-later | https://ffmpeg.org/download.html |
| [Python](https://www.python.org) | PSF License | https://github.com/python/cpython |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) (macOS builds) | MIT | https://github.com/ronaldoussoren/pyobjc |
| [libxcb-cursor](https://gitlab.freedesktop.org/xorg/lib/libxcb-cursor) (Linux builds) | MIT/X11 | https://gitlab.freedesktop.org/xorg/lib/libxcb-cursor |

mpv runs as a separate program that Wallcraft starts and controls. It isn't linked into Wallcraft.
Its license text is at https://github.com/mpv-player/mpv/blob/master/Copyright.
