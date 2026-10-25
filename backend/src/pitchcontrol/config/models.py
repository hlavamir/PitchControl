"""Configuration models.

Every model allows unknown keys (``extra="allow"``) so that a typo never stops the
show; the loader reports unknown keys to the log instead (see ``loader.py``).
Missing keys are filled with the defaults defined here.
"""

from __future__ import annotations

import ipaddress
import logging
import math
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

log = logging.getLogger(__name__)



def _merge_legacy_gamma(data, where: str):
    """Old configs had brightness_gamma (on the HSV value) and rgb_gamma (per channel); both are now
    one per-channel ``gamma``. Their product is the closest single curve."""
    if not isinstance(data, dict) or not ({"brightness_gamma", "rgb_gamma"} & data.keys()):
        return data
    data = dict(data)
    old = {k: data.pop(k) for k in ("brightness_gamma", "rgb_gamma") if k in data}
    if "gamma" not in data:
        values = [float(v) for v in old.values() if v is not None]
        if values:
            g = 1.0
            for v in values:
                g *= v
            data["gamma"] = g
        log.info("%s: %s replaced by gamma = %s (one per-channel gamma now)", where, ", ".join(old), data.get("gamma"))
    return data


class Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# Macros that were renamed in 1.5. Files written before (controller mappings, scenes, state/macros.json) still use the
# old names; every model that stores a macro name (a mapping, a scene, a fixture type's macro channel, the idle mask range
# of a rig's fixture, the fog setting) reads them through here, and a file gets the new names when it is next saved. Add
# to this table when a macro is renamed again, so older files keep loading.
MACRO_RENAMES = {
    "Shader Speed": "Mask Param A",
    "Shader Param": "Mask Param B",
    "Preset A": "Mask A",
    "Preset B": "Mask B",
    "Preset C": "Mask C",
    "Preset D": "Mask D",
}


def current_macro_name(name: str) -> str:
    return MACRO_RENAMES.get(name, name)


def current_macro_names(values: dict[str, Any]) -> dict[str, Any]:
    """``values`` with the renamed macros under their new names; a new name already there wins over an old one."""
    out = {k: v for k, v in values.items() if k not in MACRO_RENAMES}
    for old, new in MACRO_RENAMES.items():
        if old in values:
            out.setdefault(new, values[old])
    return out


# --------------------------------------------------------------------------- colours


class HSB(Model):
    """A colour as hue / saturation / brightness, all 0..1 (hue wraps)."""

    h: float = 0.0
    s: float = 1.0
    b: float = 1.0


# --------------------------------------------------------------------------- fixture types

# "I": one brightness value per pixel (the brightest of its R, G, B), for any single-colour light. Called "R" up to 1.6.
PixelFormat = Literal["I", "RGB", "RGBW"]


class Shutter(Model):
    """Shutter / strobe channel values used for "real strobo" (see port-design, Future: Hardware Strobe)."""

    open: int = 0
    strobo: int = 255


class ChannelSlot(Model):
    """One entry of a fixture profile.

    Exactly one of ``value`` (constant), ``pixels`` (the pixel block), ``macro``
    (a macro's value scaled to 0..255) or ``shutter`` must be given.
    """

    name: str | None = None
    value: int | None = Field(default=None, ge=0, le=255)
    pixels: PixelFormat | None = None
    macro: str | None = None
    shutter: Shutter | None = None

    @field_validator("macro", mode="before")
    @classmethod
    def _renamed_macro(cls, v: Any) -> Any:
        return current_macro_name(v) if isinstance(v, str) else v

    @field_validator("pixels", mode="before")
    @classmethod
    def _renamed_format(cls, v: Any) -> Any:
        return "I" if v == "R" else v  # the single-channel format was called R until 1.6

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> "ChannelSlot":
        kinds = [self.value is not None, self.pixels is not None, self.macro is not None, self.shutter is not None]
        if sum(kinds) != 1:
            raise ValueError("a channel needs exactly one of: value, pixels, macro, shutter")
        return self

    @property
    def kind(self) -> str:
        if self.value is not None:
            return "value"
        if self.pixels is not None:
            return "pixels"
        if self.macro is not None:
            return "macro"
        return "shutter"


