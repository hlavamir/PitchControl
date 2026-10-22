"""Open Fixture Library (OFL) fixture JSON -> a PitchControl fixture type.

OFL's own docs say its JSON format may change without warning and should be converted, not read live, so this
module and ``importer.py`` are the one place that knows both formats. This module is pure (no network, no files):
``convert_fixture`` takes the parsed OFL JSON and returns the modes as dicts; ``importer.py`` wraps them into a whole
type that keeps the OFL data, ``online.py`` fetches from OFL's GitHub, and ``tools/fixture_library.py`` generates the
shipped types.

The mapping (item 50 of the PitchControl dev task list; part of the app since item 53, File → Import Fixture):

* every OFL mode becomes a channel mode with its own pixel count (the number of pixels or groups its matrix block
  repeats; 1 for a mode without one);
* colour channels that form R G B (W) become the ``pixels`` block, per pixel when OFL repeats them over a matrix;
  a warm or cold white counts as W;
* a strobe / shutter channel becomes ``shutter``, with the open value and the fastest plain strobe value read from
  its capabilities (not always 0 and 255: 0..5 and 251..255 are both "open" on the Cameo ROOT Par and Q-Spot);
* the master dimmer is what the shipped types do: held at 255 when the mode mixes colours itself (the colours carry
  the brightness), an ``I`` pixel (it follows the brightness) when the mode has no colour channels;
* everything else (amber, UV, programs, speed, sound, delay, mode select, fine channels) is a named constant at its
  OFL default value, 0 unless OFL says otherwise; a colour preset that is a mode's only colour source is held at
  its "White" preset;
* a channel that switches meaning with another channel (OFL "switching channels") is read with the controlling
  channel at its default value, i.e. in the colour-mixing function.

A mode PitchControl can't express (a dimmer, amber or strobe per pixel, the pixels interleaved with other channels,
a hue / CCT / effect layout without a plain colour block) is not converted; ``convert_fixture`` lists it with the
reason in ``Converted.skipped``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

WHITES = {"White", "Warm White", "Cold White"}  # a white channel next to RGB is the W of an RGBW block
FORMATS = {("Red", "Green", "Blue", "White"): "RGBW", ("Red", "Green", "Blue"): "RGB"}
PIXEL_KEY = "$pixelKey"


class ConversionError(ValueError):
    """A mode (or a whole fixture) can't be expressed as a PitchControl channel mode."""


@dataclass
class Converted:
    modes: list[dict] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (OFL mode name, why)
    assumptions: list[str] = field(default_factory=list)  # defaults that OFL didn't give (reported, not hidden)


@dataclass
class Ref:
    """A channel of a mode, resolved against the fixture's availableChannels and templateChannels."""

    name: str  # what the mode lists
    definition: dict
    fine: bool = False  # the 16-bit fine half of another channel
    unused: bool = False  # a switching channel that does nothing with the controlling channel at its default


@dataclass
class Item:
    kind: str  # colour | dimmer | shutter | const
    ref: Ref
    colour: str | None = None


@dataclass
class Block:
    keys: list[str]  # the pixels (or pixel groups) the template channels repeat for
    items: list[Item]

    @property
    def pixels(self) -> int:
        return len(self.keys)


# --------------------------------------------------------------------------- the OFL side


def mode_short_name(mode: dict) -> str:
    return mode.get("shortName") or mode["name"]


def capabilities(definition: dict) -> list[dict]:
    caps = definition.get("capabilities")
    return caps if caps is not None else [definition["capability"]]


def _is_16bit(definition: dict) -> bool:
    return bool(definition.get("fineChannelAliases")) and definition.get("dmxValueResolution") != "8bit"


def ranges8(definition: dict) -> list[tuple[int, int, dict]]:
    """The capabilities as (start, end, capability) in 8-bit DMX values (16-bit channels are cut to their coarse byte)."""
    wide = _is_16bit(definition)
    top = 65535 if wide else 255
    out = []
    for cap in capabilities(definition):
        start, end = cap.get("dmxRange", [0, top])
        if wide:
            start, end = start // 256, end // 256
        out.append((start, end, cap))
    return out


def default_value(definition: dict) -> int:
    """The channel's OFL default as an 8-bit value (0 when OFL gives none)."""
    value = definition.get("defaultValue", 0)
    if isinstance(value, str):  # "50%"
        return round(float(value.rstrip("%")) * 2.55)
    return value // 256 if _is_16bit(definition) else value


