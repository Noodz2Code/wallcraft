"""Media classification and library scanning (no Qt dependency)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

IMAGE_EXTS = frozenset(
    {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".dib", ".webp", ".tif", ".tiff"}
)
# Formats the Windows desktop renders without conversion.
NATIVE_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".dib", ".tif", ".tiff"})
VIDEO_EXTS = frozenset({".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi", ".wmv"})
ANIMATED_EXTS = frozenset({".gif"})
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | ANIMATED_EXTS


class Kind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    ANIMATED = "animated"

    @property
    def is_live(self) -> bool:
        return self is not Kind.IMAGE

    @property
    def label(self) -> str:
        return {Kind.IMAGE: "Image", Kind.VIDEO: "Video", Kind.ANIMATED: "Animated GIF"}[self]


def classify(path: str | os.PathLike) -> Kind | None:
    ext = os.path.splitext(str(path))[1].lower()
    if ext in IMAGE_EXTS:
        return Kind.IMAGE
    if ext in VIDEO_EXTS:
        return Kind.VIDEO
    if ext in ANIMATED_EXTS:
        return Kind.ANIMATED
    return None


def is_live(path: str) -> bool:
    kind = classify(path)
    return kind is not None and kind.is_live


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
            if classify(entry.name) is None:
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
