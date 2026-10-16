"""OSC out: the base colours A and B, to one IP address and port, as the messages a file in ``osc/`` describes.

A file is a JSON array; each entry says what to send, to which address and in which format::

    [
      {"what": "color_a.rgba", "address": "/color_a", "format": "r"},
      {"what": "color_b.g",    "address": "/color_b/green", "format": "f"}
    ]

``what`` is ``color_a`` or ``color_b`` plus ``.r``, ``.g``, ``.b`` (one value: ``f`` = float 0..1 or ``i`` = integer
0..255) or ``.rgba`` (one OSC colour, type ``r``: four bytes R, G, B, A with A = 255). The colours are the group
colours as the Hue / Saturation macros or Auto Color Change make them (Swap Colors included), before strobo,
brightness, masks, dimmers and gamma. Anything else in a file (an unknown ``what``, a format that doesn't fit,
an address that isn't an OSC address) is ignored and reported.

A message is sent when its value changes, and everything again once a second, so a receiver started late catches up.
A file that is edited while the app runs is read again within a second; one that can't be read keeps the last
good messages going and is reported.
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config.models import OscSettings
from .workers import LatestFrameWorker

log = logging.getLogger(__name__)

REFRESH_S = 1.0  # unchanged messages are sent again this often; the file is checked for edits this often

CHANNELS = ("r", "g", "b")
GROUPS = ("a", "b")
# what -> the formats it can be sent in
FORMATS: dict[str, tuple[str, ...]] = {
    **{f"color_{g}.{c}": ("f", "i") for g in GROUPS for c in CHANNELS},
    **{f"color_{g}.rgba": ("r",) for g in GROUPS},
}


@dataclass(frozen=True)
class OscRoute:
    what: str
    address: str
    format: str

    @property
    def group(self) -> str:
        return self.what[len("color_")]

    @property
    def part(self) -> str:
        return self.what.split(".", 1)[1]


def parse_routes(data: object) -> tuple[list[OscRoute], list[str]]:
    """The valid entries of a file's content, and why each other entry is ignored. Raises ``ValueError`` if the
    content is not an array at all."""
    if not isinstance(data, list):
        raise ValueError("the file must be a JSON array of entries")
    routes: list[OscRoute] = []
    ignored: list[str] = []
    for i, entry in enumerate(data, start=1):
        why = _problem(entry)
        if isinstance(why, str):
            ignored.append(f"entry {i}: {why}")
        else:
            routes.append(why)
    return routes, ignored


def _problem(entry: object) -> OscRoute | str:
    if not isinstance(entry, dict):
        return "not an object with what, address and format"
    what, address, fmt = entry.get("what"), entry.get("address"), entry.get("format")
    if not all(isinstance(x, str) for x in (what, address, fmt)):
        return "what, address and format must all be text"
    what, fmt = what.strip().lower(), fmt.strip().lower()
    if what not in FORMATS:
        return f"unknown what '{what}' (use color_a or color_b with .r, .g, .b or .rgba)"
    if fmt not in FORMATS[what]:
        return f"{what} can only be sent as {' or '.join(FORMATS[what])}, not '{fmt}'"
    address = address.strip()
    if not address.startswith("/") or any(not 0x21 <= ord(ch) <= 0x7E for ch in address):
        return f"'{address}' is not an OSC address (it starts with / and has plain characters only)"
    return OscRoute(what, address, fmt)


# --------------------------------------------------------------------------- the wire format


def _padded(raw: bytes) -> bytes:
    """A null-terminated string, padded with nulls to a multiple of four bytes."""
    return raw + b"\x00" * (4 - len(raw) % 4)


def encode(route: OscRoute, rgb: tuple[float, float, float]) -> bytes:
    """One OSC message for ``route`` with the colour ``rgb`` (floats 0..1)."""
    r, g, b = (min(1.0, max(0.0, float(x))) for x in rgb)
    if route.format == "r":  # the OSC colour type: R, G, B, A, one byte each
        tag, body = "r", bytes((round(r * 255), round(g * 255), round(b * 255), 255))
    else:
        value = {"r": r, "g": g, "b": b}[route.part]
        if route.format == "f":
            tag, body = "f", struct.pack(">f", value)
        else:
            tag, body = "i", struct.pack(">i", round(value * 255))
    return _padded(route.address.encode("ascii")) + _padded(f",{tag}".encode("ascii")) + body


# --------------------------------------------------------------------------- sending


class OscWorker(LatestFrameWorker):
    name = "osc"

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.sock: socket.socket | None = None
        self.target: tuple | None = None
        super().__init__()

    def open(self) -> None:
        if not self.host.strip():
            raise ConnectionError("no IP address")
        try:
            family, kind, proto, _, target = socket.getaddrinfo(self.host.strip(), self.port, socket.AF_INET, socket.SOCK_DGRAM)[0]
        except socket.gaierror as exc:
            raise ConnectionError(f"can't find '{self.host}'") from exc
        self.sock = socket.socket(family, kind, proto)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # a broadcast address works too
        self.target = target
        self.connected = True
        self.last_error = None

    def write(self, frame: object) -> None:
        """``frame``: a list of OSC messages, each sent as one datagram."""
        assert self.sock is not None and self.target is not None
        for message in frame:  # type: ignore[union-attr]
            self.sock.sendto(message, self.target)
        if self._frame is frame:  # the worker would repeat the last frame every half second: the sender decides when
            self._frame = None

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.connected = False


class OscOutput:
    """The worker plus the file: knows which messages to send, and when."""

    def __init__(self, settings: OscSettings, find_file: Callable[[str], Path | None]) -> None:
        self.settings = settings
        self.find_file = find_file
        self.worker = OscWorker(settings.host, settings.port)
        self.routes: list[OscRoute] = []
        self.ignored: list[str] = []
        self.file_error: str | None = None
        self._stamp: tuple | None = None  # which version of the file ``routes`` come from
        self._checked = 0.0
        self._last: list[bytes] | None = None
        self._sent_at = 0.0
        self._logged: set[str] = set()

    def start(self) -> None:
        self._load()
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()

    # -- the file
    def _problem_once(self, text: str) -> None:
        if text not in self._logged:
            self._logged.add(text)
            log.warning("OSC: %s", text)

    def _load(self) -> None:
        name = self.settings.file
        if not name:
            self.routes, self.ignored, self.file_error, self._stamp = [], [], None, None
            return
        path = self.find_file(name)
        if path is None:
            self._stamp = None  # read it again when it is back; what was loaded keeps going meanwhile
            self.file_error = f"the file '{name}' isn't in the osc folder"
            self._problem_once(self.file_error)
            return
        try:
            stat = path.stat()
            stamp = (str(path), stat.st_mtime_ns, stat.st_size)
            if stamp == self._stamp:
                return
            self._stamp = stamp  # a file that fails to read isn't read again until it changes
            routes, ignored = parse_routes(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:  # includes JSON errors; the last good messages keep going
            self.file_error = f"'{name}' can't be read: {exc}"
            self._problem_once(f"{self.file_error}; keeping what was loaded before")
            return
        self.routes, self.ignored, self.file_error = routes, ignored, None
        log.info("OSC: %s: %d message(s), %d ignored", path.name, len(routes), len(ignored))
        for text in ignored:
            self._problem_once(f"{path.name}: {text} (ignored)")

    # -- sending
    def send(self, colors: dict[str, tuple[float, float, float]]) -> None:
        """``colors``: the base colours as ``{"a": (r, g, b), "b": (r, g, b)}``, floats 0..1."""
        now = time.monotonic()
        if now - self._checked >= REFRESH_S:
            self._checked = now
            self._load()
        if not self.routes:
            self._last = None
            return
        messages = [encode(r, colors[r.group]) for r in self.routes]
        if messages != self._last or now - self._sent_at >= REFRESH_S:
            self.worker.submit(messages)
            self._last, self._sent_at = messages, now

    def status(self) -> dict:
        return {
            **self.worker.status(),
            "messages": len(self.routes),
            "ignored": self.ignored,
            "file_error": self.file_error,
        }