class Fixture:
    """One OFL fixture: channel lookup (plain, fine, template, switching) and the matrix."""

    def __init__(self, data: dict):
        self.data = data
        self.channels: dict[str, dict] = data.get("availableChannels", {})
        self.templates: dict[str, dict] = data.get("templateChannels", {})
        self.matrix: dict = data.get("matrix", {})
        self.fine_of: dict[str, dict] = {}
        for pool in (self.channels, self.templates):
            for definition in pool.values():
                for alias in definition.get("fineChannelAliases", []):
                    self.fine_of[alias] = definition
        # switching channel alias -> {controlling channel key: capability list}
        self.switching: dict[str, str] = {}
        for key, definition in self.channels.items():
            for cap in capabilities(definition):
                for alias in cap.get("switchChannels", {}):
                    self.switching[alias] = key

    # ---- lookup

    def _pattern_match(self, key: str, names: dict[str, Any]) -> Any | None:
        for template, value in names.items():
            pattern = re.escape(template).replace(re.escape(PIXEL_KEY), "(.+)")
            if re.fullmatch(pattern, key):
                return value
        return None

    def lookup(self, key: str) -> Ref:
        if key in self.channels:
            return Ref(key, self.channels[key])
        if key in self.templates:
            return Ref(key, self.templates[key])
        if key in self.fine_of:
            return Ref(key, self.fine_of[key], fine=True)
        found = self._pattern_match(key, self.fine_of)  # before the plain templates: "Dimmer Master fine" also fits "Dimmer $pixelKey"
        if found is not None:
            return Ref(key, found, fine=True)
        found = self._pattern_match(key, self.templates)
        if found is not None:
            return Ref(key, found)
        raise ConversionError(f"unknown channel '{key}'")

    def resolve_switching(self, alias: str, mode_keys: list[str]) -> Ref:
        """A switching channel with the controlling channel at its default value."""
        controller = self.switching[alias]
        if controller not in mode_keys:
            raise ConversionError(f"switching channel '{alias}': its controlling channel '{controller}' is not in the mode")
        definition = self.channels[controller]
        value = default_value(definition)
        for start, end, cap in ranges8(definition):
            if start <= value <= end:
                target = cap["switchChannels"].get(alias)
                break
        else:
            raise ConversionError(f"switching channel '{alias}': default {value} of '{controller}' is in no capability")
        if target is None:
            options = [o.strip() for o in alias.split(" / ") if not o.strip().startswith("NoFunction")]
            return Ref(f"{options[0] if options else alias} (unused)", {"capability": {"type": "NoFunction"}}, unused=True)
        return self.lookup(target)

    # ---- matrix

    def pixel_keys(self, repeat_for: Any) -> list[str]:
        if isinstance(repeat_for, list):
            return repeat_for
        if repeat_for == "eachPixelGroup":
            return list(self.matrix.get("pixelGroups", {}))
        if repeat_for.startswith("eachPixel"):
            if "pixelKeys" in self.matrix:
                return [k for plane in self.matrix["pixelKeys"] for row in plane for k in row if k is not None]
            count = 1
            for n in self.matrix.get("pixelCount", [1, 1, 1]):
                count *= n
            return [str(i + 1) for i in range(count)]
        raise ConversionError(f"unknown repeatFor '{repeat_for}'")


# --------------------------------------------------------------------------- classification


def classify(ref: Ref) -> Item:
    if ref.fine or ref.unused:
        return Item("const", ref)
    caps = capabilities(ref.definition)
    types = {c["type"] for c in caps}
    if types == {"ColorIntensity"} and len(caps) == 1:
        return Item("colour", ref, caps[0]["color"])
    if types == {"Intensity"} and len(caps) == 1:
        return Item("dimmer", ref)
    strobes = any(c["type"] == "ShutterStrobe" and c.get("shutterEffect") == "Strobe" for c in caps)
    if strobes and types <= {"ShutterStrobe", "NoFunction", "Effect"}:  # (a function channel: sound control, then strobe)
        return Item("shutter", ref)
    return Item("const", ref)


def _speed(cap: dict) -> float:
    """How fast a strobe capability gets at its end (a frequency in Hz; 'fast' when OFL gives no number)."""
    end = cap.get("speedEnd", cap.get("speed"))
    if isinstance(end, str):
        match = re.fullmatch(r"([\d.]+)\s*Hz", end)
        if match:
            return float(match.group(1))
        if end == "fast":
            return 1000.0
    return -1.0


