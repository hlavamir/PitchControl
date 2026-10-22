"""A QLC+ fixture definition (``.qxf``) -> an Open Fixture Library fixture (item 54).

QLC+ is the other lighting program many PitchControl users have installed, with thousands of fixture definitions on
disk. The file is XML (namespace ``http://www.qlcplus.org/FixtureDefinition``). It is read here into **OFL's fixture
model**, the way OFL's own QLC+ import plugin does (``plugins/qlcplus_4.12.2/import.js`` and ``presets.js`` in the
Open Fixture Library, MIT), and then goes through ``importer.import_fixture`` and ``convert.py`` like every other
import: there is one mapping to PitchControl, and the type keeps the OFL data (and the QLC+ file) the same way.

What is mapped (as OFL's plugin does it):

* name, manufacturer, categories (a ``LED Bar …`` type is ``Pixel Bar``), authors, physical data per fixture and mode;
* every channel with its capabilities: channel presets (``IntensityRed``, ``PositionPan``, …) and capability presets
  (``StrobeSlowToFast``, ``ColorMacro``, ``RotationClockwise``, …) become OFL capabilities, the other channels are
  guessed from their group (Intensity, Colour, Gobo, Speed, Pan, Tilt, Shutter, Prism, Effect, Maintenance);
* wheels (guessed from the channel names and presets, as OFL does);
* **fine channels** (``Group Byte="1"``, or a preset ending in ``Fine``) become ``fineChannelAliases`` of their coarse
  channel;
* **switching channels** (capabilities with ``<Alias>`` elements) become OFL's ``switchChannels`` and the
  ``A / B`` channel keys in the modes;
* the modes (name, short name, channel list, physical data).

What OFL's plugin does not do and PitchControl needs: ``<Head>`` elements. OFL only warns ("please add the head to
the matrix"); here a mode whose heads all have the same channels becomes an OFL **matrix** (``matrix`` from the
physical layout, or one row) with ``templateChannels`` (the head's channels, ``$pixelKey`` where the head number is in
the name) and a ``matrixChannels`` insert in the mode, so ``convert.py`` makes pixels of them. Heads whose channels
differ, or that are not one run of the mode's channels, are not made pixels: that mode is left out of the import (the report
says why; the original stays in ofl_modes), because plain channels would read as one pixel.

What the OFL model can't hold is kept: ``qlcplus`` (a key of the type, next to OFL's) has the creator and the
original ``Type``, ``unmapped``: every element and attribute of the file this module didn't read, and ``xml``: the
file itself, so nothing of QLC+'s data is lost and the conversion can be repeated with a better mapping later.

Differences from OFL's plugin (on purpose): gobo images are not looked up in OFL's resource library (a gobo slot keeps
its QLC+ name), a channel without a ``Group`` is not an error, a wheel without slots is not made, and the pan / tilt
maximum is 0 (angles unknown) instead of -Infinity when the file has no ``Focus`` element.
"""

from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .importer import ImportProblem, Imported, import_fixture

NAMESPACE = "http://www.qlcplus.org/FixtureDefinition"
OFL_SCHEMA = "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/schemas/fixture.json"
MAX_BYTES = 8_000_000  # the biggest QLC+ fixture definitions are a few hundred kB
PIXEL_KEY = "$pixelKey"


@dataclass
class Qlc:
    """The result of reading a ``.qxf``: the OFL fixture, who made it, and what to tell the user."""

    ofl: dict[str, Any]
    manufacturer: str
    warnings: list[str] = field(default_factory=list)  # things to check (OFL's own "please check" lines)
    dropped: list[str] = field(default_factory=list)  # what the OFL model can't hold (kept under ``qlcplus.unmapped``)
    kept: dict[str, Any] = field(default_factory=dict)  # the ``qlcplus`` key of the type
    creator: str = ""  # "Q Light Controller Plus 4.12.2"
    skip: dict[str, str] = field(default_factory=dict)  # OFL mode name -> why its heads can't be pixels: left out of the import


# --------------------------------------------------------------------------- small JS-like helpers


def parse_int(value: str | None) -> int:
    """``Number.parseInt(value, 10) || 0``."""
    match = re.match(r"\s*([+-]?\d+)", value or "")
    return int(match[1]) if match else 0


def parse_float(value: str | None) -> float | None:
    """``Number.parseFloat(value)``; None for NaN."""
    match = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", value or "")
    return float(match[1]) if match else None


def number_text(number: float) -> str:
    return str(int(number)) if number == int(number) else str(number)


def slugify(text: str) -> str:
    return re.sub(r"\s+", "-", re.sub(r"[^\da-z-]+", " ", text.lower()).strip())


# --------------------------------------------------------------------------- reading the XML


def parse_xml(source: str | bytes) -> ET.Element:
    size = len(source)
    if size > MAX_BYTES:
        raise ImportProblem(f"this file is {size // 1_000_000} MB: a QLC+ fixture definition is a few kB")
    if (b"<!entity" if isinstance(source, bytes) else "<!entity") in source.lower():
        raise ImportProblem("this file declares XML entities, which a QLC+ fixture definition never does")
    if isinstance(source, str):
        source = source.lstrip("\ufeff")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        if (source.lstrip() if isinstance(source, str) else source.lstrip()[:1].decode("latin-1")).startswith("{"):
            raise ImportProblem("this looks like an Open Fixture Library fixture (JSON), not a QLC+ definition: use File → Import Fixture → Open Fixture Library…") from exc
        raise ImportProblem(f"this is not a readable XML file ({exc}): pick a QLC+ fixture definition (.qxf)") from exc
    for el in root.iter():  # drop the namespace: {http://www.qlcplus.org/FixtureDefinition}Channel -> Channel
        if isinstance(el.tag, str) and el.tag.startswith("{"):
            el.tag = el.tag.split("}", 1)[1]
    if root.tag != "FixtureDefinition":
        raise ImportProblem("this is not a QLC+ fixture definition (.qxf): the XML has no FixtureDefinition")
    return root


