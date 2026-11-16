"""Convert images a desktop can't display natively into a cached PNG."""

from __future__ import annotations

import hashlib
import os

from ..paths import converted_dir


def prepare_image(path: str, native_exts: frozenset[str]) -> str:
    path = os.path.abspath(path)
    if os.path.splitext(path)[1].lower() in native_exts:
        return path
    from PySide6.QtGui import QImage

    st = os.stat(path)
    key = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()
    out = converted_dir() / f"{key}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        img = QImage(path)
        if img.isNull() or not img.save(str(out), "PNG"):
            raise OSError(f"Could not convert {path} for use as a wallpaper")
    return str(out)
