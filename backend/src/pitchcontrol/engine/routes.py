"""Routes (Control Desk page, item 58): live input that overrides output channels.

A route copies a block of input channels (an Art-Net universe, or the DMX input) onto a block of output channels:
source, first input channel, count (1 to 512), output universe, first output channel. A **MIDI** route (item 59) has a
MIDI device and MIDI channel instead, and each of its output channels has its own input: a CC, a 14-bit CC pair, a
note, or a constant. Three layers, the later one wins: the app's own output (fixtures, fog) → routes → manual overrides (``Overrides``). A manual value on a routed
channel sits on top and doesn't delete the route; releasing it shows the route's value again.

An overridden channel stays overridden (Miro, 2026-10-22): the input store keeps the last values of a source, so a
sender that goes quiet leaves its channels where they were. A route lets go when it is switched off or deleted. A
route whose source has never sent anything changes nothing, so the app's output shows.

Routes are saved to ``state/routes.json`` and restored on start, like the overrides.
"""

from __future__ import annotations

import itertools
import json
import logging
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..config.loader import write_json
from ..config.models import Model
from ..io.live_input import DMX_KEY, LiveInput, artnet_key
from ..io.midi_in import port_key
from ..io.midi_routes import MidiRouteHub

log = logging.getLogger(__name__)

RouteKind = Literal["artnet", "dmx", "midi"]
MidiType = Literal["none", "cc", "cc14", "note", "const"]
MAX_ROUTES = 256
MAX_MIDI_COUNT = 64  # a MIDI route sets each of its channels by hand: it is a block of knobs, not a universe


class MidiChannel(Model):
    """The input of one output channel of a MIDI route. ``none``: nothing yet (the fixtures show); ``cc``: a control
    change 0..127 scaled to 0..255; ``cc14``: a pair, ``number`` is the MSB (0 to 31) and ``number + 32`` the LSB;
    ``note``: the velocity while it is held (``velocity``) or 255 while it is held (``onoff``), 0 after; ``const``:
    ``value`` (the fallback for a channel no control drives)."""

    type: MidiType = "none"
    number: int = Field(default=0, ge=0, le=127)
    value: int = Field(default=0, ge=0, le=255)
    note_mode: Literal["velocity", "onoff"] = "velocity"

    @model_validator(mode="after")
    def _pair(self) -> "MidiChannel":
        if self.type == "cc14" and self.number > 31:
            raise ValueError("a 14-bit CC pair starts at CC 0 to 31 (its second half is 32 higher)")
        return self


class Route(Model):
    id: str = ""  # made by the app when empty
    name: str = ""
    enabled: bool = True
    kind: RouteKind = "artnet"
    artnet_universe: int = Field(default=0, ge=0, le=0x7FFF)  # the raw Art-Net port address (net, sub-net, universe)
    first_input: int = Field(default=1, ge=1, le=512)
    count: int = Field(default=1, ge=1, le=512)
    universe: int = Field(default=0, ge=0)  # the output universe (as on the Rig page and in Connections)
    first_output: int = Field(default=1, ge=1, le=512)
    # MIDI routes (item 59)
    midi_device: str = ""  # a MIDI input port name, as Connections → MIDI lists it
    midi_channel: int = Field(default=1, ge=1, le=16)
    channels: list[MidiChannel] = Field(default_factory=list)  # one per output channel, in order

    @model_validator(mode="after")
    def _fits(self) -> "Route":
        if self.kind == "midi":
            if self.count > MAX_MIDI_COUNT:
                raise ValueError(f"a MIDI route has at most {MAX_MIDI_COUNT} channels")
            # one input per output channel: the list follows the count
            self.channels = [*self.channels[: self.count], *(MidiChannel() for _ in range(self.count - len(self.channels)))]
        else:
            self.channels = []
        if self.first_input + self.count - 1 > 512:
            raise ValueError(f"input channels {self.first_input} to {self.first_input + self.count - 1} don't exist (a universe has 512)")
        if self.first_output + self.count - 1 > 512:
            raise ValueError(f"output channels {self.first_output} to {self.first_output + self.count - 1} don't exist (a universe has 512)")
        return self

    @property
    def source_key(self) -> str:
        return DMX_KEY if self.kind == "dmx" else artnet_key(self.artnet_universe)

    def label(self) -> str:
        return self.name or f"{self.source_label()} → {self.universe}:{self.first_output}"

    def source_label(self) -> str:
        if self.kind == "midi":
            return f"MIDI {self.midi_device or '?'} ch {self.midi_channel}"
        return "DMX input" if self.kind == "dmx" else f"Art-Net {self.artnet_universe}"

    def last_output(self) -> int:
        return self.first_output + self.count - 1


