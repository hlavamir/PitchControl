"""What ran lately (item 98): a ring of the last seconds' activities, for the frame timing logs.

When the Open DMX writer or the engine is late, the timing log says what else was going on at that time: a garbage
collection, the audio device lookup, a file write. The places that do such work wrap it in ``track(label)`` (or call
``record``); the logs ask ``overlapping(t0, t1)`` and print ``format_summary`` of the answer. Times are
``time.perf_counter()`` seconds. Cheap on purpose: a lock and an append per event, and no logging in here.
"""

from __future__ import annotations

import gc
import threading
import time
from collections import deque
from dataclasses import dataclass

KEEP_S = 60.0  # how far back the ring remembers
MAX_ENTRIES = 4000  # and the most it holds, whatever their age


@dataclass
class Summary:
    """All the activities of one label that overlap a time span."""

    label: str
    count: int = 0
    total_s: float = 0.0
    longest_s: float = 0.0
    running: bool = False  # one of them has not ended yet


class ActivityRecorder:
    def __init__(self, keep_s: float = KEEP_S, max_entries: int = MAX_ENTRIES) -> None:
        self.keep_s = keep_s
        self._done: deque[tuple[str, float, float]] = deque(maxlen=max_entries)
        self._running: dict[int, tuple[str, float]] = {}  # token -> (label, start)
        self._pending: deque[tuple[str, float, float]] = deque(maxlen=max_entries)  # events that couldn't take the lock
        self._next_token = 0
        self._lock = threading.Lock()

    def record(self, label: str, start: float, end: float) -> None:
        with self._lock:
            self._append(label, start, end)

    def record_nowait(self, label: str, start: float, end: float) -> None:
        """For the garbage collector's callback, which can run on a thread that holds the lock already (the collection
        starts from an allocation inside ``record``): a plain acquire would wait for itself. When the lock is taken the
        event waits in ``_pending`` (a deque's append is atomic) and joins the ring at the next append or query, so a
        long collection is never lost: it is what the timing logs look for."""
        if not self._lock.acquire(blocking=False):
            self._pending.append((label, start, end))
            return
        try:
            self._append(label, start, end)
        finally:
            self._lock.release()

    def _flush_pending(self) -> None:
        """Under the lock: move the waiting events into the ring."""
        pending, done = self._pending, self._done
        while pending:
            try:
                done.append(pending.popleft())
            except IndexError:  # emptied meanwhile
                break

    def _append(self, label: str, start: float, end: float) -> None:
        self._flush_pending()
        done = self._done
        done.append((label, start, end))
        horizon = end - self.keep_s
        while done and done[0][2] < horizon:
            done.popleft()

    def track(self, label: str) -> "_Tracked":
        """``with activities.track("write macros.json"):`` records the block; while it runs it counts as running."""
        return _Tracked(self, label)

    def _begin(self, label: str, start: float) -> int:
        with self._lock:
            self._next_token += 1
            self._running[self._next_token] = (label, start)
            return self._next_token

    def _end(self, token: int, end: float) -> None:
        with self._lock:
            entry = self._running.pop(token, None)
            if entry is not None:
                self._append(entry[0], entry[1], end)

    def overlapping(self, t0: float, t1: float, now: float | None = None) -> list[Summary]:
        """The activities that overlap ``t0``..``t1``, by label, the longest total first. One that has not ended counts
        up to ``now`` (default: the clock) and is marked running."""
        if now is None:
            now = time.perf_counter()
        with self._lock:
            self._flush_pending()
            done = list(self._done)
            running = list(self._running.values())
        by_label: dict[str, Summary] = {}
        for label, start, end in done:
            if end > t0 and start < t1:
                s = by_label.setdefault(label, Summary(label))
                s.count += 1
                s.total_s += end - start
                s.longest_s = max(s.longest_s, end - start)
        for label, start in running:
            if start < t1:
                s = by_label.setdefault(label, Summary(label))
                s.count += 1
                s.total_s += max(0.0, now - start)
                s.longest_s = max(s.longest_s, now - start)
                s.running = True
        return sorted(by_label.values(), key=lambda s: -s.total_s)

    def clear(self) -> None:
        with self._lock:
            self._done.clear()
            self._running.clear()
            self._pending.clear()


class _Tracked:
    __slots__ = ("_recorder", "_label", "_token")

    def __init__(self, recorder: ActivityRecorder, label: str) -> None:
        self._recorder = recorder
        self._label = label
        self._token = 0

    def __enter__(self) -> "_Tracked":
        self._token = self._recorder._begin(self._label, time.perf_counter())
        return self

    def __exit__(self, *exc) -> None:
        self._recorder._end(self._token, time.perf_counter())


def format_duration(seconds: float) -> str:
    ms = seconds * 1000
    if ms >= 1000:
        return f"{ms / 1000:.1f} s"
    return "<1 ms" if ms < 0.5 else f"{ms:.0f} ms"


def format_summary(summaries: list[Summary]) -> str:
    """``gc gen2 1× 84 ms, audio device lookup 1× 1.6 s (running)``; with several of one kind the longest is added."""
    if not summaries:
        return "nothing recorded"
    parts = []
    for s in summaries:
        text = f"{s.label} {s.count}× {format_duration(s.total_s)}"
        if s.count > 1:
            text += f" (longest {format_duration(s.longest_s)})"
        if s.running:
            text += " (running)"
        parts.append(text)
    return ", ".join(parts)


ACTIVITIES = ActivityRecorder()  # the one of this process


def track(label: str) -> _Tracked:
    return ACTIVITIES.track(label)


def record(label: str, start: float, end: float) -> None:
    ACTIVITIES.record(label, start, end)


def overlapping(t0: float, t1: float) -> list[Summary]:
    return ACTIVITIES.overlapping(t0, t1)


# -- garbage collections

GC_GEN0_MIN_S = 0.002  # gen0 runs all the time: only the ones that took long enough to matter go in the ring
_gc_start = 0.0


def _gc_callback(phase: str, info: dict) -> None:
    global _gc_start
    if phase == "start":
        _gc_start = time.perf_counter()
        return
    end = time.perf_counter()
    generation = info.get("generation", 0)
    if generation == 0 and end - _gc_start < GC_GEN0_MIN_S:
        return
    ACTIVITIES.record_nowait(f"gc gen{generation}", _gc_start, end)


def install_gc_hook() -> None:
    """Record the collections (once: a second call changes nothing)."""
    if _gc_callback not in gc.callbacks:
        gc.callbacks.append(_gc_callback)


def remove_gc_hook() -> None:
    if _gc_callback in gc.callbacks:
        gc.callbacks.remove(_gc_callback)