def derive_shutter(ref: Ref, assumptions: list[str]) -> dict:
    """The shutter channel's open value and the fastest plain strobe value."""
    caps = ranges8(ref.definition)
    openers = [(s, e) for s, e, c in caps if (c["type"] == "ShutterStrobe" and c.get("shutterEffect") == "Open") or c["type"] == "NoFunction"]
    if openers:
        start, end = min(openers)
        opened = 0 if start == 0 else (start + end + 1) // 2  # "LED off" 0..31, "on" 32..63: the middle of "on"
    else:
        opened = 0
        assumptions.append(f"{ref.name}: OFL has no open range, open = 0")
    strobes = [(s, e, c) for s, e, c in caps if c["type"] == "ShutterStrobe" and c.get("shutterEffect") == "Strobe"]
    plain = [t for t in strobes if not t[2].get("randomTiming") and "durationStart" not in t[2] and "duration" not in t[2]]
    pool = plain or strobes
    if not pool:
        raise ConversionError(f"shutter channel '{ref.name}' has no strobe range")
    best = max(range(len(pool)), key=lambda i: (_speed(pool[i][2]), i))
    return {"open": opened, "strobo": pool[best][1]}


def white_preset(ref: Ref) -> int | None:
    """The middle of a colour-preset channel's "White" step, or None."""
    for start, end, cap in ranges8(ref.definition):
        if cap["type"] == "ColorPreset" and cap.get("comment", "").strip().lower() == "white":
            return (start + end + 1) // 2
    return None


# --------------------------------------------------------------------------- modes


def flatten(fx: Fixture, mode: dict) -> list[Item | Block]:
    """The mode's channels in order, with switching channels resolved and matrix inserts as Blocks."""
    keys = [c for c in mode["channels"] if isinstance(c, str)]
    out: list[Item | Block] = []
    for entry in mode["channels"]:
        if entry is None:
            raise ConversionError("a channel that OFL leaves out (null)")
        if isinstance(entry, dict):
            if entry.get("insert") != "matrixChannels":
                raise ConversionError(f"unknown insert '{entry.get('insert')}'")
            pixels = fx.pixel_keys(entry["repeatFor"])
            if entry.get("channelOrder", "perPixel") != "perPixel" and len(pixels) > 1:
                raise ConversionError("channels ordered per channel, not per pixel")
            out.append(Block(pixels, [classify(fx.lookup(k)) for k in entry["templateChannels"]]))
            continue
        ref = fx.resolve_switching(entry, keys) if entry in fx.switching and entry not in fx.channels else fx.lookup(entry)
        out.append(classify(ref))
    return out


def _format_of(colours: list[str]) -> str | None:
    names = tuple("White" if c in WHITES else c for c in colours)
    return FORMATS.get(names)


def convert_mode(fx: Fixture, mode: dict, assumptions: list[str]) -> dict:
    items = flatten(fx, mode)
    flat: list[Item] = []
    colour_block: Block | None = None
    expanded: list[Item | Block] = []  # blocks of shutters (a strobe per pixel group) become one shutter channel each
    for entry in items:
        if isinstance(entry, Block):
            kinds = {i.kind for i in entry.items}
            if kinds == {"shutter"}:  # a strobe per pixel group: one shutter channel each, named by the group
                for key in entry.keys:
                    for item in entry.items:
                        ref = Ref(item.ref.name.replace(PIXEL_KEY, key), item.ref.definition)
                        expanded.append(Item("shutter", ref))
            elif kinds == {"colour"}:
                if colour_block is not None:
                    raise ConversionError("more than one pixel block")
                colour_block = entry
                expanded.append(entry)
            else:
                names = ", ".join(i.ref.name for i in entry.items)
                raise ConversionError(f"a per-pixel block with {names}")
        else:
            expanded.append(entry)

    # colour runs in a flat list: R G B (W) next to each other are the pixel block of a one-pixel mode
    slots: list[dict] = []
    has_colour_block = colour_block is not None
    pixels = 1
    if colour_block is not None:
        if any(isinstance(e, Item) and e.kind == "colour" for e in expanded):
            raise ConversionError("colour channels both inside and outside a pixel block")
        fmt = _format_of([i.colour for i in colour_block.items])
        if fmt is None:
            raise ConversionError("pixel colours " + " ".join(i.colour for i in colour_block.items) + " are not RGB or RGBW")
        pixels = colour_block.pixels
    else:
        run_start = next((n for n, e in enumerate(expanded) if isinstance(e, Item) and e.kind == "colour"), None)
        if run_start is not None:
            for length in (4, 3):
                run = expanded[run_start : run_start + length]
                if len(run) == length and all(isinstance(e, Item) and e.kind == "colour" for e in run) and _format_of([e.colour for e in run]):
                    fmt = _format_of([e.colour for e in run])
                    expanded[run_start : run_start + length] = [Block(['1'], run)]
                    colour_block, has_colour_block = expanded[run_start], True
                    break
            else:
                raise ConversionError("colour channels that don't start with R G B")

    for entry in expanded:
        if isinstance(entry, Block):
            slots.append({"pixels": fmt})
            continue
        ref = entry.ref
        if entry.kind == "colour":  # amber, UV, ... or a second white: no pixel colour, held off
            slots.append({"name": ref.name, "value": default_value(ref.definition)})
        elif entry.kind == "dimmer":
            if has_colour_block:
                slots.append({"name": ref.name, "value": 255})  # held at full: the colours carry the brightness
            elif any(s.get("pixels") == "I" for s in slots):
                raise ConversionError("more than one dimmer without colour channels")
            else:
                slots.append({"name": ref.name, "pixels": "I"})  # follows the brightness
        elif entry.kind == "shutter":
            slots.append({"name": ref.name, "shutter": derive_shutter(ref, assumptions)})
        else:
            value = default_value(ref.definition)
            if not has_colour_block and not ref.fine and not ref.unused:
                value = white_preset(ref) or value
            slots.append({"name": ref.name, "value": value})
    return {"pixels": pixels, "channels": slots}


