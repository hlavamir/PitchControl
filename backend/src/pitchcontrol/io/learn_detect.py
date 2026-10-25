"""What the hardware is that Learn is listening to, from the messages one control sent (item 93).

Learn (``MidiInput``) watches the control it caught first for a moment and hands what that control sent here, as
``(value, time)`` pairs: ``classify`` says whether it is a gate button, a trigger button, a latching button, a fader or an
encoder (with the way it sends its steps), and ``fill_for`` turns that and the kind of macro on the row into the mode the
row gets. Both are pure: the clock and the ports stay in ``midi_in``.

A note sends its velocity (0 for a note off or a note on with velocity 0); a CC button counts as pressed from 64 up, like
the engine's own mapping does.
"""

from __future__ import annotations

from dataclasses import dataclass

GATE_MAX_HOLD = 1.0  # a press that is let go within this many seconds is a gate button; a later 0 is the second press of a latching one
BURST_GAP = 0.5  # presses of the encoder's "down" value (127) this close are a turned encoder, further apart they are a button pressed twice
FADER_MIN_VALUES = 3  # that many different values (outside the encoder patterns) is a fader

# the values an encoder sends for a step of 1 to 4, per kind of encoder (acceleration sends the larger ones)
_UP = range(1, 5)  # two's complement and sign bit: up
_TWOS_DOWN = range(124, 128)  # two's complement: down
_SIGN_DOWN = range(65, 69)  # sign bit: down; offset 64: up
_OFFSET_DOWN = range(60, 64)  # offset 64: down

ENCODER_LABEL = {"twos_complement": "two's complement", "sign_bit": "sign bit", "offset_64": "offset 64"}


@dataclass(frozen=True)
class Detection:
    kind: str  # gate, trigger, latching, fader, encoder or undecided
    encoder: str | None = None  # encoder: twos_complement, sign_bit or offset_64
    ask: str | None = None  # undecided: what to ask the user: press_again, turn or turn_other

    @property
    def button(self) -> bool:
        return self.kind in ("gate", "trigger", "latching")

    @property
    def label(self) -> str:
        if self.kind == "encoder":
            return f"encoder ({ENCODER_LABEL[self.encoder]})"
        return {"gate": "gate button", "trigger": "trigger button", "latching": "latching button", "fader": "fader"}.get(self.kind, "unclear")


def _undecided(ask: str) -> Detection:
    return Detection("undecided", ask=ask)


def _encoder(values: list[int], times: list[float]) -> Detection | None:
    """The encoder these values are, ``undecided`` when they are one but one direction can't say which, else None. Values
    around 1 / 127 are two's complement, 1 / 65 sign bit, 63 / 65 offset 64; a control that sent each value once isn't
    taken for an encoder (a fader at its end does that), nor is one that sent 0 or 64 (an encoder has no resting value)."""
    if len(values) < 2 or any(v in (0, 64) for v in values):
        return None
    up = any(v in _UP for v in values)
    twos = any(v in _TWOS_DOWN for v in values)
    sign = any(v in _SIGN_DOWN for v in values)
    offset = any(v in _OFFSET_DOWN for v in values)
    if not all(v in _UP or v in _TWOS_DOWN or v in _SIGN_DOWN or v in _OFFSET_DOWN for v in values):
        return None
    bands = sum((up, twos, sign, offset))
    repeated = len(values) > len(set(values))
    if twos and not sign and not offset:  # 127 alone is also a trigger button pressed again: a turned encoder sends them in a burst
        burst = any(b - a < BURST_GAP for a, b in zip(times, times[1:]))
        return Detection("encoder", "twos_complement") if (up or burst) and (repeated or bands == 2) else None
    if not (repeated or bands > 1):
        return None
    if offset and not twos:
        return Detection("encoder", "offset_64")
    if sign and up and not twos and not offset:
        return Detection("encoder", "sign_bit")
    if up and not (twos or sign or offset):
        return Detection("encoder", "twos_complement")  # only "up": the same for two's complement and sign bit
    if sign and not (up or twos or offset):
        return _undecided("turn_other")  # 65 alone is sign bit "down" or offset 64 "up": the other direction tells
    return None


def _button(kind: str, values: list[int], times: list[float]) -> Detection:
    press = (lambda v: v > 0) if kind == "note" else (lambda v: v > 63)
    first = next((i for i, v in enumerate(values) if press(v)), None)
    if first is None:
        return _undecided("press_again" if kind == "note" else "turn")
    for i in range(first + 1, len(values)):
        if values[i] == 0:  # let go (a note off, or CC 0)
            return Detection("gate" if times[i] - times[first] <= GATE_MAX_HOLD else "latching")
    presses = sum(1 for v in values if press(v))
    return Detection("trigger") if presses > 1 else _undecided("press_again")


def classify(kind: str, messages: list[tuple[int, float]]) -> Detection:
    """What the control that sent ``messages`` (value, time in seconds, oldest first; ``kind`` is ``"cc"`` or ``"note"``)
    is. ``undecided`` carries what to ask: ``press_again`` (a button that was pressed once), ``turn`` (a knob that sent
    one value, or two) or ``turn_other`` (an encoder that only turned one way, and that way doesn't tell the type)."""
    values = [v for v, _ in messages]
    times = [t for _, t in messages]
    if not values:
        return _undecided("turn")
    if kind == "note":
        return _button(kind, values, times)
    encoder = _encoder(values, times)
    if encoder is not None:
        return encoder
    if len(set(values)) >= FADER_MIN_VALUES:
        return Detection("fader")
    pressed = {v for v in values if v > 63}
    if all(v == 0 or v > 63 for v in values) and len(pressed) == 1 and (len(values) > 1 or 127 in pressed):
        return _button(kind, values, times)  # one press value and 0: a button (one press alone: ask for another)
    return _undecided("turn")


def fill_for(detection: Detection, macro_kind: str | None, macro: str | None = None) -> tuple[str | None, str | None, str, bool | None]:
    """What Learn sets on the row for this hardware and this kind of macro: ``(mode, encoder, note, latching)``. A mode of
    None keeps what the row had (the hardware doesn't fit the macro, or it couldn't be told), and the note says why;
    ``latching`` (item 97) is True for a button that switches itself on the controller (every press counts: the mapping
    reads every change of its value as a press), False for any other button, None when the row keeps it. ``macro_kind`` is
    the macro's ``kind``: a fader is a value, a toggle an on / off switch, a momentary one a hold, a button or radio one
    that only fires; ``macro`` is its name, for the note."""
    kind = detection.kind
    if kind == "undecided":
        return None, None, "couldn't tell what it sends, mode kept", None
    if macro_kind == "fader":
        if kind == "fader":
            return "absolute", None, "", None
        if kind == "encoder":
            return "relative", detection.encoder, "", None
        return None, None, f"a {detection.label} on a fader, mode kept", None
    if not detection.button:
        if macro_kind is None:
            return None, None, "", None
        return None, None, f"a {detection.label} on a switch or button, mode kept", None
    latching = kind == "latching"
    if macro_kind is None:
        return None, None, "", latching
    if macro_kind == "toggle":
        return "toggle", None, "", latching  # a gate or trigger button flips it on every press, a latching one on every change
    if macro_kind == "momentary":
        if latching:
            name = macro or "the macro"
            return "momentary", None, f"this button latches on the controller: {name} stays on until you press it again. For hold, set it to Gate in the controller's software", True
        if kind == "gate":
            return "momentary", None, "", False
        return "trigger", None, "the button can't be held, it only fires", False
    return "trigger", None, "", latching