def _mode_id(text: str) -> str:
    """A mode's id from its name: ``6CH`` -> ``6ch``, ``3CH-1`` -> ``3ch-1`` (what the UI makes for a new mode)."""
    slug = "".join(c if c.isalnum() else "-" for c in text.lower())
    return "-".join(part for part in slug.split("-") if part) or "mode"


class ChannelMode(Model):
    """One DMX channel mode of a fixture type: a name (free text, e.g. "6CH"), a short description and the
    channel layout. ``id`` is what a rig fixture stores, so renaming a mode never breaks a rig."""

    id: str = ""
    name: str = ""
    description: str = ""
    # how many pixels the light has in this mode (a bar can have 1 or 8 depending on the mode)
    pixels: int = Field(default=1, ge=1)
    channels: list[ChannelSlot] = Field(default_factory=lambda: [ChannelSlot(pixels="RGB")])
    # imported from the Open Fixture Library (item 53): the ``name`` of the OFL mode this one was converted from
    ofl_mode: str | None = None

    def channel_count(self) -> int:
        total = 0
        for ch in self.channels:
            total += self.pixels * len(ch.pixels) if ch.pixels else 1
        return total


class FixtureType(Model):
    name: str = ""
    description: str = ""
    transport: Literal["dmx", "pitchpls_v2"] = "dmx"
    # One or more channel modes; a rig fixture picks one (FixtureInstance.mode). Files before 1.6 have a
    # bare ``channels`` list: it loads as one mode, named by its channel count, and is written back as
    # ``modes`` when the type is next saved. The pixel count belongs to each mode (1.6.1: before, one ``pixels``
    # per type); a type-level ``pixels`` in an older file becomes the count of every mode that has none.
    modes: list[ChannelMode] = Field(default_factory=lambda: [ChannelMode()])
    default_mode: str = ""  # a mode's id: a new rig fixture starts in it, and a fixture without a mode uses it
    # Decodes the perceptual values the engine works with into what the device expects, per output
    # channel: device value = value ** gamma. 1 = send perceptual values unchanged, for devices that
    # decode themselves (PitchPlease v2 / v3 firmware apply 2.2). Must be > 0 (an invalid value falls
    # back to 1 with a warning).
    gamma: float = 1.0
    strobo_color: HSB = Field(default_factory=lambda: HSB(h=0, s=0, b=1))
    # Kept data of an import (item 53, shape in ``ofl/importer.py``): where the type came from, and the original
    # fixture's keys under their Open Fixture Library names, not used by the engine, written back as they were read.
    # Typed ``Any``: the data is OFL's (or a later importer's), PitchControl only carries it.
    source: dict[str, Any] | None = None
    ofl_modes: list[Any] | None = None  # OFL's own ``modes`` list (OFL's name collides with ``modes`` above)
    shortName: Any = None
    categories: Any = None
    meta: Any = None
    comment: Any = None
    links: Any = None  # {"manual": [url, ...], "productPage": [...], "video": [...]}: shown on the Fixtures page
    helpWanted: Any = None
    rdm: Any = None
    physical: Any = None
    matrix: Any = None
    wheels: Any = None
    availableChannels: Any = None
    templateChannels: Any = None
    qlcplus: dict[str, Any] | None = None  # item 54: what a QLC+ import kept (creator, type, unmapped, the .qxf's own text)
    # Whether a fixture flashes on strobo peaks is a rig setting (FixtureInstance.react_to_strobo).
    # Type files written before 2026-10-08 still say it; that value only fills in rig fixtures that
    # don't set it themselves (ConfigStore.load_rig), and is not written back.
    legacy_react_to_strobo: bool | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        where = f"fixture type {data.get('name', '') if isinstance(data, dict) else ''}".strip()
        data = _merge_legacy_gamma(data, where)
        if isinstance(data, dict) and "react_to_strobo" in data:
            data = dict(data)
            data["legacy_react_to_strobo"] = data.pop("react_to_strobo")
        if isinstance(data, dict) and "channels" in data:  # before 1.6: one channel layout, no modes
            data = dict(data)
            channels = data.pop("channels")
            if data.get("modes"):
                log.warning("%s: has both channels and modes, channels ignored", where)
            else:
                data["modes"] = [{"channels": channels}]
        if isinstance(data, dict) and "pixels" in data:  # before 1.6.1: one pixel count for the whole type
            data = dict(data)
            pixels = data.pop("pixels")
            if isinstance(data.get("modes"), list):
                data["modes"] = [{"pixels": pixels, **m} if isinstance(m, dict) else m for m in data["modes"]]
            else:
                data["modes"] = [{"pixels": pixels}]
        return data

    @field_validator("gamma", mode="before")
    @classmethod
    def _gamma_positive(cls, v):
        if v is None or float(v) <= 0:
            log.warning("fixture type: gamma must be > 0 (got %r), using 1", v)
            return 1.0
        return v

    @model_validator(mode="after")
    def _complete_modes(self) -> "FixtureType":
        """At least one mode; every mode has a name (its channel count) and a unique id; the default exists."""
        if not self.modes:
            log.warning("fixture type %s: no channel mode, using one with an RGB pixel block", self.name)
            self.modes = [ChannelMode()]
        seen: set[str] = set()
        for mode in self.modes:
            if not mode.name:
                mode.name = f"{mode.channel_count()}CH"
            wanted = mode.id or _mode_id(mode.name)
            mode.id, n = wanted, 2
            while mode.id in seen:
                mode.id, n = f"{wanted}-{n}", n + 1
            if mode.id != wanted:
                log.warning("fixture type %s: mode id '%s' is used twice, this one is now '%s'", self.name, wanted, mode.id)
            seen.add(mode.id)
        if self.default_mode not in seen:
            if self.default_mode:
                log.warning("fixture type %s: default mode '%s' does not exist, using '%s'", self.name, self.default_mode, self.modes[0].id)
            self.default_mode = self.modes[0].id
        return self

    def mode_of(self, mode_id: str | None) -> ChannelMode:
        """The mode with this id; none or an unknown id gives the default mode."""
        for mode in self.modes:
            if mode.id == mode_id:
                return mode
        return next(m for m in self.modes if m.id == self.default_mode)

    def has_mode(self, mode_id: str) -> bool:
        return any(m.id == mode_id for m in self.modes)

    def channel_count(self, mode_id: str | None = None) -> int:
        """Channels one fixture takes in this mode (none: the default mode)."""
        return self.mode_of(mode_id).channel_count()

    def pixel_count(self, mode_id: str | None = None) -> int:
        """Pixels one fixture has in this mode (none: the default mode)."""
        return self.mode_of(mode_id).pixels


