"""MIDI controller input: CC and note messages → macros, using a ``controllers/*.json`` mapping.

A message is matched to a mapping by its kind (CC / note), number and channel. Several mappings can
share a control when they differ in the control page or in the shift state (the same physical fader
drives other macros on the Dimmers page; a button saves a scene while shift is held); the most
specific one wins.

Faders and knobs use *value scaling* (soft takeover): while the hardware position and the macro's
value differ, the macro follows the fader proportionally, so both reach the end of the range together
and nothing jumps.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from ..config.models import Controller, MidiMapping

log = logging.getLogger(__name__)

try:
    import mido
except ImportError:  # pragma: no cover
    mido = None

SYNC_TOLERANCE = 1.5 / 127  # hardware and macro this close count as the same position
LEARN_SECONDS = 20.0  # the learn mode lets go by itself, so a forgotten one doesn't leave the controller dead


def list_midi_inputs() -> list[str]:
    if mido is None:
        return []
    try:
        return list(mido.get_input_names())
    except Exception as exc:  # noqa: BLE001
        log.warning("cannot list MIDI inputs: %s", exc)
        return []


def decode_step(value: int, encoder: str) -> int:
    """The signed number of steps a relative encoder message stands for."""
    if encoder == "offset_64":
        return value - 64
    if encoder == "sign_bit":
        return value if value < 64 else -(value - 64)
    return value if value < 64 else value - 128  # two's complement


def scale(h: float, h0: float, s0: float) -> float:
    """Value scaling: the macro value for hardware position ``h``, when the macro stood at ``s0``
    while the hardware was at ``h0``. Moving up both reach 1 together, moving down both reach 0."""
    if h >= h0:
        return s0 + (h - h0) * (1.0 - s0) / (1.0 - h0) if h0 < 1.0 else s0
    return s0 * h / h0


@dataclass
class _Takeover:
    last: float  # the value this module wrote last: if the macro differs, something else changed it
    h0: float | None = None  # hardware position and macro value where the scaling started (None: 1:1)
    s0: float = 0.0


class MidiInput:
    def __init__(self, controller: Controller | None, port_override: str | None, macros, ignored=None):
        self.controller = controller
        self.ignored = ignored or (lambda macro: False)  # macro → True: drop the message (unassigned dimmer)
        self.port_override = port_override
        self.macros = macros
        self.port = None
        self.port_name: str | None = None
        self.error: str | None = None
        self.by_control: dict[tuple[str, int], list[MidiMapping]] = {}
        self.shift_controls: set[tuple[str, int, int]] = set()  # (kind, number, channel) of the shift buttons held down
        # (kind, number, channel) of a held button -> the momentary mapping that got its press: the release goes
        # there, whatever shift state or control page is current when the button is let go
        self._held: dict[tuple[str, int, int], MidiMapping] = {}
        # controls whose last message was a press (CC above 63, note on): a CC of 0 from one of them is a release
        self._down: set[tuple[str, int, int]] = set()
        self._takeover: dict[str, _Takeover] = {}
        self._layer: tuple[str, bool] | None = None  # (control page, shift) the takeover state belongs to
        self._learn_until = 0.0
        self.recent: deque[dict] = deque(maxlen=20)  # MIDI monitor for the Inputs page
        self.received = 0
        self._ignored_channels: set[int] = set()
        if controller:
            for m in controller.mappings:
                self.by_control.setdefault((m.type, m.number), []).append(m)
                if m.macro is not None and m.macro not in macros.defs:
                    log.warning("controller '%s': %s %d mapped to unknown macro '%s'", controller.name, m.type, m.number, m.macro)
            # a shift button always wins on its control: whatever else is mapped there never fires
            shifts = {(m.type, m.number, m.channel or controller.channel) for m in controller.mappings if m.mode == "shift"}
            for m in controller.mappings:
                if m.mode != "shift" and (m.type, m.number, m.channel or controller.channel) in shifts:
                    log.warning(
                        "controller '%s': %s %d on channel %d is the shift button, so '%s' mapped to it never fires",
                        controller.name, m.type, m.number, m.channel or controller.channel, m.macro,
                    )

    # -- port
    def start(self) -> None:
        if mido is None or self.controller is None:
            return
        match = (self.port_override or self.controller.port_match or "").lower()
        names = list_midi_inputs()
        name = next((n for n in names if match and match in n.lower()), None)
        if name is None:
            self.error = f"MIDI input matching '{match}' not found"
            log.warning(self.error)
            return
        try:
            self.port = mido.open_input(name, callback=self.handle)
            self.port_name = name
            self.error = None
            log.info("MIDI input: %s (controller '%s')", name, self.controller.name)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            log.error("MIDI input failed: %s", exc)

    def release_all(self) -> None:
        """Let go of everything the controller still holds: a momentary macro (fog!) must not stay on when the input
        is closed or the mapping is swapped while a button is down."""
        held, self._held = self._held, {}
        for m in held.values():
            if m.macro in self.macros.defs:
                self.macros.set(m.macro, 1.0 if m.invert else 0.0)
        self.shift_controls.clear()
        self._down.clear()
        self._takeover.clear()

    def stop(self) -> None:
        self.release_all()
        if self.port is not None:
            try:
                self.port.close()
            except Exception:  # noqa: BLE001
                pass
        self.port = None

    # -- learn mode: messages are shown in the monitor but move nothing
    def set_learning(self, on: bool) -> None:
        self._learn_until = time.monotonic() + LEARN_SECONDS if on else 0.0

    @property
    def learning(self) -> bool:
        return time.monotonic() < self._learn_until

    @property
    def shift(self) -> bool:
        return bool(self.shift_controls)

    # -- messages
    def handle(self, msg) -> None:
        if msg.type in ("clock", "active_sensing"):
            return
        self.received += 1
        kind, number, value = None, 0, 0
        if msg.type == "control_change":
            kind, number, value = "cc", msg.control, msg.value
        elif msg.type in ("note_on", "note_off"):
            kind, number, value = "note", msg.note, (msg.velocity if msg.type == "note_on" else 0)
        channel = getattr(msg, "channel", 0) + 1
        entry = {
            "t": round(time.time(), 2),
            "seq": self.received,
            "text": str(msg),
            "kind": kind,
            "number": number,
            "channel": channel,
            "value": value,
            "macro": None,
            "note": "",
            "shift": self.shift,  # whether a shift button was held when this arrived (Learn pre-fills "with shift")
            # what Learn may pick: not the let-go of a button (it would learn a button held from before Learn) and not
            # a shift button (it would learn the shift button onto the row); the Shift row itself may take a shift button
            "release": False,
            "shift_button": False,
            "learnable": kind is not None,
        }
        self.recent.append(entry)
        if kind is None:
            entry["note"] = "not a CC or note message"
            return
        key = (kind, number, channel)
        entry["release"] = value == 0 and (kind == "note" or key in self._down)
        if value > (63 if kind == "cc" else 0):
            self._down.add(key)
        else:
            self._down.discard(key)
        if self.controller is not None:
            entry["shift_button"] = any(
                m.mode == "shift" and (m.channel or self.controller.channel) == channel for m in self.by_control.get((kind, number), [])
            )
        entry["learnable"] = not entry["release"] and not entry["shift_button"]
        if self.controller is None:
            entry["note"] = "no controller selected"
            return

        learning = self.learning  # Learn: new presses and fader moves are shown but muted; shift and releases still count
        candidates = self.by_control.get((kind, number), [])
        label = "CC" if kind == "cc" else "note"
        if not candidates:
            entry["note"] = "learning: not applied" if learning else f"{label} {number} not mapped"
            return
        here = [m for m in candidates if (m.channel or self.controller.channel) == channel]
        if not here:
            expected = candidates[0].channel or self.controller.channel
            entry["note"] = "learning: not applied" if learning else f"channel {channel}, mapping expects {expected}"
            if channel not in self._ignored_channels:
                self._ignored_channels.add(channel)
                log.warning("MIDI: ignoring %s on channel %d (controller '%s' maps it on channel %d)", label, channel, self.controller.name, expected)
            return

        pressed = value > 63 if kind == "cc" else value > 0
        for m in here:  # the shift buttons first: they change which layer the other mappings are in
            if m.mode == "shift":
                before = self.shift
                (self.shift_controls.add if pressed else self.shift_controls.discard)(key)
                entry["note"] = "shift " + ("on" if self.shift else "off")
                if before != self.shift:
                    self._takeover.clear()
                return

        if not pressed and key in self._held:  # the release goes to the mapping that got the press
            m = self._held.pop(key)
            entry["macro"] = m.macro
            self.macros.set(m.macro, 1.0 if m.invert else 0.0)
            return
        if learning:
            entry["note"] = "learning: not applied"
            return

        page = self.macros.control_page
        if self._layer != (page, self.shift):  # a new layer: the hardware no longer matches the macros
            self._layer = (page, self.shift)
            self._takeover.clear()
        shift = "on" if self.shift else "off"
        fitting = [m for m in here if m.page in (None, page) and m.shift in (None, shift)]
        if not fitting:
            entry["note"] = f"{label} {number} is not mapped on page '{page}'" + (" with shift" if self.shift else "")
            return
        m = max(fitting, key=lambda m: (m.page is not None) + (m.shift is not None))
        self._apply(m, kind, value, pressed, entry)
        if m.mode == "momentary" and pressed and entry["macro"]:
            self._held[key] = m

    def _apply(self, m: MidiMapping, kind: str, value: int, pressed: bool, entry: dict) -> None:
        name = m.macro
        entry["macro"] = name
        if self.ignored(name):
            entry["macro"] = None
            entry["note"] = f"{name} is unassigned (no fixture uses it), ignored"
            return
        macro_def = self.macros.defs.get(name)
        if macro_def is None:
            entry["macro"] = None
            entry["note"] = f"unknown macro '{name}'"
            return
        flip = (lambda x: 1.0 - x) if m.invert else (lambda x: x)
        if m.mode == "absolute":
            self._absolute(name, macro_def, flip(value / 127.0))
        elif m.mode == "relative":
            step = decode_step(value, m.encoder) * (-1 if m.invert else 1)
            if step:
                self._put(name, macro_def, self._current(name, macro_def) + step * m.sensitivity / 127.0)
        elif m.mode == "momentary":
            self.macros.set(name, 1.0 if pressed != m.invert else 0.0)
        elif m.mode == "toggle":
            if pressed:
                self.macros.toggle(name)
        elif m.mode == "trigger" and pressed:
            self.macros.set(name, 1.0)

    # -- macro values
    def _current(self, name: str, macro_def) -> float:
        """What the macro will be: a deferred knob's pending value, else its value."""
        if macro_def.deferred:
            pending = self.macros.pending().get(name)
            if pending is not None:
                return pending
        return self.macros.control(name)

    def _put(self, name: str, macro_def, value: float) -> None:
        value = min(max(value, 0.0), 1.0)
        if macro_def.deferred:
            self.macros.set_deferred(name, value, time.monotonic())
        else:
            self.macros.set(name, value)

    def _absolute(self, name: str, macro_def, h: float) -> None:
        if macro_def.kind != "fader":  # toggles and buttons have no position to take over
            self._put(name, macro_def, h)
            return
        current = self._current(name, macro_def)
        state = self._takeover.get(name)
        if state is None or abs(current - state.last) > 1e-6:  # first message, or something else moved the macro
            state = _Takeover(last=current)
            if abs(h - current) > SYNC_TOLERANCE:
                state.h0, state.s0 = h, current
            self._takeover[name] = state
        if state.h0 is None:
            value = h
        else:
            value = scale(h, state.h0, state.s0)
            if abs(value - h) <= SYNC_TOLERANCE:  # arrived at the end: from here on 1:1
                value, state.h0 = h, None
        state.last = min(max(value, 0.0), 1.0)
        self._put(name, macro_def, value)

    def status(self) -> dict:
        return {
            "port": self.port_name,
            "port_override": self.port_override or None,  # section 02's MIDI port; wins over the controller file's
            "error": self.error,
            "controller": self.controller.name if self.controller else None,
            "channel": self.controller.channel if self.controller else None,
            "received": self.received,
            "shift": self.shift,
            "learning": self.learning,
            "recent": list(self.recent)[::-1],
        }
