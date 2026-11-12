"""Playlist ordering for slideshow mode."""

from __future__ import annotations

import random
from collections.abc import Iterable


class Slideshow:
    """Cycles through items in order, or in a shuffled order without repeats per round."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._items: list[str] = []
        self._shuffle = False
        self._order: list[str] = []
        self._pos = -1

    @property
    def items(self) -> list[str]:
        return list(self._items)

    @property
    def current(self) -> str | None:
        if 0 <= self._pos < len(self._order):
            return self._order[self._pos]
        return None

    def configure(self, items: Iterable[str], shuffle: bool, current: str | None = None) -> None:
        items = list(dict.fromkeys(items))
        if items == self._items and shuffle == self._shuffle:
            return
        keep = current if current is not None else self.current
        self._items = items
        self._shuffle = shuffle
        self._build_order(keep)

    def _build_order(self, keep: str | None) -> None:
        order = list(self._items)
        if self._shuffle:
            self._rng.shuffle(order)
            if keep in order:
                order.remove(keep)
                order.insert(0, keep)
        self._order = order
        self._pos = order.index(keep) if keep in order else -1

    def next(self) -> str | None:
        if not self._order:
            return None
        self._pos += 1
        if self._pos >= len(self._order):
            last = self._order[-1]
            if self._shuffle:
                self._rng.shuffle(self._order)
                if len(self._order) > 1 and self._order[0] == last:
                    self._order[0], self._order[-1] = self._order[-1], self._order[0]
            self._pos = 0
        return self.current

    def previous(self) -> str | None:
        if not self._order:
            return None
        self._pos = (self._pos - 1) % len(self._order)
        return self.current
