"""Windows' system timer ticks every 15.6 ms unless a program asks for finer steps; sleeps and waits round up to it, which
makes the frame pacing and the Open DMX writer's gaps coarse (item 35). The engine raises the resolution to 1 ms while it
runs. Off Windows these are no-ops."""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger(__name__)

PERIOD_MS = 1

_lock = threading.Lock()
_raised = False


def _winmm():
    import ctypes

    return ctypes.windll.winmm  # type: ignore[attr-defined]


def raise_resolution() -> None:
    """timeBeginPeriod(1), once however often it is called; never raises."""
    global _raised
    if sys.platform != "win32":
        return
    with _lock:
        if _raised:
            return
        try:
            _winmm().timeBeginPeriod(PERIOD_MS)
        except Exception as exc:  # noqa: BLE001 - timing precision is not worth a crash
            log.warning("could not set the Windows timer resolution: %s", exc)
            return
        _raised = True
        log.info("Windows timer resolution set to %d ms (precise frame timing)", PERIOD_MS)


def restore_resolution() -> None:
    """timeEndPeriod(1) if raise_resolution() did its call; never raises."""
    global _raised
    if sys.platform != "win32":
        return
    with _lock:
        if not _raised:
            return
        _raised = False
        try:
            _winmm().timeEndPeriod(PERIOD_MS)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not restore the Windows timer resolution: %s", exc)