# --------------------------------------------------------------------------- rigs

T = TypeVar("T")


class Override(Model, Generic[T]):
    """A fixture's override of a fixture-type value. Switched off, the type's value is used but the
    override value is kept, so switching it on again restores it (the UI's override checkbox)."""

    enabled: bool = True
    value: T


OVERRIDABLE = ("gamma", "strobo_color")


def _wrap_plain_overrides(data, where: str):
    """Old rigs stored overrides as plain values ("gamma": 2.0, "channel_values": {"mode": 2});
    they become enabled overrides. The per-fixture pixel count is no longer overridable."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    for key in OVERRIDABLE:
        v = data.get(key)
        if v is not None and not (isinstance(v, dict) and "value" in v):
            data[key] = {"enabled": True, "value": v}
    cv = data.get("channel_values")
    if isinstance(cv, dict):
        data["channel_values"] = {
            k: v if isinstance(v, dict) and "value" in v else {"enabled": True, "value": v} for k, v in cv.items()
        }
    if data.get("pixels") is not None:
        log.warning("%s: a per-fixture pixel count is no longer supported (ignored); use a fixture type with that many pixels", where)
    data.pop("pixels", None)
    return data



class IdleMaskRange(Model):
    """Remap of the sampled mask value: ``lerp(min, max, mask ** (2 ** curve))``.

    If ``macro`` is set, the range only applies while that macro is on (> 0.5),
    otherwise the identity range is used. This is how "Invert Discoball" works.
    """

    min: float = 0.0
    max: float = 1.0
    curve: float = 0.0
    macro: str | None = None

    @field_validator("macro", mode="before")
    @classmethod
    def _renamed_macro(cls, v: Any) -> Any:
        return current_macro_name(v) if isinstance(v, str) else v


class FixtureInstance(Model):
    name: str = ""
    type: str = ""
    # the id of a channel mode of the type (see ChannelMode); missing = the type's default mode. Not in scenes.
    mode: str | None = None
    enabled: bool = True
    group: Literal["A", "B"] = "A"

    # DMX placement (1-based address, as printed on fixtures)
    universe: int = Field(default=0, ge=0)
    address: int = Field(default=1, ge=1, le=512)

    # placement in the square UV scene (u right, v down, 0..1)
    position: tuple[float, float] = (0.5, 0.5)
    rotation: float = 0.0  # degrees, clockwise on screen (90 = down, 270 = vertical with the first pixel at the bottom)
    length: float = 0.0  # pixels are spread along this length, centred on position
    pixel_positions: list[tuple[float, float]] | None = None  # explicit positions override the spread

    # overrides of fixture-type values (None = never overridden; switched off = type's value)
    gamma: Override[float] | None = None  # > 0
    strobo_color: Override[HSB] | None = None
    channel_values: dict[str, Override[int]] = Field(default_factory=dict)  # constant channels by name
    react_to_strobo: bool = False  # flash on strobo peaks (a rig setting)
    real_strobo: bool = False  # use the type's shutter channel on peaks (only for types with one)

    dimmer_macro: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        where = f"fixture {data.get('name', '') if isinstance(data, dict) else ''}".strip()
        data = _wrap_plain_overrides(_merge_legacy_gamma(data, where), where)
        # react_to_strobo used to be a type value with a per-fixture override: an enabled override
        # becomes the fixture's value; a switched-off or missing one is left unset, so load_rig
        # fills it in from the old type value
        v = data.get("react_to_strobo") if isinstance(data, dict) else None
        if isinstance(v, dict):
            data = dict(data)
            if v.get("enabled", True):
                data["react_to_strobo"] = v.get("value")
            else:
                data.pop("react_to_strobo")
        return data

    @field_validator("gamma", mode="after")
    @classmethod
    def _gamma_positive(cls, v):
        if v is not None and v.value <= 0:
            log.warning("fixture: gamma override must be > 0 (got %r), dropped", v.value)
            return None
        return v

    @field_validator("channel_values", mode="after")
    @classmethod
    def _channel_values_in_range(cls, v):
        for name, o in v.items():
            if not 0 <= o.value <= 255:
                raise ValueError(f"channel value '{name}' must be 0–255, got {o.value}")
        return v

    def override(self, key: str, default):
        """The fixture's value for an overridable type property."""
        o = getattr(self, key)
        return o.value if o is not None and o.enabled else default

    def channel_value(self, name: str | None, default: int) -> int:
        o = self.channel_values.get(name) if name else None
        return o.value if o is not None and o.enabled else default

    # colour sources (see port-design, Colour and Brightness Model)
    hue_source: Literal["group", "A", "B", "const"] = "group"
    hue: float = 0.0
    saturation_source: Literal["group", "A", "B", "const"] = "group"
    saturation: float = 1.0
    brightness_source: Literal["pipeline", "const"] = "pipeline"
    brightness: float = 1.0

    idle_mask_range: IdleMaskRange = Field(default_factory=IdleMaskRange)


