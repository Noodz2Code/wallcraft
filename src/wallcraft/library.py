"""Media classification and library scanning (no Qt dependency)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

IMAGE_EXTS = frozenset(
    {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".dib", ".tif", ".tiff"}
)
# Formats the Windows desktop renders without conversion.
NATIVE_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".dib", ".tif", ".tiff"})
# Every container below was verified to play through Qt Multimedia's FFmpeg backend.
VIDEO_EXTS = frozenset({
    ".mp4", ".m4v", ".mov", ".mkv", ".webm",           # modern (H.264, H.265, VP8/9, AV1)
    ".avi", ".wmv", ".asf",                            # Windows / legacy
    ".mpg", ".mpeg", ".m2v", ".vob",                   # MPEG-1/2, DVD
    ".m2ts", ".mts",                                   # camcorders, Blu-ray
    ".flv", ".f4v", ".3gp", ".3g2", ".ogv",            # Flash, phones, Ogg/Theora
})
ANIMATED_EXTS = frozenset({".gif"})
# Extensions whose kind depends on the file contents: WebP can be still or animated, and
# .ts is both MPEG transport stream video and TypeScript source code.
SNIFFED_EXTS = frozenset({".webp", ".ts"})
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | ANIMATED_EXTS | SNIFFED_EXTS


class Kind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    ANIMATED = "animated"

    @property
    def is_live(self) -> bool:
        return self is not Kind.IMAGE

    @property
    def label(self) -> str:
        return {Kind.IMAGE: "Image", Kind.VIDEO: "Video", Kind.ANIMATED: "Animated image"}[self]


@lru_cache(maxsize=4096)
def _header(path: str, mtime_ns: int, size: int) -> bytes:
    """First bytes of a file, cached per (path, mtime, size) so repeated checks are free."""
    try:
        with open(path, "rb") as fh:
            return fh.read(32)
    except OSError:
        return b""


def read_header(path: str) -> bytes:
    try:
        st = os.stat(path)
    except OSError:
        return b""
    return _header(os.path.abspath(path), st.st_mtime_ns, st.st_size)


def is_animated_webp(header: bytes) -> bool:
    # RIFF....WEBPVP8X, then a flags byte where bit 1 (0x02) marks animation.
    return (len(header) > 20 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
            and header[12:16] == b"VP8X" and bool(header[20] & 0x02))


def is_mpeg_ts(header: bytes) -> bool:
    # 188-byte packets start with sync byte 0x47; 192-byte (M2TS-style) packets have it at offset 4.
    return len(header) > 4 and (header[0] == 0x47 or header[4] == 0x47)


def classify(path: str | os.PathLike) -> Kind | None:
    path = str(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return Kind.IMAGE
    if ext in VIDEO_EXTS:
        return Kind.VIDEO
    if ext in ANIMATED_EXTS:
        return Kind.ANIMATED
    if ext == ".webp":
        return Kind.ANIMATED if is_animated_webp(read_header(path)) else Kind.IMAGE
    if ext == ".ts":
        return Kind.VIDEO if is_mpeg_ts(read_header(path)) else None
    return None


def is_live(path: str) -> bool:
    kind = classify(path)
    return kind is not None and kind.is_live


def file_tag(path: str) -> str:
    """Short file-type label shown on tiles, e.g. "JPG", "MP4", "WEBP"."""
    return os.path.splitext(path)[1].lstrip(".").upper() or "FILE"


def norm(path: str) -> str:
    """Canonical form for comparing paths (case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(path))


@dataclass(frozen=True)
class MediaItem:
    path: str
    kind: Kind
    size: int = 0
    mtime: float = 0.0

    @property
    def name(self) -> str:
        return Path(self.path).stem

    @property
    def is_live(self) -> bool:
        return self.kind.is_live

    @property
    def tag(self) -> str:
        return file_tag(self.path)

    @classmethod
    def from_path(cls, path: str) -> MediaItem | None:
        kind = classify(path)
        if kind is None:
            return None
        try:
            st = os.stat(path)
        except OSError:
            return None
        return cls(path=path, kind=kind, size=st.st_size, mtime=st.st_mtime)


def _walk(folder: str, recursive: bool, cancelled: Callable[[], bool]) -> Iterable[os.DirEntry]:
    stack = [folder]
    while stack:
        if cancelled():
            return
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        stack.append(entry.path)
                elif entry.is_file():
                    yield entry
            except OSError:
                continue


def scan(
    folders: Iterable[str],
    files: Iterable[str] = (),
    excluded: Iterable[str] = (),
    recursive: bool = True,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[MediaItem]:
    """Collect supported media from folders and individual files, de-duplicated and sorted."""
    skip = {norm(p) for p in excluded}
    seen: set[str] = set()
    items: list[MediaItem] = []

    def add(path: str, size: int, mtime: float) -> None:
        key = norm(path)
        if key in seen or key in skip:
            return
        kind = classify(path)
        if kind is None:
            return
        seen.add(key)
        items.append(MediaItem(path=os.path.abspath(path), kind=kind, size=size, mtime=mtime))

    for folder in folders:
        for entry in _walk(folder, recursive, cancelled):
            if os.path.splitext(entry.name)[1].lower() not in ALL_EXTS:
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            add(entry.path, st.st_size, st.st_mtime)

    for f in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        add(f, st.st_size, st.st_mtime)

    items.sort(key=lambda i: (i.name.lower(), i.path.lower()))
    return items
