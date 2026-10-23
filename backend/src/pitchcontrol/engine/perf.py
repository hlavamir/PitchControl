"""The frame times of the last seconds, for the header's FPS bubble (item 66): a perf meter like vvvv's.

The engine thread writes two numbers per frame into a fixed ring; the UI reads what is new a few times a second, and
only while a bubble shows it. Nothing here allocates per frame or waits for the reader.
"""

from __future__ import annotations

import threading

PERF_FRAMES = 1024  # the ring: 23 s at the highest frame rate Settings offers (44 fps), the bubble's 10 s up to 100 fps


class FrameTimes:
    """Per frame: the time since the frame before (ms, what the lights see) and the time the engine computed (ms)."""

    def __init__(self, size: int = PERF_FRAMES) -> None:
        self.size = size
        self._interval = [0.0] * size
        self._tick = [0.0] * size
        self.count = 0  # frames recorded so far; frame n sits at n % size
        self._lock = threading.Lock()

    def record(self, interval_ms: float, tick_ms: float) -> None:
        with self._lock:
            i = self.count % self.size
            self._interval[i] = interval_ms
            self._tick[i] = tick_ms
            self.count += 1

    def since(self, after: int, limit: int | None = None) -> tuple[int, list[list[float]]]:
        """The frames recorded after frame number ``after`` (``[interval_ms, tick_ms]`` each, oldest first), at most the
        ring's size or ``limit``, and the number of the last one. ``after`` ahead of the count (an engine that restarted)
        gives everything there is."""
        with self._lock:
            count = self.count
            if after > count:
                after = 0
            n = min(count - after, self.size, limit if limit is not None else self.size)
            rows = [[round(self._interval[f % self.size], 2), round(self._tick[f % self.size], 2)] for f in range(count - n, count)]
        return count, rows