def short_reason(why: str) -> str:
    """A skipped mode's reason in words for the import report (the converter's own wording stays in ``Converted.skipped``)."""
    if why.startswith("a per-pixel block"):
        return "a dimmer, amber, CCT or strobe per pixel, which PitchControl can't repeat"
    if "leaves out (null)" in why:
        return "an empty gap channel between the pixels"
    if why.startswith("pixel colours"):
        return "amber next to RGB on every pixel"
    return why


def mode_name(mode: dict) -> str:
    short = mode_short_name(mode)
    match = re.fullmatch(r"(d?)(\d+)ch[ -]?(\d*)", short, re.IGNORECASE)
    if match:  # "4ch 1" -> 4CH1, "D3ch" -> D3CH (the names the fixtures' displays and manuals use)
        return f"{match.group(1).upper()}{match.group(2)}CH{match.group(3)}"
    return mode["name"]


def mode_id(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower())
    return "-".join(part for part in slug.split("-") if part) or "mode"


def describe(mode: dict) -> str:
    """One line of the mode's layout, naming every constant and its value."""
    parts = []
    for slot in mode["channels"]:
        if "pixels" in slot and slot["pixels"] != "I":
            parts.append(f"{mode['pixels']} × {slot['pixels']}" if mode["pixels"] > 1 else slot["pixels"])
        elif "pixels" in slot:
            parts.append(f"{slot['name']} (follows the brightness)")
        elif "shutter" in slot:
            parts.append(slot["name"])
        else:
            value = slot["value"]
            if slot["name"].endswith("(unused)"):  # a channel that does nothing in the colour-mixing function
                parts.append(slot["name"])
            else:
                parts.append(f"{slot['name']} (held at full)" if value == 255 else f"{slot['name']} (held at {value})" if value else f"{slot['name']} (off)")
    text = ", ".join(parts)
    text = text[:1].upper() + text[1:] + "."
    kinds = {slot.get("pixels") for slot in mode["channels"]}
    if not kinds & {"RGB", "RGBW"}:
        text += " No colour mixing in this mode: only the brightness follows PitchControl." if "I" in kinds else (
            " PitchControl can't change the light in this mode (no colour or dimmer channel); it is listed for addressing."
        )
    return text


def convert_fixture(data: dict, skip: dict[str, str] | None = None) -> Converted:
    """Every OFL mode of ``data`` as a PitchControl channel mode (``ofl_mode`` names the OFL mode it came from); modes
    it can't express go to ``skipped``, with the reason. ``skip`` names OFL modes to leave out on purpose (OFL mode
    name -> why)."""
    fx = Fixture(data)
    result = Converted()
    for mode in data["modes"]:
        if skip and mode["name"] in skip:
            result.skipped.append((mode["name"], skip[mode["name"]]))
            continue
        try:
            converted = convert_mode(fx, mode, result.assumptions)
        except ConversionError as problem:
            result.skipped.append((mode["name"], str(problem)))
            continue
        name = mode_name(mode)
        converted = {"id": mode_id(name), "name": name, "description": "", "ofl_mode": mode["name"], **converted}
        converted["description"] = describe(converted)
        result.modes.append(converted)
    return result
