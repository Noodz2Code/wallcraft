"""Shared services handed to every UI component."""

from __future__ import annotations

from dataclasses import dataclass

from ..controller import Controller
from ..platform.base import Backend
from ..services.config_store import ConfigStore
from ..services.library_service import LibraryService
from ..services.thumbnails import ThumbnailCache
from ..services.updater import UpdateChecker


@dataclass
class AppContext:
    store: ConfigStore
    backend: Backend
    library: LibraryService
    thumbs: ThumbnailCache
    controller: Controller
    updates: UpdateChecker | None = None

    def refresh_all(self) -> None:
        """The Refresh button: retry missing thumbnails, rescan, and re-apply every wallpaper."""
        self.thumbs.retry_failed()
        self.controller.reload_all()
