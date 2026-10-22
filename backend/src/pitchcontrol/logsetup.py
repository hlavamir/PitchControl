"""Logging: one file per backend start in ``logs/YYMMDD_hhmmss.log``, plus the console, plus the last records of
this run in memory (``MemoryLogHandler``: Settings → Log shows them, item 56)."""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from itertools import islice
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

LOG_CAPACITY = 3000  # records kept in memory for the log view


class MemoryLogHandler(logging.Handler):
    """A ring buffer of the last ``capacity`` records of this run, for the log view. Each record is a dict with a
    sequence number (``seq``, 1, 2, 3 … for the life of the handler, so a viewer asks for what is newer than the last
    one it has), the time (``t``, epoch seconds), the level (``level``, the name: ERROR, WARNING, INFO, DEBUG, CRITICAL)
    as a field of its own, the ``logger`` and the ``msg`` (with the traceback below it when there is one).

    ``emit`` runs in whatever thread logs (the engine's included): it formats once and appends under a lock, nothing
    else; delivery to the UI is batched by the reader (``since``)."""

    def __init__(self, capacity: int = LOG_CAPACITY) -> None:
        super().__init__(logging.NOTSET)
        self.capacity = capacity
        self._records: deque[dict] = deque(maxlen=capacity)
        self._seq = 0
        self._guard = threading.Lock()
        self._formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + self._formatter.formatException(record.exc_info)
            with self._guard:
                self._seq += 1
                self._records.append(
                    {"seq": self._seq, "t": round(record.created, 3), "level": record.levelname, "logger": record.name, "msg": msg}
                )
        except Exception:  # noqa: BLE001
            self.handleError(record)

    @property
    def last_seq(self) -> int:
        with self._guard:
            return self._seq

    def since(self, after: int = 0, limit: int | None = None) -> list[dict]:
        """The records newer than ``after`` (0: all that are kept), oldest first; with ``limit``, the first ``limit`` of
        them (the reader asks again from the last ``seq`` it got)."""
        with self._guard:
            count = min(self._seq - max(after, 0), len(self._records))  # the sequence numbers are consecutive
            newer = list(islice(reversed(self._records), count))[::-1] if count > 0 else []
        return newer if limit is None else newer[:limit]


_memory = MemoryLogHandler()


def memory_log() -> MemoryLogHandler:
    """The in-memory handler of this run (the one ``setup_logging`` attached; an unattached, empty one before)."""
    return _memory


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{datetime.now():%y%m%d_%H%M%S}.log"

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    global _memory
    _memory = MemoryLogHandler()
    root.addHandler(_memory)

    logging.getLogger(__name__).info("logging to %s", path)
    return path
