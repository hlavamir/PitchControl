"""The frame times of the last seconds, for the header's FPS bubble (item 66): a perf meter like vvvv's.

The engine thread writes two numbers per frame into a fixed ring; the UI reads what is new a few times a second, and
only while a bubble shows it. Nothing here allocates per frame or waits for the reader.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .. import activity

log = logging.getLogger(__name__)

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


TIMING_SUMMARY_S = 10.0  # one summary line per this many seconds
TIMING_LATE_FACTOR = 1.5  # a frame is late when the time since the one before is over this x the engine's frame time


class EngineTimingLog:
    """The engine's side of "Log frame timing" (item 98): the writer's log says it was late, this one says whether the
    engine loop was, and what ran meanwhile. Called by the engine thread once per frame, only while an output has the
    log on (``reset`` otherwise, so that switching it on starts with a clean window)."""

    def __init__(
        self, period: Callable[[], float], activities: activity.ActivityRecorder = activity.ACTIVITIES
    ) -> None:
        self.period = period  # the engine's frame time in seconds, read live
        self.activities = activities
        self.reset()

    def reset(self) -> None:
        self._prev_start: float | None = None
        self._window_start: float | None = None
        self._frames = 0
        self._longest_tick = 0.0
        self._largest_gap = 0.0
        self._late = 0

    def frame(self, start: float, tick_s: float) -> None:
        """One frame: it started at ``start`` (perf_counter) and its tick took ``tick_s``."""
        period = self.period()
        prev_start, self._prev_start = self._prev_start, start
        if self._window_start is None:
            self._window_start = start
        self._frames += 1
        self._longest_tick = max(self._longest_tick, tick_s)
        if prev_start is not None:
            gap = start - prev_start
            self._largest_gap = max(self._largest_gap, gap)
            if gap > TIMING_LATE_FACTOR * period:
                self._late += 1
                meanwhile = activity.format_summary(self.activities.overlapping(prev_start, start))
                log.info(
                    "engine: late frame: gap %.1f ms (target %.1f ms), tick %.1f ms; meanwhile: %s",
                    gap * 1000, period * 1000, tick_s * 1000, meanwhile,
                )
        if tick_s >= TIMING_LATE_FACTOR * period:
            # after the line above: this tick is the cause of the next frame's gap, not of this one's
            self.activities.record("engine tick", start, start + tick_s)
        elapsed = start - self._window_start
        if elapsed >= TIMING_SUMMARY_S:
            log.info(
                "engine: timing, last %.1f s: %.1f fps (target %.1f), longest tick %.1f ms, largest gap %.1f ms, late frames %d",
                elapsed, self._frames / elapsed, 1 / period, self._longest_tick * 1000, self._largest_gap * 1000, self._late,
            )
            self._window_start, self._frames = start, 0
            self._longest_tick = self._largest_gap = 0.0
            self._late = 0
