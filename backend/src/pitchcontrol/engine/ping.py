"""Ping a fixture (item 104): identify it in the rig by flashing it.

A ping makes one fixture flash white at full three times in one second, on top of everything: the app's output,
the routes and the manual overrides (the engine writes the flash last). A fixture with several pixels flashes only
its first tenth, so its orientation shows too. Afterwards the fixture shows what it showed before, because nothing
of the flash is kept: the layer is only asked for what to write in the frame being built.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

FLASHES = 3
STEP_S = 0.2  # one flash, and the gap between two
TOTAL_S = (2 * FLASHES - 1) * STEP_S  # on, off, on, off, on: three flashes in one second


def flash_pixels(pixels: int) -> int:
    """How many pixels of a fixture flash: the first tenth (rounded up), at least one (24 pixels: 3, 140: 14, 1: 1)."""
    return max(1, math.ceil(pixels / 10))


def is_lit(elapsed: float) -> bool:
    """Whether a ping that started ``elapsed`` seconds ago is in one of its flashes."""
    if not 0.0 <= elapsed < TOTAL_S:
        return False
    return int(elapsed / STEP_S) % 2 == 0


class Pings:
    """The running pings, by fixture name. Pressing Ping again restarts it."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._started: dict[str, float] = {}
        self._lock = threading.Lock()

    def start(self, name: str) -> None:
        with self._lock:
            self._started[name] = self.clock()

    def lit(self, name: str, now: float | None = None) -> bool:
        """Whether the fixture is in a flash now; a ping that is over is forgotten."""
        now = self.clock() if now is None else now
        with self._lock:
            started = self._started.get(name)
            if started is None:
                return False
            if now - started >= TOTAL_S:
                del self._started[name]
                return False
            return is_lit(now - started)