class Reader:
    """Reads elements and remembers what was read, so what wasn't can be kept and reported."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.seen: set[int] = set()
        self.read_attrs: set[tuple[int, str]] = set()

    def attr(self, el: ET.Element, name: str, default: str | None = None) -> str | None:
        self.seen.add(id(el))
        self.read_attrs.add((id(el), name))
        return el.get(name, default)

    def text(self, el: ET.Element | None) -> str:
        if el is None:
            return ""
        self.seen.add(id(el))
        self.read_attrs.add((id(el), "#text"))
        return el.text or ""

    def child(self, el: ET.Element, tag: str) -> ET.Element | None:
        found = el.find(tag)
        self.seen.add(id(el))
        if found is not None:
            self.seen.add(id(found))
        return found

    def children(self, el: ET.Element, tag: str) -> list[ET.Element]:
        self.seen.add(id(el))
        found = el.findall(tag)
        self.seen.update(id(c) for c in found)
        return found

    def child_text(self, el: ET.Element, tag: str) -> str | None:
        found = self.child(el, tag)
        return None if found is None else self.text(found).strip()

    # ---- what was not read

    def unmapped(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        self._walk(self.root, "FixtureDefinition", out)
        return out

    def _walk(self, el: ET.Element, path: str, out: list[dict[str, Any]]) -> None:
        if id(el) not in self.seen:  # an element nothing looked at: kept whole (with its children, as text)
            entry: dict[str, Any] = {"path": path, "element": True}
            if el.attrib:
                entry["attributes"] = dict(el.attrib)
            if (el.text or "").strip():
                entry["text"] = el.text.strip()
            if len(el):
                entry["children"] = [ET.tostring(c, encoding="unicode").strip() for c in el]
            out.append(entry)
            return
        left = {k: v for k, v in el.attrib.items() if (id(el), k) not in self.read_attrs}
        if left:
            out.append({"path": path, "attributes": left})
        if (el.text or "").strip() and (id(el), "#text") not in self.read_attrs and not len(el):
            out.append({"path": path, "text": el.text.strip()})
        counts: dict[str, int] = {}
        for child in el:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            name = child.get("Name")
            label = f'{child.tag}[@Name="{name}"]' if name else f"{child.tag}[{counts[child.tag]}]" if len(el.findall(child.tag)) > 1 else child.tag
            self._walk(child, f"{path}/{label}", out)


def summarize(unmapped: list[dict[str, Any]]) -> list[str]:
    """The unmapped entries as lines for the report: grouped by element and attribute, with how often and where first."""
    groups: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for entry in unmapped:
        tag = re.sub(r"\[[^\]]*\]", "", entry["path"]).rsplit("/", 1)[-1]
        if entry.get("element"):
            groups.setdefault(f"element {tag}", []).append((entry, ""))
        elif "attributes" in entry:
            for name, value in entry["attributes"].items():
                groups.setdefault(f"{tag} attribute “{name}”", []).append((entry, f' ({name}="{value}")'))
        else:
            groups.setdefault(f"text of {tag}", []).append((entry, ""))
    lines = []
    for what, found in groups.items():
        entry, example = found[0]
        where = entry["path"].split("/", 1)[-1] if "/" in entry["path"] else entry["path"]
        lines.append(f"{what}: {len(found)} time{'s' if len(found) > 1 else ''}, first in {where}{example}")
    return lines


# --------------------------------------------------------------------------- capability guessing (presets.js)


SPEED_RE = re.compile(
    r"(?:^|,\s*|\s+)\(?((?:(?:counter\s?-?\s?)?clockwise|c?cw).*?(?:,\s*|\s+))?\(?(slow|fast|\d+|\d+\s*hz)\s*(?:-|to|–|…|\.{2,}|->|<->|→)\s*(fast|slow|\d+\s*hz)\)?$",
    re.I,
)
STOP_RE = re.compile(r"\s*\b(?:stop(?:ped)?|no rotation|no rotate)\b\s*", re.I)


def direction_suffix(direction: str | None) -> str:
    if not direction:
        return ""
    return " CCW" if re.search(r"counter|ccw", direction, re.I) else " CW"


def speed_guessed_comment(name: str, cap: dict[str, Any]) -> str:
    """Guess speedStart / speedEnd from the capability name and set them on ``cap`` (it may become a Rotation);
    returns the rest of the name."""
    match = SPEED_RE.search(name)
    if match:
        suffix = direction_suffix(match[1])
        if suffix:
            cap["type"] = "Rotation"
        start, end = match[2].lower(), match[3].lower()
        start_n, end_n = parse_float(start), parse_float(end)
        if start_n is not None and end_n is not None:
            start, end = f"{number_text(start_n)}Hz", f"{number_text(end_n)}Hz"
        cap["speedStart"] = start + suffix
        cap["speedEnd"] = end + suffix
        return name[: match.start()] + name[match.end() :]
    if STOP_RE.search(name):
        cap["speed"] = "stop"
        return STOP_RE.sub("", name)
    return name


def color_intensity(color: str) -> dict[str, Any]:
    return {"type": "ColorIntensity", "color": color}


def pan_tilt(kind: str, maximum: int = 0) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": kind, "angleStart": "0deg", "angleEnd": f"{maximum}deg"}
    if maximum == 0:
        cap["angleStart"], cap["angleEnd"] = "0%", "100%"
        cap["helpWanted"] = "Can you provide exact angles?"
    return cap


def shutter_strobe(effect: str, start: str | None = None, end: str | None = None, random: bool = False) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": "ShutterStrobe", "shutterEffect": effect}
    if end:
        cap["speedStart"], cap["speedEnd"] = start, end
    elif start:
        cap["speed"] = start
    if random:
        cap["randomTiming"] = True
    return cap


def wheel_rotation() -> dict[str, Any]:
    return {"type": "WheelRotation", "wheel": "", "speedStart": "slow", "speedEnd": "fast"}


def focus(start: str, end: str) -> dict[str, Any]:
    return {"type": "Focus", "distanceStart": start, "distanceEnd": end}


@dataclass
class CapData:
    """What the capability presets and parsers need to know (``capabilityData`` in OFL's import.js)."""

    channel_el: ET.Element
    channel_name: str
    channel_type: str | None
    in_wheels: bool
    cap_el: ET.Element
    cap_name: str
    index: int
    res1: str | None
    res2: str | None
    pan_max: int
    tilt_max: int


def rotation_cap_type(d: CapData) -> str:
    if d.channel_type in ("Pan", "Tilt"):
        return f"{d.channel_type}Continuous"
    if d.channel_type in ("Colour", "Gobo") or re.search("gobo", d.channel_name, re.I):
        return "WheelRotation" if re.search("wheel", d.channel_name, re.I) else "WheelSlotRotation"
    return "PrismRotation" if d.channel_type == "Prism" else "Rotation"


def rotation_speed(d: CapData, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": rotation_cap_type(d)}
    if cap["type"].startswith("Wheel") and not d.in_wheels:
        cap["wheel"] = ""
    if end:
        cap["speedStart"], cap["speedEnd"] = start, end
    elif start:
        cap["speed"] = start
    return cap


def speed_cap_type(d: CapData) -> str:
    if d.channel_type == "Shutter" or re.search("strobe", d.channel_name, re.I):
        return "StrobeSpeed"
    if re.search(r"pan\W*tilt", d.channel_name, re.I):
        return "PanTiltSpeed"
    return "EffectSpeed" if d.channel_type == "Effect" or re.search("program|effect", d.channel_name, re.I) else "Speed"


def beam_angle(d: CapData, ascending: bool) -> dict[str, Any]:
    if d.channel_type == "Shutter" or re.search("iris", d.channel_name, re.I):
        start, end = ("closed", "open") if ascending else ("open", "closed")
        return {"type": "Iris", "openPercentStart": start, "openPercentEnd": end}
    start, end = ("small", "big") if ascending else ("big", "small")
    return {"type": "Zoom" if re.search("zoom", d.channel_name, re.I) else "BeamAngle", "angleStart": start, "angleEnd": end}


def maintenance(d: CapData) -> dict[str, Any]:
    return {"type": "Maintenance", "comment": d.cap_name}


def white_of(name: str) -> str:
    if re.search(r"\bwarm\b", name, re.I):
        return "Warm White"
    return "Cold White" if re.search(r"\bcold\b", name, re.I) else "White"


# channel presets: name -> (channel name, pan max, tilt max) -> OFL capability
def _channel_presets() -> dict[str, Any]:
    p: dict[str, Any] = {}
    for preset in ("IntensityMasterDimmer", "IntensityDimmer"):
        p[preset] = lambda name, pan, tilt: {"type": "Intensity"}
    for colour in ("Red", "Green", "Blue", "Cyan", "Magenta", "Yellow", "Amber", "UV", "Indigo", "Lime"):
        p[f"Intensity{colour}"] = lambda name, pan, tilt, c=colour: color_intensity(c)
    p["IntensityWhite"] = lambda name, pan, tilt: color_intensity(white_of(name))
    for preset in ("IntensityHue", "IntensitySaturation", "IntensityLightness", "IntensityValue", "ColorRGBMixer"):
        p[preset] = lambda name, pan, tilt: {"type": "Generic"}
    p["PositionPan"] = lambda name, pan, tilt: pan_tilt("Pan", pan)
    p["PositionTilt"] = lambda name, pan, tilt: pan_tilt("Tilt", tilt)
    p["PositionXAxis"] = lambda *_: {"type": "BeamPosition", "horizontalAngleStart": "left", "horizontalAngleEnd": "right", "helpWanted": "Is this the correct direction? Can you provide exact angles?"}
    p["PositionYAxis"] = lambda *_: {"type": "BeamPosition", "verticalAngleStart": "top", "verticalAngleEnd": "bottom", "helpWanted": "Is this the correct direction? Can you provide exact angles?"}
    for preset, kind, a, b in (
        ("SpeedPanSlowFast", "PanContinuous", "slow", "fast"),
        ("SpeedPanFastSlow", "PanContinuous", "fast", "slow"),
        ("SpeedTiltSlowFast", "TiltContinuous", "slow", "fast"),
        ("SpeedTiltFastSlow", "TiltContinuous", "fast", "slow"),
        ("SpeedPanTiltSlowFast", "PanTiltSpeed", "slow", "fast"),
        ("SpeedPanTiltFastSlow", "PanTiltSpeed", "fast", "slow"),
    ):
        p[preset] = lambda *_, k=kind, s=a, e=b: {"type": k, "speedStart": s, "speedEnd": e}
    p["ColorMacro"] = lambda *_: {"type": "ColorPreset", "helpWanted": "Which color can be selected at which DMX values?"}
    p["ColorWheel"] = lambda *_: wheel_rotation()
    p["GoboWheel"] = lambda *_: wheel_rotation()
    for preset, end in (("ColorCTOMixer", "warm"), ("ColorCTBMixer", "cold")):
        p[preset] = lambda *_, e=end: {"type": "ColorTemperature", "colorTemperatureStart": "default", "colorTemperatureEnd": e, "helpWanted": "Can you provide exact color temperature values in Kelvin?"}
    p["ColorCTCMixer"] = lambda *_: {"type": "ColorTemperature", "colorTemperatureStart": "warm", "colorTemperatureEnd": "cold", "helpWanted": "Is this the correct direction? Can you provide exact color temperature values in Kelvin?"}
    p["GoboIndex"] = lambda *_: {"type": "WheelSlotRotation", "angleStart": "0deg", "angleEnd": "360deg", "helpWanted": "Are these the correct angles?"}
    for preset, a, b in (("ShutterStrobeSlowFast", "slow", "fast"), ("ShutterStrobeFastSlow", "fast", "slow")):
        p[preset] = lambda *_, s=a, e=b: {"type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": s, "speedEnd": e, "helpWanted": "At which DMX values is strobe disabled? When is the lamp constantly on/off?"}
    p["ShutterIrisMinToMax"] = lambda *_: {"type": "Iris", "openPercentStart": "closed", "openPercentEnd": "open"}
    p["ShutterIrisMaxToMin"] = lambda *_: {"type": "Iris", "openPercentStart": "open", "openPercentEnd": "closed"}
    p["BeamFocusNearFar"] = lambda *_: focus("near", "far")
    p["BeamFocusFarNear"] = lambda *_: focus("far", "near")
    p["BeamZoomSmallBig"] = lambda *_: {"type": "Zoom", "angleStart": "narrow", "angleEnd": "wide"}
    p["BeamZoomBigSmall"] = lambda *_: {"type": "Zoom", "angleStart": "wide", "angleEnd": "narrow"}
    p["PrismRotationSlowFast"] = lambda *_: {"type": "PrismRotation", "speedStart": "slow CW", "speedEnd": "fast CW", "helpWanted": "Does the prism rotate clockwise or counter-clockwise?"}
    p["PrismRotationFastSlow"] = lambda *_: {"type": "PrismRotation", "speedStart": "fast CW", "speedEnd": "slow CW", "helpWanted": "Does the prism rotate clockwise or counter-clockwise?"}
    p["NoFunction"] = lambda *_: {"type": "NoFunction"}
    return p


CHANNEL_PRESETS = _channel_presets()


def channel_preset_capability(preset: str, name: str, pan: int, tilt: int) -> dict[str, Any]:
    if preset in CHANNEL_PRESETS:
        return CHANNEL_PRESETS[preset](name, pan, tilt)
    return {"type": "Generic", "helpWanted": f"Unknown QLC+ channel preset {preset}."}


MAINTENANCE_PRESETS = (
    "ResetPanTilt ResetPan ResetTilt ResetEffects ResetGobo ResetColor ResetCMY ResetCTO ResetPrism ResetBlades ResetIris ResetFrost "
    "ResetZoom ResetMotors ResetAll LampOn LampOff SilentModeOn SilentModeOff SilentModeAutomatic"
).split()


def color_double_macro(d: CapData) -> dict[str, Any]:
    if re.search(r"wheel\b", d.channel_name, re.I):
        return {"type": "WheelSlot", "slotNumber": d.index + 1}
    colors = [d.res1] if d.res1 else []
    if d.res2:
        colors.append(d.res2)
    return {"type": "ColorPreset", "comment": "", "colors": colors}


def gobo_shake(d: CapData) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": "WheelShake", "slotNumber": d.index + 1}
    comment = speed_guessed_comment(d.cap_name, cap)
    if "speed" in cap:
        cap["shakeSpeed"] = cap.pop("speed")
    elif "speedStart" in cap:
        cap["shakeSpeedStart"], cap["shakeSpeedEnd"] = cap.pop("speedStart"), cap.pop("speedEnd")
    cap["comment"] = comment
    return cap


def generic_picture(d: CapData) -> dict[str, Any]:
    if d.res1 == "Others/rainbow.png":
        if re.search("wheel", d.channel_name, re.I):
            cap: dict[str, Any] = {"type": "WheelRotation"}
            cap["comment"] = speed_guessed_comment(d.cap_name, cap)
            if "speed" not in cap and "speedStart" not in cap:
                cap["speedStart"], cap["speedEnd"] = "slow CW", "fast CW"
                cap["helpWanted"] = "Are the automatically added speed values correct?"
            return cap
        return {"type": "Effect", "effectName": d.cap_name}
    return {"type": "Generic", "comment": d.res1}


def _capability_presets() -> dict[str, Any]:
    p: dict[str, Any] = {}
    p["ShutterOpen"] = lambda d: {"type": "ShutterStrobe", "shutterEffect": "Open"}
    p["ShutterClose"] = lambda d: {"type": "ShutterStrobe", "shutterEffect": "Closed"}
    for effect in ("Strobe", "Pulse", "RampUp", "RampDown"):
        p[f"{effect}Frequency"] = lambda d, e=effect: shutter_strobe(e, f"{d.res1}Hz")
        p[f"{effect}FreqRange"] = lambda d, e=effect: shutter_strobe(e, f"{d.res1}Hz", f"{d.res2}Hz")
        p[f"{effect}SlowToFast"] = lambda d, e=effect: shutter_strobe(e, "slow", "fast")
        p[f"{effect}FastToSlow"] = lambda d, e=effect: shutter_strobe(e, "fast", "slow")
    p["StrobeRandomSlowToFast"] = lambda d: shutter_strobe("Strobe", "slow", "fast", True)
    p["StrobeRandomFastToSlow"] = lambda d: shutter_strobe("Strobe", "fast", "slow", True)
    p["StrobeRandom"] = lambda d: shutter_strobe("Strobe", None, None, True)
    p["ColorDoubleMacro"] = color_double_macro
    p["ColorMacro"] = color_double_macro
    p["ColorWheelIndex"] = lambda d: {"type": "WheelRotation", "angleStart": "0deg", "angleEnd": "360deg", "helpWanted": "Are these the correct angles?"}
    p["GoboShakeMacro"] = gobo_shake
    p["GoboMacro"] = lambda d: {"type": "WheelSlot", "slotNumber": d.index + 1}
    p["PrismEffectOn"] = lambda d: p["GoboMacro"](d) if re.search("wheel", d.channel_name, re.I) else {"type": "Prism", "comment": f"{d.res1}-facet" if d.res1 else ""}
    p["PrismEffectOff"] = lambda d: {"type": "NoFunction"}
    p["RotationClockwiseSlowToFast"] = lambda d: rotation_speed(d, "slow CW", "fast CW")
    p["RotationClockwiseFastToSlow"] = lambda d: rotation_speed(d, "fast CW", "slow CW")
    p["RotationClockwise"] = lambda d: rotation_speed(d, "fast CW")
    p["RotationStop"] = lambda d: rotation_speed(d, "stop")
    p["RotationCounterClockwiseSlowToFast"] = lambda d: rotation_speed(d, "slow CCW", "fast CCW")
    p["RotationCounterClockwiseFastToSlow"] = lambda d: rotation_speed(d, "fast CCW", "slow CCW")
    p["RotationCounterClockwise"] = lambda d: rotation_speed(d, "fast CCW")
    p["RotationIndexed"] = lambda d: {"type": rotation_cap_type(d), "angleStart": "0deg", "angleEnd": "360deg", "helpWanted": "Are these the correct angles?"}
    for preset in MAINTENANCE_PRESETS:
        p[preset] = maintenance
    p["GenericPicture"] = generic_picture
    p["SlowToFast"] = lambda d: {"type": speed_cap_type(d), "speedStart": "slow", "speedEnd": "fast"}
    p["FastToSlow"] = lambda d: {"type": speed_cap_type(d), "speedStart": "fast", "speedEnd": "slow"}
    p["NearToFar"] = lambda d: focus("near", "far")
    p["FarToNear"] = lambda d: focus("far", "near")
    p["SmallToBig"] = lambda d: beam_angle(d, True)
    p["BigToSmall"] = lambda d: beam_angle(d, False)
    return p


CAPABILITY_PRESETS = _capability_presets()


def capability_preset_capability(preset: str, d: CapData) -> dict[str, Any]:
    if preset in CAPABILITY_PRESETS:
        cap = CAPABILITY_PRESETS[preset](d)
        comment = cap.get("comment")
        cap["comment"] = d.cap_name if not comment or comment in d.cap_name else f"{comment} {d.cap_name}"
        return cap
    return {"type": "Generic", "comment": d.cap_name, "helpWanted": f'Unknown QLC+ capability preset {preset}, Res1="{d.res1}", Res2="{d.res2}".'}


# parsers by channel group, for capabilities without a preset
def _parse_nothing(d: CapData) -> dict[str, Any]:
    return {"type": "NoFunction"}


def _parse_intensity(d: CapData, colour: str | None) -> dict[str, Any]:
    cap: dict[str, Any] = {}
    if colour and colour != "Generic":
        cap["type"], cap["color"] = "ColorIntensity", colour
    else:
        cap["type"] = "Intensity"
    if not re.fullmatch(r"intensity|dimmer", d.cap_name, re.I):
        cap["comment"] = d.cap_name
    return cap


def _parse_colour(d: CapData) -> dict[str, Any]:
    cap: dict[str, Any] = {}
    if re.search(r"wheel\b", d.channel_name, re.I):
        cap["type"], cap["slotNumber"] = "WheelSlot", d.index + 1
        cap["comment"] = speed_guessed_comment(d.cap_name, cap)
        if "speed" in cap or "speedStart" in cap:
            cap["type"] = "WheelRotation"
            del cap["slotNumber"]
        return cap
    cap["type"], cap["comment"] = "ColorPreset", d.cap_name
    if "Color" in d.cap_el.attrib:
        cap["colors"] = [d.cap_el.get("Color")]
        if "Color2" in d.cap_el.attrib:
            cap["colors"].append(d.cap_el.get("Color2"))
    return cap


def _parse_gobo(d: CapData) -> dict[str, Any]:
    if re.search(r"shake\b|shaking\b", d.cap_name, re.I):
        return CAPABILITY_PRESETS["GoboShakeMacro"](d)
    cap: dict[str, Any] = {"type": "WheelSlot", "slotNumber": d.index + 1}
    cap["comment"] = speed_guessed_comment(d.cap_name, cap)
    if "speed" in cap or "speedStart" in cap:
        cap["type"] = "WheelRotation" if d.in_wheels else "WheelSlotRotation"
        del cap["slotNumber"]
    return cap


def _parse_effect(d: CapData) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": "Effect", "effectName": ""}
    cap["effectName"] = speed_guessed_comment(d.cap_name, cap)
    if cap["effectName"] == "":
        del cap["effectName"]
        if cap["type"] == "Effect":
            cap["type"] = "Speed"
    elif cap["type"] == "Rotation":
        cap["comment"] = cap.pop("effectName")
    elif re.search(r"\bsound\b", cap["effectName"], re.I):
        cap["soundControlled"] = True
    return cap


def _parse_continuous(kind: str):
    def parse(d: CapData) -> dict[str, Any]:
        if re.search("continuous", d.channel_name, re.I):
            cap: dict[str, Any] = {"type": f"{kind}Continuous"}
            cap["comment"] = speed_guessed_comment(d.cap_name, cap)
            if "speed" not in cap and "speedStart" not in cap:
                cap["speedStart"], cap["speedEnd"] = "slow CW", "fast CW"
                cap["helpWanted"] = "Are the automatically added speed values correct?"
            return cap
        return {**pan_tilt(kind, d.pan_max if kind == "Pan" else d.tilt_max), "comment": d.cap_name}

    return parse


def _parse_shutter(d: CapData) -> dict[str, Any]:
    cap: dict[str, Any] = {"type": "ShutterStrobe"}
    effects = {
        "Closed": r"^(?:blackout|(?:shutter |strobe )?closed?)$",
        "Open": r"^(?:(?:shutter |strobe )?open|full?)$",
        "Pulse": r"puls",
        "RampUp": r"ramp\s*up",
        "RampDown": r"ramp\s*down",
    }
    cap["shutterEffect"] = next((e for e, rx in effects.items() if re.search(rx, d.cap_name, re.I)), "Strobe")
    if cap["shutterEffect"] in ("Open", "Closed"):
        return cap
    if re.search("random", d.cap_name, re.I):
        cap["randomTiming"] = True
    cap["comment"] = speed_guessed_comment(d.cap_name, cap)
    if "speed" not in cap and "speedStart" not in cap:
        cap["speedStart"], cap["speedEnd"] = "slow", "fast"
        cap["helpWanted"] = "Are the automatically added speed values correct?"
    return cap


def _parse_speed(d: CapData) -> dict[str, Any]:
    cap: dict[str, Any] = {}
    if re.search(r"pan/?tilt", d.channel_name, re.I):
        cap["type"] = "PanTiltSpeed"
    elif re.search("strobe", d.channel_name, re.I) or re.search("strobe", d.cap_name, re.I):
        if re.search("speed|rate", d.channel_name, re.I):
            cap["type"] = "StrobeSpeed"
        else:
            cap["type"], cap["shutterEffect"] = "ShutterStrobe", "Strobe"
    else:
        cap["type"] = "Speed"
    cap["comment"] = speed_guessed_comment(d.cap_name, cap)
    if "speed" not in cap and "speedStart" not in cap:
        cap["speedStart"], cap["speedEnd"] = "slow", "fast"
        cap["helpWanted"] = "Are the automatically added speed values correct?"
    return cap


PARSERS = {
    "Nothing": _parse_nothing,
    "Colour": _parse_colour,
    "Gobo": _parse_gobo,
    "Effect": _parse_effect,
    "Maintenance": maintenance,
    "Pan": _parse_continuous("Pan"),
    "Tilt": _parse_continuous("Tilt"),
    "Prism": lambda d: {"type": "Prism", "comment": d.cap_name},
    "Shutter": _parse_shutter,
    "Speed": _parse_speed,
}


# --------------------------------------------------------------------------- wheels (import.js)


def _is_rotation_name(text: str) -> bool:
    return bool(re.search(r"\bc?cw\b|rainbow|stop|(?:counter|anti)?[ -]?clockwise|rotat|spin", text, re.I))


def wheel_slot(cap_el: ET.Element, text: str, preset: str, group: str | None) -> dict[str, Any]:
    res = cap_el.get("Res1") or cap_el.get("Res")
    if text == "Open" or res == "Others/open.svg":
        return {"type": "Open"}
    if (preset == "GoboMacro") if preset else group == "Gobo":
        slot: dict[str, Any] = {"type": "Gobo"}
        if res:
            slot["resource"] = f"gobos/aliases/qlcplus/{res}"
        slot["name"] = text
        return slot
    if (preset in ("ColorMacro", "ColorDoubleMacro")) if preset else group == "Colour":
        slot = {"type": "Color", "name": text}
        colors = [cap_el.get(a) for a in ("Color", "Color2", "Res1", "Res2") if a in cap_el.attrib]
        if colors:
            slot["colors"] = colors
        return slot
    if (preset == "PrismEffectOn") if preset else group == "Prism":
        slot = {"type": "Prism", "name": text}
        if "Res1" in cap_el.attrib:
            slot["facets"] = parse_int(cap_el.get("Res1"))
        return slot
    return {"type": "Unknown", "name": text}


# --------------------------------------------------------------------------- the converter


class _Converter:
    def __init__(self, root: ET.Element, today: str):
        self.rd = Reader(root)
        self.root = root
        self.today = today
        self.warnings: list[str] = []
        self.skip: dict[str, str] = {}
        self.channels: dict[str, ET.Element] = {}
        self.modes: list[ET.Element] = []
        self.fixture: dict[str, Any] = {}

    # ---- helpers

    def group_of(self, qch: ET.Element) -> tuple[str | None, str | None]:
        group = self.rd.child(qch, "Group")
        if group is None:
            return None, None
        return self.rd.text(group).strip(), self.rd.attr(group, "Byte")

    def physicals(self) -> list[ET.Element]:
        out = []
        for el in [*self.modes, self.root]:
            p = self.rd.child(el, "Physical")
            if p is not None:
                out.append(p)
        return out

    # ---- the fixture

    def convert(self) -> Qlc:
        rd, root = self.rd, self.root
        model = rd.child_text(root, "Model")
        maker = rd.child_text(root, "Manufacturer")
        qtype = rd.child_text(root, "Type")
        if not model:
            raise ImportProblem("this QLC+ fixture definition has no Model")
        self.modes = rd.children(root, "Mode")
        if not self.modes:
            raise ImportProblem("this QLC+ fixture definition has no modes")
        qchannels = rd.children(root, "Channel")
        for qch in qchannels:
            name = rd.attr(qch, "Name") or ""
            if name in self.channels:
                self.warnings.append(f"the channel “{name}” is defined twice: the later definition is used")
            self.channels[name] = qch

        creator = rd.child(root, "Creator")
        creator_info = {k: (rd.child_text(creator, k) or "") for k in ("Name", "Version", "Author")} if creator is not None else {}

        fixture: dict[str, Any] = {"$schema": OFL_SCHEMA, "name": model}
        fixture["categories"] = [(qtype or "Other") if not (qtype or "").startswith("LED Bar") else "Pixel Bar"]
        authors = [a for a in re.split(r",\s*", creator_info.get("Author", "")) if a]
        fixture["meta"] = {**({"authors": authors} if authors else {}), "createDate": self.today, "lastModifyDate": self.today}
        physical = self.fixture_physical(qtype)
        if physical:
            fixture["physical"] = physical

        wheels = self.wheels(qchannels)
        available: dict[str, Any] = {}
        pan_max, tilt_max = self.pan_tilt_max()
        for qch in qchannels:
            available[rd.attr(qch, "Name") or ""] = self.channel(qch, wheels, pan_max, tilt_max)
        fine_of = self.merge_fine(qchannels, available)

        modes = [self.mode(m, physical or {}) for m in self.modes]
        self.switching(qchannels, available, modes, [rd.attr(m, "Name") for m in self.modes])
        self.clean_up(available)

        templates: dict[str, Any] = {}
        matrix = self.heads(modes, available, templates, fine_of)

        if matrix:
            fixture["matrix"] = matrix
        if wheels:
            fixture["wheels"] = wheels
        fixture["availableChannels"] = available
        if templates:
            fixture["templateChannels"] = templates
        fixture["modes"] = modes
        self.warn_extra_colours(modes, available)

        unmapped = rd.unmapped()
        creator_name = " ".join(x for x in (creator_info.get("Name"), creator_info.get("Version")) if x)
        kept: dict[str, Any] = {"creator": creator_info, "type": qtype, "unmapped": unmapped}
        return Qlc(fixture, maker or "", self.warnings, summarize(unmapped), kept, creator_name, self.skip)

    # ---- physical

    def pan_tilt_max(self) -> tuple[int, int]:
        best = {"PanMax": 0, "TiltMax": 0}
        for physical in self.physicals():
            focus_el = self.rd.child(physical, "Focus")
            if focus_el is None:
                continue
            for key in best:
                best[key] = max(best[key], parse_int(self.rd.attr(focus_el, key)))
        return best["PanMax"], best["TiltMax"]

    def fixture_physical(self, qtype: str | None) -> dict[str, Any] | None:
        rd = self.rd
        every = all(rd.child(m, "Physical") is not None for m in self.modes)
        first = next((m for m in self.modes if rd.child(m, "Physical") is not None), None)
        global_physical = rd.child(self.root, "Physical")
        if global_physical is None and (first is None or every):
            return None
        source = global_physical if global_physical is not None else rd.child(first, "Physical")
        physical = self.physical(source, {})
        if qtype == "LED Bar (Pixels)":
            physical["matrixPixels"] = {"spacing": [0, 0, 0]}
        return physical

    def physical(self, el: ET.Element, fixture_physical: dict[str, Any]) -> dict[str, Any]:
        rd = self.rd
        out: dict[str, Any] = {}
        dims = rd.child(el, "Dimensions")
        if dims is not None:
            w, h, d, weight = (parse_float(rd.attr(dims, k)) or 0.0 for k in ("Width", "Height", "Depth", "Weight"))
            array = [w, h, d]
            if w + h + d != 0 and array != fixture_physical.get("dimensions"):
                out["dimensions"] = [int(x) if x == int(x) else x for x in array]
            if weight != 0 and fixture_physical.get("weight") != weight:
                out["weight"] = int(weight) if weight == int(weight) else weight
        tech = rd.child(el, "Technical")
        if tech is not None:
            power = parse_float(rd.attr(tech, "PowerConsumption")) or 0.0
            if power != 0 and fixture_physical.get("power") != power:
                out["power"] = int(power) if power == int(power) else power
            connector = rd.attr(tech, "DmxConnector")
            if connector == "3.5 mm stereo jack":
                connector = "3.5mm stereo jack"
            if connector not in ("", "Other", fixture_physical.get("DMXconnector"), None):
                out["DMXconnector"] = connector
        bulb = rd.child(el, "Bulb")
        if bulb is not None:
            section: dict[str, Any] = {}
            kind = rd.attr(bulb, "Type")
            if kind not in ("", "Other", None, fixture_physical.get("bulb", {}).get("type")):
                section["type"] = kind
            temp = parse_float(rd.attr(bulb, "ColourTemperature"))
            if temp and fixture_physical.get("bulb", {}).get("colorTemperature") != temp:
                section["colorTemperature"] = int(temp) if temp == int(temp) else temp
            lumens = parse_float(rd.attr(bulb, "Lumens"))
            if lumens and fixture_physical.get("bulb", {}).get("lumens") != lumens:
                section["lumens"] = int(lumens) if lumens == int(lumens) else lumens
            if section:
                out["bulb"] = section
        lens = rd.child(el, "Lens")
        if lens is not None:
            section = {}
            name = rd.attr(lens, "Name")
            if name not in ("", "Other", None, fixture_physical.get("lens", {}).get("name")):
                section["name"] = name
            low, high = parse_float(rd.attr(lens, "DegreesMin")) or 0.0, parse_float(rd.attr(lens, "DegreesMax")) or 0.0
            degrees = [int(x) if x == int(x) else x for x in (low, high)]
            if (low != 0 or high != 0) and fixture_physical.get("lens", {}).get("degreesMinMax") != degrees:
                section["degreesMinMax"] = degrees
            if section:
                out["lens"] = section
        focus_el = rd.child(el, "Focus")  # the pan / tilt maximum is used by the pan and tilt channels
        if focus_el is not None:
            rd.attr(focus_el, "PanMax")
            rd.attr(focus_el, "TiltMax")
            if focus_el.get("Type", "Fixed") == "Fixed":  # nothing to keep; a Head, Mirror or Barrel is OFL-less data and reported
                rd.attr(focus_el, "Type")
        layout = rd.child(el, "Layout")
        if layout is not None:  # read by ``layout()`` for the matrix
            rd.attr(layout, "Width")
            rd.attr(layout, "Height")
        return out

    # ---- wheels

    def wheels(self, qchannels: list[ET.Element]) -> dict[str, Any]:
        rd = self.rd
        out: dict[str, Any] = {}
        for qch in qchannels:
            name = rd.attr(qch, "Name") or ""
            caps = rd.children(qch, "Capability")
            group, _ = self.group_of(qch)
            gobo_preset = any(rd.attr(c, "Preset") in ("GoboMacro", "GoboShakeMacro") for c in caps)
            is_wheel = bool(re.search(r"wheel\b", name, re.I)) or gobo_preset
            is_rotation = bool(re.search("rotation|index", name, re.I)) or group == "Speed"
            if not is_wheel or is_rotation:
                continue
            slots = []
            for cap in caps:
                text = rd.text(cap).strip()
                preset = rd.attr(cap, "Preset") or ""
                if _is_rotation_name(text) or re.match(r"^(?:GoboShakeMacro|ColorWheelIndex)$|^Rotation", preset):
                    continue
                slots.append(wheel_slot(cap, text, preset, group))
            if slots:
                out[name] = {"slots": slots}
        return out

    # ---- channels

    def capability(self, qch: ET.Element, qcap: ET.Element, wheels: dict[str, Any], pan: int, tilt: int) -> dict[str, Any]:
        rd = self.rd
        caps = rd.children(qch, "Capability")
        cap: dict[str, Any] = {"dmxRange": [parse_int(rd.attr(qcap, "Min")), parse_int(rd.attr(qcap, "Max"))], "type": ""}
        channel_name = (rd.attr(qch, "Name") or "").strip()
        channel_type, _ = self.group_of(qch)
        cap_name = rd.text(qcap).strip()
        data = CapData(
            qch, channel_name, channel_type, channel_name in wheels, qcap, cap_name,
            caps.index(qcap) if qcap in caps else 0, rd.attr(qcap, "Res1"), rd.attr(qcap, "Res2"), pan, tilt,
        )
        rd.attr(qcap, "Res")
        rd.attr(qcap, "Color")
        rd.attr(qcap, "Color2")
        preset = rd.attr(qcap, "Preset")
        if preset and preset != "Alias":
            cap.update(capability_preset_capability(preset, data))
        elif re.fullmatch(r"nothing|no func(?:tion)?|unused|not used|empty|no strobe|no prism|no frost", cap_name, re.I):
            cap["type"] = "NoFunction"
        elif channel_type == "Intensity":
            cap.update(_parse_intensity(data, rd.child_text(qch, "Colour")))
        elif channel_type in PARSERS:
            cap.update(PARSERS[channel_type](data))
        else:
            cap["type"], cap["comment"] = "Generic", cap_name
        comment = cap.get("comment")
        if comment is not None and (comment == channel_name or comment == "" or re.fullmatch(r"0%?\s*(?:-|to|–|…|\.{2,}|->|<->|→)\s*100%", comment, re.I)):
            del cap["comment"]
        return cap

    def channel(self, qch: ET.Element, wheels: dict[str, Any], pan: int, tilt: int) -> dict[str, Any]:
        rd = self.rd
        channel: dict[str, Any] = {"fineChannelAliases": [], "dmxValueResolution": "8bit", "defaultValue": parse_int(rd.attr(qch, "Default"))}
        name = rd.attr(qch, "Name") or ""
        preset = rd.attr(qch, "Preset")
        caps = rd.children(qch, "Capability")
        self.group_of(qch)
        rd.child(qch, "Colour")
        if preset:
            channel["capabilities"] = [channel_preset_capability(preset, name, pan, tilt)]
        elif caps:
            channel["capabilities"] = [self.capability(qch, c, wheels, pan, tilt) for c in caps]
        else:
            whole = ET.Element("Capability", {"Min": "0", "Max": "255"})
            whole.text = "0-100%"
            rd.seen.add(id(whole))
            channel["capabilities"] = [self.capability(qch, whole, wheels, pan, tilt)]
        return channel

    # ---- fine channels

    def merge_fine(self, qchannels: list[ET.Element], available: dict[str, Any]) -> dict[str, str]:
        """OFL's mergeFineChannels. Returns fine alias -> coarse channel key."""
        rd = self.rd
        fine_rx = re.compile(r"\s*fine\s*|\s*16[\s_-]*bit\s*", re.I)
        fine_of: dict[str, str] = {}
        fines = []
        for qch in qchannels:
            _, byte = self.group_of(qch)
            preset = rd.attr(qch, "Preset")
            if byte == "1" or (preset and preset.endswith("Fine")):
                fines.append(qch)
        for fine in fines:
            key = rd.attr(fine, "Name") or ""
            try:
                coarse = self.coarse_of(fine, qchannels, available, fine_rx)
                if not coarse:
                    raise ValueError("The corresponding coarse channel could not be detected.")
                available[coarse]["fineChannelAliases"].append(key)
                fine_of[key] = coarse
                fine_channel = available[key]
                if len(fine_channel["capabilities"]) > 1:
                    raise ValueError(f"Merge its capabilities into channel '{coarse}'.")
                del available[key]
            except ValueError as problem:
                self.warnings.append(f"Please check 16bit channel '{key}': {problem}")
        return fine_of

    def coarse_of(self, fine: ET.Element, qchannels: list[ET.Element], available: dict[str, Any], fine_rx: re.Pattern) -> str | None:
        rd = self.rd
        key = rd.attr(fine, "Name") or ""
        preset = rd.attr(fine, "Preset")
        if preset:
            coarse_preset = preset[:-4]
            found = [c for c in qchannels if rd.attr(c, "Preset") == coarse_preset]
            if len(found) == 1:
                return rd.attr(found[0], "Name")
        group, _ = self.group_of(fine)
        if group is not None:
            found = []
            for c in qchannels:
                g, byte = self.group_of(c)
                if g is not None and g == group and byte == "0":
                    found.append(c)
            if len(found) == 1:
                return rd.attr(found[0], "Name")
        if not fine_rx.search(key):
            return None
        # (OFL takes the whitespace around "fine" with it: "Dimmer Fine 1" would become "Dimmer1"; the second try keeps one space)
        for coarse_key in (fine_rx.sub("", key, count=1), re.sub(r"\s+", " ", fine_rx.sub(" ", key, count=1)).strip()):
            found = next((k for k in available if k == coarse_key or re.fullmatch(r"\s+|\s+coarse", k.replace(key, "", 1), re.I)), None)
            if found:
                return found
        return None

    # ---- modes

    def mode(self, qmode: ET.Element, fixture_physical: dict[str, Any]) -> dict[str, Any]:
        rd = self.rd
        name = re.sub(r"\s+mode|mode\s+", "", rd.attr(qmode, "Name") or "", flags=re.I)
        mode: dict[str, Any] = {"name": name}
        match = re.search(r"(\d+)(?:\s+|-|)(?:channels?|chan|ch)", name, re.I)
        if match:
            mode["shortName"] = name.replace(match[0], f"{match[1]}ch", 1)
            mode["name"] = name.replace(match[0], f"{match[1]}-channel", 1)
        physical = rd.child(qmode, "Physical")
        if physical is not None:
            data = self.physical(physical, fixture_physical)
            if data:
                mode["physical"] = data
        channels: list[str | None] = []
        for qc in rd.children(qmode, "Channel"):
            number = parse_int(rd.attr(qc, "Number"))
            while len(channels) <= number:
                channels.append(None)
            channels[number] = rd.text(qc)
        mode["channels"] = channels
        return mode

    # ---- switching channels (Alias)

    def switching(self, qchannels: list[ET.Element], available: dict[str, Any], modes: list[dict[str, Any]], qlc_names: list[str | None]) -> None:
        rd = self.rd
        for qch in qchannels:
            caps = rd.children(qch, "Capability")
            if not any(rd.attr(c, "Preset") == "Alias" for c in caps):
                continue
            switches: list[dict[str, Any]] = []
            for index, cap in enumerate(caps):
                for alias in rd.children(cap, "Alias"):
                    default, mode_name, with_ = rd.attr(alias, "Channel"), rd.attr(alias, "Mode"), rd.attr(alias, "With")
                    found = next((s for s in switches if s["default"] == default and mode_name in s["modes"]), None)
                    if found:
                        found["switchTo"][index] = with_
                    else:
                        switches.append({"default": default, "modes": [mode_name], "switchTo": {index: with_}})
            self.merge_similar(switches)
            self.replace_in_modes(switches, modes, qlc_names)
            channel = available.get(rd.attr(qch, "Name") or "")
            if channel is not None:
                for index, cap in enumerate(channel["capabilities"]):
                    cap["switchChannels"] = {s["key"]: s["switchTo"].get(index) or s["default"] for s in switches}

    def merge_similar(self, switches: list[dict[str, Any]]) -> None:
        i = 0
        while i < len(switches):
            s = switches[i]
            j = i + 1
            while j < len(switches):
                other = switches[j]
                if other["default"] == s["default"] and other["switchTo"] == s["switchTo"]:
                    s["modes"].extend(other["modes"])
                    del switches[j]
                else:
                    j += 1
            alternatives = list(dict.fromkeys([s["default"], *s["switchTo"].values()]))
            s["key"] = " / ".join(str(a) for a in alternatives)
            i += 1

    def replace_in_modes(self, switches: list[dict[str, Any]], modes: list[dict[str, Any]], qlc_names: list[str | None]) -> None:
        """Replace the default channel by the switching channel in the modes the Alias names (QLC+'s own mode name:
        OFL's plugin compares with the renamed one, which misses "6 Channel" -> "6-channel")."""
        for s in switches:
            same = [o for o in switches if o["key"] == s["key"]]
            if len(same) > 1:
                for o in same:
                    o["key"] += f" ({', '.join(str(m) for m in o['modes'])})"
            for qlc_name, mode in zip(qlc_names, modes):
                if qlc_name in s["modes"] and s["default"] in mode["channels"]:
                    mode["channels"][mode["channels"].index(s["default"])] = s["key"]

    # ---- clean up (OFL's cleanUpFixture, without the matrix part)

    def clean_up(self, available: dict[str, Any]) -> None:
        for channel in available.values():
            if len(channel["capabilities"]) == 1:
                channel["capability"] = channel.pop("capabilities")[0]
                channel["capability"].pop("dmxRange", None)
                if "defaultValue" not in channel or channel["defaultValue"] == 0:
                    channel.pop("dmxValueResolution", None)
            if channel["fineChannelAliases"]:
                continue
            del channel["fineChannelAliases"]
            channel.pop("dmxValueResolution", None)

    # ---- heads -> matrix

    def layout(self) -> tuple[int, int] | None:
        widths, heights = [], []
        for physical in self.physicals():
            layout = self.rd.child(physical, "Layout")
            if layout is not None:
                widths.append(parse_int(self.rd.attr(layout, "Width")))
                heights.append(parse_int(self.rd.attr(layout, "Height")))
        return (max(widths), max(heights)) if widths else None

    def heads(self, modes: list[dict[str, Any]], available: dict[str, Any], templates: dict[str, Any], fine_of: dict[str, str]) -> dict[str, Any] | None:
        """Turn the heads of every mode into OFL matrix inserts. Returns the matrix, or None when no mode got one."""
        rd = self.rd
        switch_names = {n for ch in available.values() for cap in _caps(ch) for n in [*cap.get("switchChannels", {}), *cap.get("switchChannels", {}).values()]}
        per_mode: list[list[str] | None] = []
        templated: set[str] = set()
        for qmode, mode in zip(self.modes, modes):
            heads = rd.children(qmode, "Head")
            numbers = [[parse_int(rd.text(c)) for c in rd.children(h, "Channel")] for h in heads]
            numbers = [n for n in numbers if n]
            # heads that list the same channels are one pixel as far as DMX goes (OFL's export gives every pixel of a pixel group a head)
            unique: list[list[int]] = []
            for h in numbers:
                if not any(sorted(h) == sorted(u) for u in unique):
                    unique.append(h)
            if len(unique) < len(numbers):
                self.warnings.append(f"mode “{mode['name']}”: {len(numbers)} heads, {len(unique)} different: heads that list the same channels count as one pixel")
            # a channel that several heads list controls them all (a master dimmer): it is a plain channel, not the head's own
            count = {n: sum(n in h for h in unique) for h in unique for n in h}
            unique = [[n for n in h if count[n] == 1] for h in unique]
            unique = [h for h in unique if h]
            if len(unique) < 2:  # no heads, one head, or heads that only share channels: the channels are plain, a fixture with one pixel needs no matrix
                per_mode.append(None)
                continue
            numbers = unique
            per_mode.append(self.insert_heads(mode, numbers, available, templates, fine_of, switch_names, templated))
        used = [k for k in per_mode if k]
        if not used:
            return None
        referenced = {c for mode in modes for c in mode["channels"] if isinstance(c, str)}
        for name in templated - referenced:  # the template channels replace them
            available.pop(name, None)
        every = list(dict.fromkeys(k for keys in used for k in keys))
        for mode, keys in zip(modes, per_mode):
            if keys:
                next(c for c in mode["channels"] if isinstance(c, dict))["repeatFor"] = keys
        count = len(every)
        layout = self.layout()
        width, height = layout if layout and layout[0] * layout[1] == count else (count, 1)
        if height == 1 and every == [str(i + 1) for i in range(count)]:
            return {"pixelCount": [width, 1, 1]}
        return {"pixelKeys": [[every[i * width : (i + 1) * width] for i in range(height)]]}

    def insert_heads(self, mode, numbers, available, templates, fine_of, switch_names, templated) -> list[str] | None:
        """One mode: replace the heads' channels by a matrixChannels insert (its repeatFor is set by the caller).
        Returns the pixel keys, or None when the heads can't be expressed (the channels stay as they are)."""
        channels: list[str | None] = mode["channels"]

        def fail(why: str) -> None:
            # PitchControl would read the plain channels as one pixel and hold the others: better to leave the mode out
            self.skip[mode["name"]] = f"the heads can't be pixels ({why})"

        seen: set[int] = set()
        for head in numbers:
            for n in head:
                if n >= len(channels) or channels[n] is None:
                    return fail(f"a head lists channel number {n}, which the mode doesn't have")
                seen.add(n)
        heads = sorted((sorted(h) for h in numbers), key=lambda h: h[0])
        names = [[channels[n] for n in h] for h in heads]
        if len({len(h) for h in heads}) != 1:
            return fail("the heads don't all have the same number of channels")
        flat = [n for h in heads for n in h]
        positions = sorted(flat)
        start = positions[0]
        if positions != list(range(start, start + len(positions))):
            return fail("the heads' channels are not one block of the mode's channels")
        size, count = len(heads[0]), len(heads)
        if flat == positions:
            order = "perPixel"
        elif count > 1 and all(positions[j * count + i] == heads[i][j] for i in range(count) for j in range(size)):
            order = "perChannel"
        else:
            return fail("the channels of the heads are mixed in a way OFL's matrix can't describe")
        if any(n in switch_names for h in names for n in h):
            return fail("a head channel is a switching channel")
        signatures = [[self.signature(n, available, fine_of, h) for n in h] for h in names]
        if any(s is None for s in signatures[0]):
            return fail("a head channel is not a defined channel")
        if any(s != signatures[0] for s in signatures[1:]):
            return fail("the heads' channels differ")

        columns = [list(c) for c in zip(*names)]
        splits = [template_split(c) for c in columns]  # (template, keys) when the names differ by one number
        first = next((s for s in splits if s), None)
        keys = first[1] if first else [str(i + 1) for i in range(count)]
        block: list[str] = []
        for column in columns:
            if column[0] in fine_of:  # a fine channel is listed by its alias's template key
                block.append(self.template_key(column, keys))
                continue
            definition = copy.deepcopy(available[column[0]])
            definition["fineChannelAliases"] = [self.template_key([available[c]["fineChannelAliases"][i] for c in column], keys) for i in range(len(definition.get("fineChannelAliases", [])))]
            if not definition["fineChannelAliases"]:
                del definition["fineChannelAliases"]
            key = self.template_key(column, keys)
            if key in templates and templates[key] != definition:  # another mode's template of the same name differs
                key = key.replace(PIXEL_KEY, f"{PIXEL_KEY} ({mode['name']})")
            templates[key] = definition
            templated.update(column)
            block.append(key)
        channels[start : start + len(positions)] = [{"insert": "matrixChannels", "repeatFor": [], "channelOrder": order, "templateChannels": block}]
        return keys

    @staticmethod
    def template_key(column: list[str], keys: list[str]) -> str:
        """``Red $pixelKey`` for the names ``Red 1``, ``Red 2``, … (when their number is the pixel key), else the name
        without its digits and ``$pixelKey``."""
        split = template_split(column)
        if split and split[1] == keys:
            return split[0]
        return (re.sub(r"\d+", "", column[0]).strip() or "Channel") + " " + PIXEL_KEY

    @staticmethod
    def signature(name: str | None, available: dict[str, Any], fine_of: dict[str, str], head: list[str | None]) -> Any:
        """What a head channel is, apart from its name: equal heads have equal signatures."""
        if name in fine_of:
            coarse = fine_of[name]
            return "fine", head.index(coarse) if coarse in head else -1, available.get(coarse, {}).get("fineChannelAliases", []).index(name)
        channel = available.get(name or "")
        if channel is None:
            return None
        return json.dumps({k: v for k, v in channel.items() if k != "fineChannelAliases"}, sort_keys=True), len(channel.get("fineChannelAliases", []))

    def warn_extra_colours(self, modes: list[dict[str, Any]], available: dict[str, Any]) -> None:
        """A mode that lists several red channels as plain channels (a bar without ``<Head>`` elements, or with pixel
        groups the heads can't express): PitchControl would take the first R G B (W) run as the one pixel and hold
        the other colour channels at their default value."""
        for mode in modes:
            if mode["name"] in self.skip or any(isinstance(c, dict) for c in mode["channels"]):
                continue  # left out anyway, or the pixels of the heads are the colours
            reds = [c for c in mode["channels"] if isinstance(c, str) and _colour_of(available.get(c)) == "Red"]
            if len(reds) > 1:
                self.warnings.append(
                    f"mode “{mode['name']}” has {len(reds)} red channels as plain channels (no <Head> elements, or heads that share channels): PitchControl takes the first "
                    "R G B (W) run as the one pixel and holds the other colour channels at their default value (add the pixels by hand in the Fixtures page)"
                )


def _caps(channel: dict[str, Any]) -> list[dict[str, Any]]:
    return channel["capabilities"] if "capabilities" in channel else [channel["capability"]]


def _colour_of(channel: dict[str, Any] | None) -> str | None:
    if not channel:
        return None
    caps = _caps(channel)
    return caps[0].get("color") if len(caps) == 1 and caps[0].get("type") == "ColorIntensity" else None


def template_split(names: list[str]) -> tuple[str, list[str]] | None:
    """``["Red 1", "Red 2", "Red 3"]`` -> ``("Red $pixelKey", ["1", "2", "3"])``: the names must be the same apart from
    one number; None when they are not (or there is one name only)."""
    parts = [re.split(r"(\d+)", n) for n in names]
    if len(names) < 2 or len({len(p) for p in parts}) != 1:
        return None
    differing = [i for i in range(len(parts[0])) if len({p[i] for p in parts}) > 1]
    if len(differing) != 1:
        return None
    i = differing[0]
    keys = [p[i] for p in parts]
    if not all(k.isdigit() for k in keys) or len(set(keys)) != len(keys):
        return None
    return "".join(parts[0][:i]) + PIXEL_KEY + "".join(parts[0][i + 1 :]), keys


# --------------------------------------------------------------------------- entry point


def qxf_to_ofl(source: str | bytes, *, today: str | None = None) -> Qlc:
    """Read a QLC+ fixture definition and build the OFL fixture. Raises ``ImportProblem`` when it isn't one."""
    root = parse_xml(source)
    converter = _Converter(root, today or date.today().isoformat())
    result = converter.convert()
    text = source.decode("utf-8", errors="replace") if isinstance(source, bytes) else source
    result.kept["xml"] = text
    return result


QLC_CHECK = "QLC+ fixture definitions are written by volunteers: compare the modes, channels and values with the fixture's manual before using the type."


def import_qxf(source: str | bytes, *, file: str | None = None, today: str | None = None) -> Imported:
    """The PitchControl type and the import report for a QLC+ fixture definition (the file's bytes or text): the
    ``.qxf`` is read into the OFL model (``qxf_to_ofl``) and imported like an OFL fixture, so there is one mapping to
    PitchControl. ``source.via`` says it came from QLC+, ``source.file`` has the file name and the type's ``qlcplus``
    key keeps what OFL's model can't hold."""
    qlc = qxf_to_ofl(source, today=today)
    made_by = f", made by {qlc.creator}" if qlc.creator else ""
    note = f"converted from a QLC+ fixture definition{' (' + file + ')' if file else ''}{made_by}; QLC+'s data is kept under qlcplus"
    result = import_fixture(
        qlc.ofl,
        manufacturer=qlc.manufacturer or None,
        file=file,
        note=note,
        via="qlcplus",
        where=f"a QLC+ fixture definition{' (' + file + ')' if file else ''}",
        licence=None,
        keep={"qlcplus": qlc.kept},
        skip=qlc.skip,
        check=QLC_CHECK,
    )
    result.report.dropped = qlc.dropped
    result.report.notes.extend(qlc.warnings)
    return result