class Routes:
    def __init__(self) -> None:
        self._routes: list[Route] = []
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.version = 0  # bumped on every change (autosave)

    # -- edit
    def set_all(self, routes: list[Route]) -> None:
        """Replace the list. A route without an id gets one; two with the same id (a copy) are told apart."""
        if len(routes) > MAX_ROUTES:
            raise ValueError(f"at most {MAX_ROUTES} routes")
        with self._lock:
            used: set[str] = set()
            out = []
            for r in routes:
                r = r.model_copy()
                if not r.id or r.id in used:
                    r.id = self._new_id(used)
                used.add(r.id)
                out.append(r)
            self._routes = out
            self.version += 1

    def _new_id(self, used: set[str]) -> str:
        known = used | {r.id for r in self._routes}
        while True:
            candidate = f"r{next(self._ids)}"
            if candidate not in known:
                return candidate

    def add(self, route: Route) -> Route:
        """Append one route (it gets an id)."""
        with self._lock:
            if len(self._routes) >= MAX_ROUTES:
                raise ValueError(f"at most {MAX_ROUTES} routes")
            route = route.model_copy(update={"id": self._new_id(set())})
            self._routes.append(route)
            self.version += 1
            return route

    def patch(self, route_id: str, fields: dict) -> Route:
        """Change some fields of one route, so two quick edits (or two pages) never overwrite each other's field. When a
        first channel moves up and the count isn't given, the count shrinks to fit. KeyError: no such route."""
        with self._lock:
            for i, r in enumerate(self._routes):
                if r.id != route_id:
                    continue
                data = {**r.model_dump(), **{k: v for k, v in fields.items() if k in Route.model_fields and k != "id"}}
                if "count" not in fields:
                    data["count"] = max(1, min(data["count"], 513 - data["first_input"], 513 - data["first_output"]))
                self._routes[i] = new = Route.model_validate(data)
                self.version += 1
                return new
        raise KeyError(route_id)

    def remove(self, route_id: str) -> None:
        with self._lock:
            kept = [r for r in self._routes if r.id != route_id]
            if len(kept) == len(self._routes):
                raise KeyError(route_id)
            self._routes = kept
            self.version += 1

    def clear(self) -> int:
        with self._lock:
            n = len(self._routes)
            self._routes = []
            self.version += 1
        return n

    def all(self) -> list[Route]:
        with self._lock:
            return list(self._routes)

    def __len__(self) -> int:
        return len(self._routes)

    # -- the frame
    def apply(self, universes: dict[int, bytearray], live: LiveInput, midi: MidiRouteHub | None = None) -> None:
        """Write what the routes carry into the frame, after fixtures and fog and before the manual overrides. Routes
        later in the list win on a channel two of them cover."""
        with self._lock:
            routes = [r for r in self._routes if r.enabled]
        latest: dict[str, bytes | None] = {}
        for r in routes:
            if r.kind == "midi":
                if midi is not None and r.midi_device:
                    self._apply_midi(universes, r, midi)
                continue
            key = r.source_key
            if key not in latest:
                latest[key] = live.latest(key)
            values = latest[key]
            if values is None:  # the source has never sent: leave the app's own output
                continue
            chunk = values[r.first_input - 1 : r.first_input - 1 + r.count]
            universes.setdefault(r.universe, bytearray(512))[r.first_output - 1 : r.first_output - 1 + len(chunk)] = chunk

    @staticmethod
    def _apply_midi(universes: dict[int, bytearray], r: Route, midi: MidiRouteHub) -> None:
        device = port_key(r.midi_device)
        frame = None
        for i, spec in enumerate(r.channels):
            v = midi.value(device, r.midi_channel, spec)
            if v is not None:
                if frame is None:
                    frame = universes.setdefault(r.universe, bytearray(512))
                frame[r.first_output - 1 + i] = v

    def patch_channel(self, route_id: str, index: int, fields: dict) -> Route:
        """Change the input of one output channel of a MIDI route (``index`` from 0)."""
        with self._lock:
            for i, r in enumerate(self._routes):
                if r.id != route_id:
                    continue
                if r.kind != "midi" or not 0 <= index < len(r.channels):
                    raise KeyError(f"{route_id}[{index}]")
                channels = [c.model_dump() for c in r.channels]
                channels[index] = {**channels[index], **fields}
                self._routes[i] = new = Route.model_validate({**r.model_dump(), "channels": channels})
                self.version += 1
                return new
        raise KeyError(route_id)

    # -- what the page shows
    def status(self, sources: dict[str, dict], midi: dict | None = None) -> list[dict]:
        """Each route with whether its source has sent, and how long ago (``sources``: the input store's snapshot by
        key; ``midi``: the MIDI hub's status, for the routes of a MIDI device)."""
        devices = {port_key(d["device"]): d for d in (midi or {}).get("devices", [])}
        out = []
        for r in self.all():
            extra: dict = {}
            if r.kind == "midi":
                d = devices.get(port_key(r.midi_device))
                info = {"age": d["age"], "pps": 0.0} if d and d["age"] is not None else None
                extra = {"midi_open": bool(d and d["open"]), "midi_error": d["error"] if d else None}
            else:
                info = sources.get(r.source_key)
            out.append({**r.model_dump(mode="json"), **extra, "seen": info is not None, "age": info["age"] if info else None, "pps": info["pps"] if info else 0.0})
        return out

    def midi_overlaps(self, midi_input) -> list[dict]:
        """CCs and notes of MIDI routes that the app's MIDI mapping uses too, on the same MIDI channel: a warning, not a
        block (both react). The mapping listens to every device that is on (item 89), so the device doesn't matter.
        ``midi_input``: the app's ``MidiInput`` (its controller file)."""
        controller = getattr(midi_input, "controller", None)
        if controller is None:
            return []
        out = []
        for r in self.all():
            if r.kind != "midi" or not r.enabled:
                continue
            for i, spec in enumerate(r.channels):
                if spec.type not in ("cc", "cc14", "note"):
                    continue
                kind = "note" if spec.type == "note" else "cc"
                for number in [spec.number, spec.number + 32] if spec.type == "cc14" else [spec.number]:
                    macros = sorted({m.macro for m in controller.mappings if m.macro and m.type == kind and m.number == number and (m.channel or controller.channel) == r.midi_channel})
                    if macros:
                        label = ("CC" if kind == "cc" else "note") + f" {number}"
                        text = f"{label} on {r.midi_device} also drives {', '.join(macros)} in the MIDI mapping: both will react"
                        out.append({"route": r.id, "index": i, "kind": kind, "number": number, "macros": macros, "text": text})
        return out

    def overlaps(self) -> list[dict]:
        """Output channels that two or more enabled routes cover: ``{universe, first, last, routes: [ids]}``, contiguous
        channels with the same routes merged (the later route wins there)."""
        covered: dict[tuple[int, int], list[str]] = {}
        for r in self.all():
            if not r.enabled:
                continue
            for ch in range(r.first_output, r.last_output() + 1):
                covered.setdefault((r.universe, ch), []).append(r.id)
        out: list[dict] = []
        for (u, ch), ids in sorted(covered.items()):
            if len(ids) < 2:
                continue
            last = out[-1] if out else None
            if last and last["universe"] == u and last["last"] == ch - 1 and last["routes"] == ids:
                last["last"] = ch
            else:
                out.append({"universe": u, "first": ch, "last": ch, "routes": ids})
        return out

    # -- persistence
    def load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            routes = [Route.model_validate(r) for r in data.get("routes", [])]
        except (OSError, ValueError, AttributeError) as exc:
            log.error("%s: cannot restore the routes: %s", path, exc)
            return
        self.set_all(routes)
        if routes:
            log.warning("restored %d route(s) from %s", len(routes), path)

    def save(self, path: Path) -> None:
        write_json(path, {"routes": [r.model_dump(mode="json") for r in self.all()]})