class FogMachine(Model):
    name: str = "Fog"
    enabled: bool = True
    universe: int = 0
    channel: int = Field(default=1, ge=1, le=512)
    on_value: int = Field(default=255, ge=0, le=255)
    off_value: int = Field(default=0, ge=0, le=255)
    interval_s: float = 60.0
    duration_s: float = 4.0
    manual_macro: str | None = "Fog Machine"

    @field_validator("manual_macro", mode="before")
    @classmethod
    def _renamed_manual_macro(cls, v: Any) -> Any:
        return current_macro_name(v) if isinstance(v, str) else v


class Rig(Model):
    name: str = ""
    description: str = ""
    fixtures: list[FixtureInstance] = Field(default_factory=list)
    # names of the dimmer macros in this rig ("Dimmer 03" → "D Pinspots"); without a name the UI
    # shows the macro name. Which dimmer a fixture follows is its dimmer_macro; a dimmer that no
    # fixture uses is unassigned: disabled in the UI and ignored by MIDI.
    dimmer_names: dict[str, str] = Field(default_factory=dict)
    # the fog machines of this setup (Fog page); up to 1.4 they were in settings.json
    fog_machines: list[FogMachine] = Field(default_factory=list)
    # Until 1.8.2 the rig had a "mask_curve" (-3 ... +3, the mask's exponent was 2 ** mask_curve); it is the macro Mask Curve
    # now (item 76). An old file's value is read here, once, for the engine to turn into the macro (``Store.legacy_mask_curve``),
    # and is never written back.
    legacy_mask_curve: float | None = Field(default=None, alias="mask_curve", exclude=True)

    @field_validator("legacy_mask_curve", mode="after")
    @classmethod
    def _legacy_mask_curve_is_a_number(cls, v):
        return v if v is not None and math.isfinite(v) else None


