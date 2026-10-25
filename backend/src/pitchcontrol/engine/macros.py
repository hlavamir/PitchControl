"""Macros: every controllable parameter, fed by the UI, MIDI and scenes.

A macro stores a *control value* in 0..1 (what a fader or MIDI CC sets). The
*value in range* maps it to ``min..max`` after quantising to ``steps``, exactly
like the vvvv ``Macro`` record.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

Kind = Literal["fader", "toggle", "button", "momentary", "radio"]
Page = Literal["general", "dimmers", "scenes", "system"]

# pages the MIDI controller can drive; the "Page …" radio macros select the active one
CONTROL_PAGES = ["general", "dimmers"]


@dataclass(frozen=True)
class MacroDef:
    name: str
    min: float = 0.0
    max: float = 1.0
    steps: int = 128
    kind: Kind = "fader"
    page: Page = "general"
    default: float = 0.0  # control value
    display_name: str = ""
    radio_group: str | None = None
    legacy_index: int | None = None  # index in the vvvv macros.ini / scene files
    # apply on release (UI) / once the knob stops moving (MIDI) instead of continuously,
    # so a colour does not sweep through the whole gradient during a show
    deferred: bool = False
    # how the UI shows the value in range: value × display_scale, with unit and decimals
    display_scale: float = 1.0
    unit: str = ""
    decimals: int = 2
    # the fader is logarithmic: the value in range runs from min to max by a constant ratio, so the control's middle is
    # the geometric mean (Mask Curve: 0.25 ... 4, 1 in the middle). min must be above 0.
    log_scale: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name


def _step(i: int) -> float:
    """Control value of step ``i`` of a 128-step fader, so a default lies exactly on the grid."""
    return i / 127


def _defs() -> list[MacroDef]:
    # The defaults are what a first start (and an empty scene slot) shows: a calm test pattern for
    # setting up the DMX output — the music changes nothing until Strobo or Audio Reactivity is raised.
    d: list[MacroDef] = [
        MacroDef("Strobo Decay", 0.1, 3.0, legacy_index=0, default=_step(61)),  # 1.49 s
        MacroDef("Strobo Brightness", legacy_index=1, default=1.0),
        MacroDef("Idle Attack", 0.1, 20.0, legacy_index=2, default=_step(15)),  # 2.45 s
        MacroDef("Idle Brightness", legacy_index=3, default=1.0),
        MacroDef("Hue A", -0.5, 0.5, legacy_index=4, deferred=True, display_scale=360, unit="°", decimals=0, default=_step(67)),  # +10°
        # renamed from "Glitches": it sets how much the audio drives the mask (see vvvv-patch-logic)
        MacroDef("Audio Reactivity", legacy_index=5),
        MacroDef("Hue B", -0.5, 0.5, legacy_index=6, deferred=True, display_scale=360, unit="°", decimals=0, default=_step(29)),  # −98°
        MacroDef("Strobo", 0.0, 0.95, legacy_index=7),
        MacroDef("Saturation A", default=1.0, deferred=True, display_scale=100, unit="%", decimals=0),
        MacroDef("Saturation B", default=1.0, deferred=True, display_scale=100, unit="%", decimals=0),
        MacroDef("Swap Colors", steps=2, kind="toggle", legacy_index=8),
        MacroDef("Auto Color Change", steps=2, kind="toggle", legacy_index=9),
        MacroDef("Vertical Symmetry", steps=2, kind="toggle", legacy_index=10, default=1.0),
        MacroDef("Strobo Bright. A", legacy_index=16, default=1.0),
        MacroDef("Idle Bright. A", legacy_index=17, default=1.0),
        MacroDef("Strobo Bright. B", legacy_index=18, default=1.0),
        MacroDef("Idle Bright. B", legacy_index=19, default=1.0),
        MacroDef("Mask Param A", -2.0, 2.0, legacy_index=20, default=_step(64)),  # slider at the middle
        MacroDef("Mask Param B", legacy_index=21, default=_step(64)),
        # the exponent of the mask before the fixtures' own idle remap (``mask ** value``): above 1 darker, below 1 brighter.
        # 129 steps put 1 exactly on the middle step. The default is 2.18, the step nearest 2.2, a cheap sRGB-like curve
        # (Miro, item 94): step 100 of 128 (2.2 itself lies between two steps). Not in the vvvv patch: no legacy index.
        MacroDef("Mask Curve", 0.25, 4.0, steps=129, default=100 / 128, log_scale=True),
        MacroDef("Invert Discoball", steps=2, kind="toggle", legacy_index=29),
        MacroDef("Fog Machine", steps=2, kind="momentary", legacy_index=30),
        MacroDef("Manual Strobo", steps=2, kind="momentary", legacy_index=31),
    ]
    for i, letter in enumerate("ABCD"):
        d.append(
            MacroDef(
                f"Mask {letter}",
                steps=2,
                kind="radio",
                radio_group="preset",
                default=1.0 if i == 1 else 0.0,  # B, Back & Forth
                legacy_index=12 + i,
            )
        )
    # dimmer names live in the rig (Rig.dimmer_names), they depend on the lights
    for i in range(16):
        d.append(MacroDef(f"Dimmer {i + 1:02d}", page="dimmers", default=1.0, legacy_index=32 + i))
    # active control page (UI tab / controller page), like the vvvv "General" / "Dimmers" tab macros
    for i, page in enumerate(CONTROL_PAGES):
        d.append(
            MacroDef(
                f"Page {page.title()}",
                steps=2,
                kind="radio",
                radio_group="page",
                page="system",
                default=1.0 if i == 0 else 0.0,
                legacy_index=92 + i,
            )
        )
    for i in range(8):
        d.append(MacroDef(f"Scene {i + 1} Save", steps=2, kind="button", page="scenes", legacy_index=64 + 2 * i))
        d.append(MacroDef(f"Scene {i + 1} Load", steps=2, kind="button", page="scenes", legacy_index=65 + 2 * i))
    return d


MACRO_DEFS: list[MacroDef] = _defs()

# Macros that came after the first scenes were saved: a scene without one of them gets the control value that gives the
# look it had when it was saved, instead of keeping whatever the macro was set to before the scene was loaded. Not the
# macro's default: Mask Curve's default became 2.18 (item 94), but those scenes were made with a curve of 1.
LATE_MACROS = {"Mask Curve": 0.5}


def quantise(control: float, steps: int) -> float:
    control = min(max(control, 0.0), 1.0)
    if steps and steps > 1:
        return math.floor(control * (steps - 1) + 0.5) / (steps - 1)  # round half up
    return control


class MacroBank:
    """Thread-safe store of macro control values."""

    def __init__(self, defs: list[MacroDef] | None = None):
        self.defs: dict[str, MacroDef] = {m.name: m for m in (defs or MACRO_DEFS)}
        self._values: dict[str, float] = {m.name: m.default for m in self.defs.values()}
        self._pending_buttons: set[str] = set()
        self._deferred: dict[str, tuple[float, float]] = {}  # name -> (value, time of last change)
        self._lock = threading.Lock()
        self.version = 0  # increments on every change (used for change detection)

    # -- reading
    def control(self, name: str) -> float:
        return self._values.get(name, 0.0)

    def value(self, name: str) -> float:
        """Value in range (quantised, mapped to min..max)."""
        m = self.defs.get(name)
        if m is None:
            return 0.0
        q = quantise(self._values[name], m.steps)
        if m.log_scale:
            return m.min * (m.max / m.min) ** q
        return m.min + q * (m.max - m.min)

    def on(self, name: str) -> bool:
        return self._values.get(name, 0.0) > 0.5

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._values)

    # -- writing
    def set(self, name: str, control: float) -> bool:
        m = self.defs.get(name)
        if m is None:
            log.warning("unknown macro '%s'", name)
            return False
        control = min(max(float(control), 0.0), 1.0)
        with self._lock:
            if m.kind == "radio" and m.radio_group:
                if control <= 0.5:
                    return True  # a radio button cannot be switched off directly
                for other in self.defs.values():
                    if other.radio_group == m.radio_group:
                        self._values[other.name] = 0.0
                control = 1.0
            if m.kind == "button":
                if control > 0.5:
                    self._pending_buttons.add(name)
                return True
            self._values[name] = control
            self.version += 1
        return True

    def toggle(self, name: str) -> None:
        self.set(name, 0.0 if self.on(name) else 1.0)

    def set_deferred(self, name: str, control: float, now: float) -> None:
        """Remember a value from a moving knob; ``apply_settled`` applies it once the knob rests."""
        if name not in self.defs:
            return
        with self._lock:
            self._deferred[name] = (min(max(float(control), 0.0), 1.0), now)

    def apply_settled(self, now: float, settle_s: float) -> None:
        with self._lock:
            ready = [n for n, (_, t) in self._deferred.items() if now - t >= settle_s]
            values = {n: self._deferred.pop(n)[0] for n in ready}
        for name, value in values.items():
            self.set(name, value)

    def cancel_deferred(self, name: str) -> None:
        with self._lock:
            self._deferred.pop(name, None)

    def pending(self) -> dict[str, float]:
        with self._lock:
            return {n: v for n, (v, _) in self._deferred.items()}

    def take_buttons(self) -> set[str]:
        """Return and clear the buttons pressed since the last call."""
        with self._lock:
            pressed, self._pending_buttons = self._pending_buttons, set()
        return pressed

    def load(self, values: dict[str, float], source: str = "") -> None:
        unknown = [k for k in values if k not in self.defs]
        if unknown:
            log.warning("%s: unknown macros ignored: %s", source or "macro snapshot", ", ".join(unknown))
        with self._lock:
            for name, control in values.items():
                m = self.defs.get(name)
                if m is None or m.kind == "button":
                    continue
                self._values[name] = min(max(float(control), 0.0), 1.0)
            self.version += 1

    def reset_to_defaults(self) -> None:
        """Every macro a scene stores (General and Dimmers) back to its default: an empty scene slot."""
        with self._lock:
            for m in self.defs.values():
                if m.kind != "button" and m.page in ("general", "dimmers"):
                    self._values[m.name] = m.default
            self._deferred.clear()
            self.version += 1

    @property
    def control_page(self) -> str:
        return CONTROL_PAGES[self.radio_index("page")]

    def set_control_page(self, page: str) -> None:
        if page in CONTROL_PAGES:
            self.set(f"Page {page.title()}", 1.0)

    def radio_index(self, group: str) -> int:
        members = [m for m in self.defs.values() if m.radio_group == group]
        for i, m in enumerate(members):
            if self._values[m.name] > 0.5:
                return i
        return 0


def from_legacy_values(values: list[float]) -> dict[str, float]:
    """Convert the 128 control values of a vvvv scene / macros.ini to ``{macro name: value}``."""
    out: dict[str, float] = {}
    for m in MACRO_DEFS:
        if m.legacy_index is not None and m.legacy_index < len(values) and m.kind != "button":
            out[m.name] = values[m.legacy_index]
    return out
