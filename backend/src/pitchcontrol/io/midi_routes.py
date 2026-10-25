"""MIDI for the routes of the Control Desk (item 59).

Every output channel of a MIDI route has its own input: a CC, a 14-bit CC pair, a note, or a constant, each on its own
MIDI channel (see ``MidiChannel`` in ``engine/routes.py``). This hub keeps the latest value of every control it has
seen, like the input store of Art-Net does: a control that stops keeps its last value (Miro, 2026-10-22).

Where the messages come from (items 89 and 91): ``MidiDevices`` owns every MIDI port (a port can be opened once only on
Windows) and hands every message of every device that is on to ``handle``. A route doesn't name a device: a control is
told apart by its MIDI channel and number only.

Learn per channel: ``set_learning`` waits for the next CC or note-on on any channel of any device and tells the caller
which control it was, with its MIDI channel.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from .midi_in import LEARN_SECONDS

Control = tuple[int, str, int]  # (MIDI channel 1-16, "cc" or "note", number)


def scale7(v: int) -> int:
    """A 7-bit MIDI value (0..127) as 0..255."""
    return round(max(0, min(127, v)) * 255 / 127)


def scale14(msb: int, lsb: int) -> int:
    """A 14-bit value from its two CCs as 0..255."""
    return round(((msb & 0x7F) << 7 | (lsb & 0x7F)) * 255 / 16383)


class MidiRouteHub:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._controls: dict[Control, dict[str, Any]] = {}  # the latest of each control: {"v": 0..127, "on": bool, "t": clock()}
        # how many MIDI inputs are open: what ``MidiDevices`` says
        self.open_inputs: Callable[[], int] = lambda: 0
        # Learn: what waits for a control
        self._learn: dict[str, Any] | None = None
        self._learn_ids = 0
        self.learned: dict | None = None  # what the last Learn captured
        self.on_learned: Callable[[str, int, dict], None] = lambda route_id, index, spec: None

    # -- messages
    def handle(self, device: str, msg) -> None:
        """A message of the device with this ``port_key`` (the device is not told apart: item 91)."""
        kind, number, value, on = None, 0, 0, False
        if msg.type == "control_change":
            kind, number, value, on = "cc", msg.control, msg.value, msg.value > 0
        elif msg.type == "note_on" and msg.velocity > 0:
            kind, number, value, on = "note", msg.note, msg.velocity, True
        elif msg.type in ("note_off", "note_on"):
            kind, number, value, on = "note", msg.note, 0, False
        else:
            return
        channel = getattr(msg, "channel", 0) + 1
        captured = None
        with self._lock:
            now = self._clock()
            self._controls[(channel, kind, number)] = {"v": value, "on": on, "t": now}
            learn = self._learn
            if learn is not None and (kind == "cc" or on) and now < learn["until"]:
                self._learn = None
                self.learned = captured = {"id": learn["id"], "route": learn["route"], "index": learn["index"], "type": kind, "number": number, "channel": channel}
        if captured is not None:
            self.on_learned(captured["route"], captured["index"], {"type": captured["type"], "number": captured["number"], "channel": captured["channel"]})

    @staticmethod
    def _controls_of(spec) -> list[Control]:
        """The controls a route channel listens to: a CC pair is two."""
        if spec.type == "cc14":
            return [(spec.channel, "cc", spec.number), (spec.channel, "cc", spec.number + 32)]
        if spec.type in ("cc", "note"):
            return [(spec.channel, spec.type, spec.number)]
        return []

    def value(self, spec) -> int | None:
        """What a route channel takes from MIDI now (0..255), or None while its control hasn't been touched (the
        fixtures then show) or the channel has no input. ``spec``: a ``MidiChannel``."""
        if spec.type == "const":
            return spec.value
        if spec.type == "none":
            return None
        with self._lock:
            if spec.type == "cc":
                s = self._controls.get((spec.channel, "cc", spec.number))
                return None if s is None else scale7(s["v"])
            if spec.type == "cc14":
                msb = self._controls.get((spec.channel, "cc", spec.number))
                lsb = self._controls.get((spec.channel, "cc", spec.number + 32))
                if msb is None and lsb is None:
                    return None
                return scale14(msb["v"] if msb else 0, lsb["v"] if lsb else 0)
            if spec.type == "note":
                s = self._controls.get((spec.channel, "note", spec.number))
                if s is None:
                    return None
                if spec.note_mode == "onoff":
                    return 255 if s["on"] else 0
                return scale7(s["v"]) if s["on"] else 0
        return None

    def age(self, specs: Iterable) -> float | None:
        """Seconds since the latest message of any control the route channels ``specs`` listen to, or None when none
        of them has been touched."""
        with self._lock:
            times = [self._controls[k]["t"] for spec in specs for k in self._controls_of(spec) if k in self._controls]
            return round(self._clock() - max(times), 2) if times else None

    # -- Learn
    def set_learning(self, route: str, index: int, on: bool = True) -> int | None:
        """Wait for the next CC or note-on, on any MIDI channel of any device, for channel ``index`` of ``route`` (or
        cancel). Returns the id of the Learn."""
        with self._lock:
            self.learned = None
            if not on:
                self._learn = None
                return None
            self._learn_ids += 1
            self._learn = {"id": self._learn_ids, "route": route, "index": index, "until": self._clock() + LEARN_SECONDS}
            return self._learn_ids

    # -- what the page shows
    def status(self) -> dict:
        now = self._clock()
        with self._lock:
            learn = self._learn
            return {
                "learn": None if learn is None or now >= learn["until"] else {"id": learn["id"], "route": learn["route"], "index": learn["index"], "seconds": round(learn["until"] - now, 1)},
                "learned": self.learned,
                "learn_seconds": LEARN_SECONDS,
            }