# --------------------------------------------------------------------------- settings


class DeviceRef(Model):
    """A USB serial device, matched by serial number + VID:PID first, port path as fallback."""

    serial_number: str | None = None
    vid: int | None = None
    pid: int | None = None
    description: str | None = None
    port: str | None = None


class AudioSettings(Model):
    device: str | None = None  # name (substring) of the input device; None = system default
    channels: list[int] = Field(default_factory=lambda: [1, 2])  # 1-based input channels, summed
    gain: float = 1.0
    sample_rate: int = 48000
    fft_size: int = 2048
    hop: int = 512
    bands: int = 32
    fmin: float = 35.0
    fmax: float = 10000.0
    floor_db: float = -80.0
    range_db: float = 80.0
    release_s: float = 0.08
    normalisation_decay: float = 0.998  # per frame
    normalisation_floor: float = 0.25  # stops a quiet input (noise) from being scaled up to full level
    trigger_full_hz: float = 100.0
    trigger_zero_hz: float = 5000.0


class EnttecSettings(Model):
    """One USB DMX interface (the settings key is still ``enttec``, from before there were more types)."""

    enabled: bool = False
    device: DeviceRef = Field(default_factory=DeviceRef)
    universe: int = 0
    # auto: found out from the USB device (Enttec Pro protocol when nothing tells);
    # pro: Enttec DMX USB Pro and compatibles (DMXKing ultraDMX …): the interface makes the DMX
    #      signal from our packets; open: Enttec Open DMX USB, a bare FTDI chip: we make the signal
    type: Literal["auto", "pro", "open"] = "auto"
    # open only, how the break (the 88 µs low before a frame) is made: "baud" = one 0x00 byte at a
    # lower baud rate; "break" = the serial port's break condition (the macOS FTDI driver stops
    # sending data after it, 2026-10-11)
    break_method: Literal["break", "baud"] = "baud"
    # open only: log the timing of each frame the writer sends (a summary every 10 s, and a line per late
    # frame), to find out why a frame is lost now and then
    log_timing: bool = False


class ArtNetTarget(Model):
    universe: int = 0  # internal universe
    ip: str = "127.255.255.255"
    artnet_universe: int | None = None  # defaults to ``universe``


class ArtNetSettings(Model):
    enabled: bool = False
    targets: list[ArtNetTarget] = Field(default_factory=list)


