"""MIDI for the routes of the Control Desk (item 59).

A MIDI route takes its values from CC and note messages of one MIDI device on one MIDI channel; every output channel
of the route has its own input (a CC, a 14-bit CC pair, a note, or a constant, see ``MidiChannel`` in
``engine/routes.py``). This hub keeps the latest value of every control it has seen, like the input store of Art-Net
does: a control that stops keeps its last value (Miro, 2026-10-22).

Where the messages come from (item 89): ``MidiDevices`` owns every MIDI port (a port can be opened once only on
Windows) and hands every message of every device on, with the device's key, to ``handle``. A route still takes the
messages of its own device only.

Learn per channel: ``set_learning`` waits for the next CC or note-on of the route's device on the route's MIDI channel
and tells the caller which control it was; messages on another channel are remembered as "heard" so the page can say
so.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from .midi_in import LEARN_SECONDS, port_key

Control = tuple[str, int, str, int]  # (device key, MIDI channel 1-16, "cc" or "note", number)


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
        self._controls: dict[Control, dict[str, Any]] = {}  # the latest of each control: {"v": 0..127, "on": bool}
        # device name -> (open, why not): what ``MidiDevices`` says about the device a route names
        self.device_state: Callable[[str], tuple[bool, str | None]] = lambda device: (False, None)
        self._last: dict[str, float] = {}  # device key -> clock() of its last message
        self._received: dict[str, int] = {}
        # Learn: what waits for a control
        self._learn: dict[str, Any] | None = None
        self._learn_ids = 0
        self.learned: dict | None = None  # what the last Learn captured
        self.heard: dict | None = None  # the last control heard while Learn waited (also on another channel)
        self.on_learned: Callable[[str, int, dict], None] = lambda route_id, index, spec: None

    # -- messages
    def handle(self, device: str, msg) -> None:
        """A message of the device with this ``port_key``."""
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
            self._controls[(device, channel, kind, number)] = {"v": value, "on": on}
            self._last[device] = self._clock()
            self._received[device] = self._received.get(device, 0) + 1
            learn = self._learn
            if learn is not None and learn["device"] == device and (kind == "cc" or on):
                self.heard = {"kind": kind, "number": number, "channel": channel}
                if channel == learn["channel"] and self._clock() < learn["until"]:
                    self._learn = None
                    self.learned = captured = {"id": learn["id"], "route": learn["route"], "index": learn["index"], "type": kind, "number": number}
        if captured is not None:
            self.on_learned(captured["route"], captured["index"], {"type": captured["type"], "number": captured["number"]})

    def value(self, device: str, channel: int, spec) -> int | None:
        """What a route channel takes from MIDI now (0..255), or None while its control hasn't been touched (the
        fixtures then show) or the channel has no input. ``spec``: a ``MidiChannel``."""
        if spec.type == "const":
            return spec.value
        if spec.type == "none":
            return None
        with self._lock:
            if spec.type == "cc":
                s = self._controls.get((device, channel, "cc", spec.number))
                return None if s is None else scale7(s["v"])
            if spec.type == "cc14":
                msb = self._controls.get((device, channel, "cc", spec.number))
                lsb = self._controls.get((device, channel, "cc", spec.number + 32))
                if msb is None and lsb is None:
                    return None
                return scale14(msb["v"] if msb else 0, lsb["v"] if lsb else 0)
            if spec.type == "note":
                s = self._controls.get((device, channel, "note", spec.number))
                if s is None:
                    return None
                if spec.note_mode == "onoff":
                    return 255 if s["on"] else 0
                return scale7(s["v"]) if s["on"] else 0
        return None

    # -- Learn
    def set_learning(self, route: str, device: str, channel: int, index: int, on: bool = True) -> int | None:
        """Wait for the next CC or note-on of ``device`` on MIDI ``channel`` for channel ``index`` of ``route`` (or
        cancel). Returns the id of the Learn."""
        with self._lock:
            self.learned = None
            self.heard = None
            if not on:
                self._learn = None
                return None
            self._learn_ids += 1
            self._learn = {"id": self._learn_ids, "route": route, "device": port_key(device), "channel": channel, "index": index, "until": self._clock() + LEARN_SECONDS}
            return self._learn_ids

    def learning_route(self) -> str | None:
        """The id of the route that waits for a control (the device of an off route is opened for its Learn)."""
        with self._lock:
            learn = self._learn
            return learn["route"] if learn is not None and self._clock() < learn["until"] else None

    # -- what the page shows
    def status(self, devices: Iterable[str] = ()) -> dict:
        """``devices``: the names the routes that listen (or learn) ask for."""
        now = self._clock()
        wanted = {port_key(d): d for d in devices if d}
        states = {k: self.device_state(d) for k, d in wanted.items()}  # outside the lock: it asks MidiDevices
        with self._lock:
            rows = [
                {
                    "device": d,
                    "open": states[k][0],
                    "error": states[k][1],
                    "received": self._received.get(k, 0),
                    "age": round(now - self._last[k], 2) if k in self._last else None,
                }
                for k, d in wanted.items()
            ]
            learn = self._learn
            return {
                "devices": rows,
                "learn": None
                if learn is None or now >= learn["until"]
                else {"id": learn["id"], "route": learn["route"], "index": learn["index"], "channel": learn["channel"], "seconds": round(learn["until"] - now, 1), "heard": self.heard},
                "learned": self.learned,
                "learn_seconds": LEARN_SECONDS,
            }
