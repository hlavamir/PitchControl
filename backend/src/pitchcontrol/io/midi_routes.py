"""MIDI for the routes of the Control Desk (item 59).

A MIDI route takes its values from CC and note messages of one MIDI device on one MIDI channel; every output channel
of the route has its own input (a CC, a 14-bit CC pair, a note, or a constant, see ``MidiChannel`` in
``engine/routes.py``). This hub keeps the latest value of every control it has seen, like the input store of Art-Net
does: a control that stops keeps its last value (Miro, 2026-10-22).

Where the messages come from:

- the controller of the MIDI mapping has its port open already, and two programs (or two opens in this one) can't
  share a MIDI port on Windows, so the controller's ``MidiInput`` hands every message on (``MidiInput.tap``);
- any other device is opened here, from the devices the enabled MIDI routes name (``sync``).

Learn per channel: ``set_learning`` waits for the next CC or note-on of the route's device on the route's MIDI channel
and tells the caller which control it was; messages on another channel are remembered as "heard" so the page can say
so.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from .midi_in import LEARN_SECONDS, list_midi_inputs_checked, match_port, mido, port_key

log = logging.getLogger(__name__)

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
        self._ports: dict[str, Any] = {}  # device key -> the mido port this hub opened
        self._errors: dict[str, str] = {}  # device key -> why it isn't open
        self._names: dict[str, str] = {}  # device key -> the name the route asks for
        self._via: dict[str, str] = {}  # device key -> "controller" when the controller's input hands the messages on
        self._last: dict[str, float] = {}  # device key -> clock() of its last message
        self._received: dict[str, int] = {}
        # Learn: what waits for a control
        self._learn: dict[str, Any] | None = None
        self._learn_ids = 0
        self.learned: dict | None = None  # what the last Learn captured
        self.heard: dict | None = None  # the last control heard while Learn waited (also on another channel)
        self.on_learned: Callable[[str, int, dict], None] = lambda route_id, index, spec: None

    # -- messages
    def tap(self, port_name: str, msg) -> None:
        """A message of the controller's own port (``MidiInput.tap``)."""
        self.handle(port_key(port_name), msg)

    def handle(self, device: str, msg) -> None:
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

    # -- ports
    def sync(self, devices: Iterable[str], controller=None, names: list[str] | None = None) -> None:
        """Make the open ports match the devices the enabled MIDI routes name. ``controller``: the app's ``MidiInput``;
        a device that is its port is not opened here (the controller's input hands its messages on). ``names``: the
        system's port list (read when not given; a failed listing changes nothing)."""
        wanted = {port_key(d): d for d in devices if d}
        via: dict[str, str] = {}
        for key, device in wanted.items():
            if controller is not None and self.controller_owns(device, controller):
                via[key] = "controller"
        need = [k for k in wanted if k not in via]
        if names is None and need:
            names = list_midi_inputs_checked()
            if names is None:
                return
        with self._lock:
            self._names = wanted
            self._via = via
            self._errors = {k: e for k, e in self._errors.items() if k in need}
        for key in [k for k in list(self._ports) if k not in need]:
            self._close(key)
        for key in need:
            port = self._ports.get(key)
            listed = match_port(wanted[key], names or [])
            if port is not None and (listed is None):
                self._close(key)  # pulled
                port = None
            if port is not None:
                continue
            if listed is None:
                self._set_error(key, f"no MIDI port matches '{wanted[key]}'")
                continue
            self._open(key, listed)

    @staticmethod
    def controller_owns(device: str, controller) -> bool:
        """Whether the controller's input owns this device: its open port is it, or it is not open yet and the port it
        looks for is this one (then it opens it, and a second open here would take the port from it)."""
        if controller.port_name:
            return port_key(controller.port_name) == port_key(device)
        wanted = controller.wanted_name().lower()
        return bool(wanted) and wanted in device.lower()

    def _open(self, key: str, name: str) -> None:
        if mido is None:
            self._set_error(key, "MIDI isn't available")
            return
        try:
            self._ports[key] = mido.open_input(name, callback=lambda msg, k=key: self.handle(k, msg))
            with self._lock:
                self._errors.pop(key, None)
            log.info("MIDI routes: opened '%s'", name)
        except Exception as exc:  # noqa: BLE001
            self._set_error(key, str(exc) or exc.__class__.__name__)

    def _set_error(self, key: str, message: str) -> None:
        with self._lock:
            if self._errors.get(key) != message:
                log.warning("MIDI routes: %s", message)
            self._errors[key] = message

    def _close(self, key: str) -> None:
        port = self._ports.pop(key, None)
        if port is not None:
            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        for key in list(self._ports):
            self._close(key)

    # -- what the page shows
    def status(self) -> dict:
        now = self._clock()
        with self._lock:
            devices = [
                {
                    "device": self._names[k],
                    "open": k in self._ports,
                    "via": self._via.get(k),
                    "error": self._errors.get(k),
                    "received": self._received.get(k, 0),
                    "age": round(now - self._last[k], 2) if k in self._last else None,
                }
                for k in self._names
            ]
            learn = self._learn
            return {
                "devices": devices,
                "learn": None
                if learn is None or now >= learn["until"]
                else {"id": learn["id"], "route": learn["route"], "index": learn["index"], "channel": learn["channel"], "seconds": round(learn["until"] - now, 1), "heard": self.heard},
                "learned": self.learned,
                "learn_seconds": LEARN_SECONDS,
            }