class PitchPlsV2Settings(Model):
    enabled: bool = False
    device: DeviceRef = Field(default_factory=DeviceRef)
    baudrate: int = 921600
    mode: int = 0  # mirror mode byte understood by the v2.2 firmware
    strips: int = 4
    pixels_per_strip: int = 19  # the firmware mirrors these to 38 LEDs


class OscSettings(Model):
    """OSC out: what is sent is described by a file in the ``osc`` folder (see ``io/osc.py``)."""

    enabled: bool = False
    host: str = "127.0.0.1"  # IP address or name of the receiver (a broadcast address works too)
    port: int = Field(default=8010, ge=1, le=65535)
    file: str = ""  # name (without .json) of a file in the osc folder; none = nothing is sent


MAX_ENTTEC = 4  # USB DMX interfaces that can be driven at once


class OutputSettings(Model):
    # one entry per Enttec DMX USB Pro, each sending its own universe; the position in the list is
    # the interface number shown in the UI
    enttec: list[EnttecSettings] = Field(default_factory=list, max_length=MAX_ENTTEC)
    artnet: ArtNetSettings = Field(default_factory=ArtNetSettings)
    pitchpls_v2: PitchPlsV2Settings = Field(default_factory=PitchPlsV2Settings)
    osc: OscSettings = Field(default_factory=OscSettings)

    @model_validator(mode="before")
    @classmethod
    def _enttec_list(cls, data: Any) -> Any:
        # before 1.2.0 there was a single interface: {"enabled": …, "device": …, "universe": …}
        if isinstance(data, dict) and isinstance(data.get("enttec"), dict):
            data = {**data, "enttec": [data["enttec"]]}
        return data


class FogSettings(Model):
    """Up to 1.4 the fog machines were settings; now they belong to the rig (``Rig.fog_machines``).
    Still read from an old settings.json, so the loader can move them into the rigs."""

    machines: list[FogMachine] = Field(default_factory=list)


class MaskSettings(Model):
    line_falloff: float = 0.12  # soft edge width of the line masks, in UV units
    transition_s: float = 2.5  # mask crossfade time


def _default_palette() -> list[HSB]:
    hues = [0, 0.041666668, 0.097222224, 0.30555555, 0.375, 0.6388889, 0.6805556, 0.7222222, 0.7777778]
    return [HSB(h=h, s=1, b=1) for h in hues]


class UiSettings(Model):
    """Appearance of the web UI, chosen on the Settings page."""

    ink: Literal["grey", "amber", "phosphor"] = "grey"
    key_hints: bool = True
    start_fullscreen: bool = False  # desktop app: open in full screen
    scale: float = Field(default=1.0, ge=0.6, le=1.5)  # UI zoom; 1 = the 1512×915 design size

    @model_validator(mode="before")
    @classmethod
    def _removed_settings(cls, data: Any) -> Any:
        # up to 1.7.1 the UI had a glow strength and a brightness (ink dimmed to 40 %); both are gone (glow is always 100 %, the
        # ink at full brightness). A file that still has them loads without a word and is written without them
        if isinstance(data, dict) and ({"glow", "brightness"} & data.keys()):
            data = {k: v for k, v in data.items() if k not in ("glow", "brightness")}
        return data


DEFAULT_PORT = 8420  # where the UI is served; also the default port for other devices on the network
PIN_LENGTHS = (4, 8)


class NetworkSettings(Model):
    """Other devices (a phone, an iPad) opening the UI over the network. Off unless this computer's owner turns
    it on: anyone who can reach the port then controls the lights and changes the rig."""

    enabled: bool = False
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)  # fixed: never moved to another one when it is taken
    pin: str = ""  # 4 to 8 digits; empty = no PIN. Asked from every device but this computer

    @field_validator("pin", mode="after")
    @classmethod
    def _pin_is_digits(cls, v: str) -> str:
        if v and not (v.isascii() and v.isdigit() and PIN_LENGTHS[0] <= len(v) <= PIN_LENGTHS[1]):
            raise ValueError(f"the PIN is {PIN_LENGTHS[0]} to {PIN_LENGTHS[1]} digits (or empty for none)")
        return v


ARTNET_PORT = 6454  # the Art-Net standard port, for the output and the default of the input


class ArtNetInputSettings(Model):
    """Art-Net in: the UDP listener (item 57). ``adapter`` is an IPv4 address of this computer; empty = all adapters."""

    enabled: bool = False
    port: int = Field(default=ARTNET_PORT, ge=1, le=65535)  # another one when another Art-Net program listens on 6454
    adapter: str = ""

    @field_validator("adapter", mode="after")
    @classmethod
    def _adapter_is_an_address(cls, v: str) -> str:
        v = v.strip()
        if v:
            try:
                ipaddress.IPv4Address(v)
            except ValueError:
                raise ValueError(f"'{v}' is not an IPv4 address (empty = all network adapters)") from None
        return v


class DmxInputSettings(Model):
    """DMX in over USB: an Enttec DMX USB Pro that receives (item 57). A Pro that receives doesn't send."""

    enabled: bool = False
    device: DeviceRef = Field(default_factory=DeviceRef)


class LiveInputSettings(Model):
    """Live input (items 57 to 59): per computer, in machine.json."""

    artnet: ArtNetInputSettings = Field(default_factory=ArtNetInputSettings)
    dmx: DmxInputSettings = Field(default_factory=DmxInputSettings)


class MidiDeviceSetting(Model):
    """One MIDI device of this computer (item 89): per computer, in machine.json, keyed by ``port_key``."""

    name: str = ""  # the port's name as the system listed it last
    input: bool = True  # In: the app listens to the device (a device seen for the first time is on)
    output: bool = False  # Out: for LED feedback to the controller; nothing sends yet


class Settings(Model):
    fps: float = 40.0
    preview_fps: float = 15.0
    active_rig: str = "default"
    active_controller: str | None = "lcxl3"
    midi_input: str | None = None  # item 89: no longer a choice; a value from an earlier version turns that device's In on, once, and goes
    midi_devices: dict[str, MidiDeviceSetting] = Field(default_factory=dict)  # per computer (item 89)
    midi_settle_s: float = 0.4  # hue/saturation knobs apply once they rest this long
    audio: AudioSettings = Field(default_factory=AudioSettings)
    outputs: OutputSettings = Field(default_factory=OutputSettings)
    fog: FogSettings = Field(default_factory=FogSettings, exclude=True)  # legacy, never written: see FogSettings
    masks: MaskSettings = Field(default_factory=MaskSettings)
    auto_colors: list[HSB] = Field(default_factory=_default_palette)
    ui: UiSettings = Field(default_factory=UiSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    live_input: LiveInputSettings = Field(default_factory=LiveInputSettings)


# --------------------------------------------------------------------------- MIDI controllers


MidiKind = Literal["cc", "note"]
# absolute: a fader or knob (value/127) · relative: an encoder, each message turns the value up or down ·
# toggle: flips on every press · momentary: on while pressed (also right for buttons that toggle themselves
# on the controller) · trigger: one press, for scene buttons and the like · shift: the modifier button
MAX_SENSITIVITY = 127.0  # relative mode: one message covers the whole range
MidiMode = Literal["absolute", "relative", "toggle", "momentary", "trigger", "shift"]
Encoder = Literal["twos_complement", "sign_bit", "offset_64"]


class MidiMapping(Model):
    """One MIDI control (a CC or a note) and what it does."""

    type: MidiKind = "cc"
    number: int = Field(ge=0, le=127)  # CC or note number
    macro: str | None = None  # none for ``shift``
    mode: MidiMode = "absolute"
    channel: int | None = Field(default=None, ge=1, le=16)  # 1-based; none = the controller's channel
    page: Literal["general", "dimmers"] | None = None  # only while this control page is active; none = on every page
    shift: Literal["on", "off"] | None = None  # only while shift is held / not held; none = either way
    invert: bool = False
    encoder: Encoder = "twos_complement"  # relative mode: how the controller sends its steps
    sensitivity: float = Field(default=1.0, gt=0)  # relative mode: 1 = 127 steps for the whole range
    note: str = ""

    @field_validator("macro", mode="before")
    @classmethod
    def _renamed_macro(cls, v: Any) -> Any:
        return current_macro_name(v) if isinstance(v, str) else v

    @model_validator(mode="before")
    @classmethod
    def _legacy_cc(cls, data: Any) -> Any:
        # before 1.5 a mapping was {"cc": 29, "macro": …}
        if isinstance(data, dict) and "cc" in data and "number" not in data:
            data = dict(data)
            data["number"] = data.pop("cc")
        return data

    @field_validator("sensitivity", mode="after")
    @classmethod
    def _sensitivity_in_range(cls, v: float) -> float:
        if v > MAX_SENSITIVITY:  # one message already covers the whole range
            log.warning("MIDI mapping: sensitivity %s is more than %s (the whole range in one step): using %s", v, MAX_SENSITIVITY, MAX_SENSITIVITY)
            return MAX_SENSITIVITY
        return v

    @model_validator(mode="after")
    def _macro_needed(self) -> "MidiMapping":
        if self.mode != "shift" and not self.macro:
            raise ValueError("a mapping needs a macro (except shift)")
        return self

    @model_validator(mode="after")
    def _sensible_settings(self) -> "MidiMapping":
        # settings that mean nothing are set right (and reported to the log) instead of stopping the file from loading
        where = f"MIDI mapping {self.type} {self.number}"
        if self.type == "note" and self.mode == "relative":
            log.warning("%s: a note can't be an encoder (relative): used as absolute", where)
            self.mode = "absolute"
        if self.mode == "shift":
            for field, unset in (("page", None), ("shift", None), ("invert", False)):
                if getattr(self, field) != unset:
                    log.warning("%s: the shift button has no '%s' setting: ignored", where, field)
                    setattr(self, field, unset)
        return self


class Controller(Model):
    name: str = ""
    author: str = ""
    description: str = ""
    contact: str = ""  # an email address or a website
    modified: str = ""  # date and time of the last edit in the app (the file also says which version wrote it)
    port_match: str = ""  # substring of the MIDI port name
    channel: int = Field(default=1, ge=1, le=16)  # 1-based MIDI channel of the controls (a mapping can use another)
    mappings: list[MidiMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_shift_button(self) -> "Controller":
        shifts = [m for m in self.mappings if m.mode == "shift"]
        if len(shifts) > 1:  # the engine takes them all, the mapping editor shows the first only
            log.warning("controller '%s' has %d shift buttons: the app shows only the first, %s %d", self.name, len(shifts), shifts[0].type, shifts[0].number)
        return self

    @model_validator(mode="before")
    @classmethod
    def _legacy_pages(cls, data: Any) -> Any:
        # before 1.5: ``mappings`` active on every page, ``pages`` {page: mappings}, and ``page_knob``, the CC of a
        # knob that switched pages (no longer there: pages are switched with the Page macros, or in the app)
        if not isinstance(data, dict) or not ({"pages", "page_knob"} & data.keys() or any(isinstance(m, dict) and m.get("mode") == "page_knob" for m in data.get("mappings") or [])):
            return data
        data = dict(data)
        data.pop("page_knob", None)
        mappings = [m for m in data.get("mappings") or [] if not (isinstance(m, dict) and m.get("mode") == "page_knob")]
        for page, items in (data.pop("pages", None) or {}).items():
            for item in items:
                item = dict(item) if isinstance(item, dict) else item.model_dump(exclude_defaults=True)
                if item.get("mode") == "page_knob":
                    continue
                item.setdefault("page", page)
                mappings.append(item)
        data["mappings"] = mappings
        return data


# --------------------------------------------------------------------------- scenes


class Scene(Model):
    name: str = ""
    values: dict[str, float] = Field(default_factory=dict)  # macro name -> control value (0..1)

    @field_validator("values", mode="before")
    @classmethod
    def _renamed_macros(cls, v: Any) -> Any:
        return current_macro_names(v) if isinstance(v, dict) else v
