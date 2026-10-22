"""The built-in fixture library (item 50): the OFL conversion (tools/ofl_convert.py) on a small fixture, and the ten
shipped types checked against their manuals (the channel tables below are typed from the manual records in the
PitchPlease wiki, ``raw/2026-10-21_<slug>-manual.md``, not copied from the generated files)."""

import sys
from pathlib import Path

import pytest
from conftest import SHIPPED_CONFIG

from pitchcontrol.config.loader import ConfigStore
from pitchcontrol.config.models import ChannelMode, FixtureInstance, Rig



from pitchcontrol.ofl.convert import convert_fixture

# --------------------------------------------------------------------------- the conversion

# A made-up OFL fixture with everything the mapping has to handle: a master dimmer (with its fine channel), a strobe
# whose "open" range comes twice, a colour preset, a switching channel, amber, and a matrix of two segments.
OFL = {
    "name": "Test Bar",
    "shortName": "TestBar",
    "categories": ["Pixel Bar"],
    "matrix": {"pixelCount": [2, 1, 1]},
    "availableChannels": {
        "Dimmer": {"fineChannelAliases": ["Dimmer fine"], "capability": {"type": "Intensity"}},
        "Strobe": {
            "capabilities": [
                {"dmxRange": [0, 5], "type": "ShutterStrobe", "shutterEffect": "Open"},
                {"dmxRange": [6, 100], "type": "ShutterStrobe", "shutterEffect": "Strobe", "randomTiming": True, "speedStart": "slow", "speedEnd": "fast"},
                {"dmxRange": [101, 250], "type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": "1Hz", "speedEnd": "20Hz"},
                {"dmxRange": [251, 255], "type": "ShutterStrobe", "shutterEffect": "Open"},
            ]
        },
        "Colors": {
            "capabilities": [
                {"dmxRange": [0, 9], "type": "NoFunction"},
                {"dmxRange": [10, 19], "type": "ColorPreset", "comment": "Red"},
                {"dmxRange": [20, 29], "type": "ColorPreset", "comment": "White"},
            ]
        },
        "Amber": {"capability": {"type": "ColorIntensity", "color": "Amber"}},
        "Function": {
            "defaultValue": 0,
            "capabilities": [
                {"dmxRange": [0, 9], "type": "NoFunction", "switchChannels": {"Red / Speed": "Red"}},
                {"dmxRange": [10, 255], "type": "Effect", "effectName": "Show", "switchChannels": {"Red / Speed": "Speed"}},
            ],
        },
        "Red": {"capability": {"type": "ColorIntensity", "color": "Red"}},
        "Speed": {"capability": {"type": "EffectSpeed", "speedStart": "slow", "speedEnd": "fast"}},
        "Green": {"capability": {"type": "ColorIntensity", "color": "Green"}},
        "Blue": {"capability": {"type": "ColorIntensity", "color": "Blue"}},
        "Warm White": {"capability": {"type": "ColorIntensity", "color": "Warm White"}},
    },
    "templateChannels": {
        "Red $pixelKey": {"capability": {"type": "ColorIntensity", "color": "Red"}},
        "Green $pixelKey": {"capability": {"type": "ColorIntensity", "color": "Green"}},
        "Blue $pixelKey": {"capability": {"type": "ColorIntensity", "color": "Blue"}},
    },
    "modes": [
        {"name": "4-channel", "shortName": "4ch", "channels": ["Dimmer", "Strobe", "Colors", "Function"]},
        {"name": "7-channel", "shortName": "7ch", "channels": ["Dimmer", "Dimmer fine", "Strobe", "Function", "Red / Speed", "Green", "Blue", "Warm White", "Amber"]},
        {
            "name": "Pixel mode",
            "shortName": "pix",
            "channels": [
                "Dimmer",
                {"insert": "matrixChannels", "repeatFor": "eachPixelABC", "channelOrder": "perPixel", "templateChannels": ["Red $pixelKey", "Green $pixelKey", "Blue $pixelKey"]},
                "Strobe",
            ],
        },
        {"name": "Per pixel dimmer", "shortName": "ppd", "channels": [{"insert": "matrixChannels", "repeatFor": ["1", "2"], "channelOrder": "perPixel", "templateChannels": ["Dimmer", "Red $pixelKey"]}]},
    ],
}

SHUTTER = {"open": 0, "strobo": 250}  # the plain strobe ends at 250: 251..255 is "open" again

EXPECTED_MODES = [
    {
        "id": "4ch",
        "name": "4CH",
        "description": "Dimmer (follows the brightness), Strobe, Colors (held at 25), Function (off). No colour mixing in this mode: only the brightness follows PitchControl.",
        "pixels": 1,
        "channels": [
            {"name": "Dimmer", "pixels": "I"},
            {"name": "Strobe", "shutter": SHUTTER},
            {"name": "Colors", "value": 25},  # the middle of the White preset, 20..29: no colour mixing without it
            {"name": "Function", "value": 0},
        ],
    },
    {
        "id": "7ch",
        "name": "7CH",
        "description": "Dimmer (held at full), Dimmer fine (off), Strobe, Function (off), RGBW, Amber (off).",
        "pixels": 1,
        "channels": [
            {"name": "Dimmer", "value": 255},  # the colours carry the brightness
            {"name": "Dimmer fine", "value": 0},
            {"name": "Strobe", "shutter": SHUTTER},
            {"name": "Function", "value": 0},
            {"pixels": "RGBW"},  # "Red / Speed" is Red with Function at its default 0; the warm white is the W
            {"name": "Amber", "value": 0},
        ],
    },
    {
        "id": "pixel-mode",
        "name": "Pixel mode",
        "description": "Dimmer (held at full), 2 × RGB, Strobe.",
        "pixels": 2,
        "channels": [{"name": "Dimmer", "value": 255}, {"pixels": "RGB"}, {"name": "Strobe", "shutter": SHUTTER}],
    },
]


def test_the_ofl_fixture_converts_mode_by_mode():
    result = convert_fixture(OFL)
    got = {m["id"]: m for m in result.modes}
    assert list(got) == ["4ch", "7ch", "pixel-mode"]
    for expected in EXPECTED_MODES:
        mode = got[expected["id"]]
        assert mode["channels"] == expected["channels"], expected["id"]
        assert mode["pixels"] == expected["pixels"] and mode["name"] == expected["name"]
    assert got["7ch"]["description"] == EXPECTED_MODES[1]["description"]
    assert got["pixel-mode"]["description"] == EXPECTED_MODES[2]["description"]


def test_a_mode_that_cant_be_expressed_is_listed_with_its_reason_not_converted():
    (name, why), = convert_fixture(OFL).skipped
    assert name == "Per pixel dimmer" and "per-pixel block" in why


def test_skipped_on_purpose_and_the_report_of_assumptions():
    result = convert_fixture(OFL, skip={"4-channel": "not wanted"})
    assert [m["id"] for m in result.modes] == ["7ch", "pixel-mode"]
    assert ("4-channel", "not wanted") in result.skipped
    data = {**OFL, "availableChannels": {**OFL["availableChannels"], "Strobe": {"capability": {"type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": "slow", "speedEnd": "fast"}}}}
    assert convert_fixture(data).assumptions == ["Strobe: OFL has no open range, open = 0"] * 3  # one per mode that has it


def test_an_open_range_that_does_not_start_at_zero_is_read_in_its_middle():
    data = {
        "name": "ADJ like",
        "modes": [{"name": "1-channel", "shortName": "1ch", "channels": ["Strobe"]}],
        "availableChannels": {
            "Strobe": {
                "capabilities": [
                    {"dmxRange": [0, 31], "type": "ShutterStrobe", "shutterEffect": "Closed"},
                    {"dmxRange": [32, 63], "type": "ShutterStrobe", "shutterEffect": "Open"},
                    {"dmxRange": [64, 95], "type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": "slow", "speedEnd": "fast"},
                ]
            }
        },
    }
    assert convert_fixture(data).modes[0]["channels"] == [{"name": "Strobe", "shutter": {"open": 48, "strobo": 95}}]


# --------------------------------------------------------------------------- the shipped types against the manuals

# One letter per DMX channel, from the manual's channel table: R G B W colours (a pixel block repeats them per
# pixel), D dimmer, F dimmer fine, S strobe (a strobe channel that works), s a strobe channel that does nothing in
# that mode, A amber, U UV, L delay (or fader response), x anything else (mode, program, speed, sound, preset...).
# Per type and mode: (pixels, letters).
MANUAL = {
    "Stairville LED Flood Panel 150": {  # 253359 manual, German, pp. 7 to 9
        "3CH": (1, "RGB"),
        "4CH": (1, "DRGB"),
        "8CH": (1, "DRGBSxxL"),
    },
    "Stairville LED Bar 240-8": {  # Thomann 294835, pp. 33 to 38 (the Varytec Giga Bar Pix 8 has the same four tables)
        "2CH": (1, "xx"),
        "3CH": (1, "RGB"),
        "5CH": (1, "RGBDS"),
        "24CH": (8, "RGB" * 8),
    },
    "Stairville xBrick Quad 16x8W RGBW": {  # Thomann 385641, pp. 38 to 46
        "4CH": (1, "RGBW"),
        "6CH": (1, "RGBWDS"),
        "8CH": (1, "RGBWDsxx"),
        "16CH": (4, "RGBW" * 4),
        "18CH": (4, "RGBW" * 4 + "DS"),
    },
    "Stairville SonicPulse LED Bar 10": {  # Thomann 580867 / 580868 (V2)
        "4CH": (1, "RGBW"),
        "5CH": (1, "Dxxxx"),
        "6CH": (1, "DSRGBW"),
        "11CH": (1, "DSxxxxxRGBW"),
        "39CH": (8, "DSxxxxx" + "RGBW" * 8),
    },
    "Eurolite LED PT-100-32 Pixel DMX Tube": {  # 00126295 v1.0
        "3CH": (1, "RGB"),
        "5CH": (1, "RGBDS"),
        "8CH": (1, "DSRGBxxx"),
        "48CH": (16, "RGB" * 16),
        "96CH": (32, "RGB" * 32),
    },
    "Ape Labs Neon Tube PIX": {  # manual of 2026-10-15, section 7
        "4CH": (1, "RGBW"),
        "7CH": (1, "RGBWDSx"),
        "32CH": (8, "RGBW" * 8),
        "64CH": (16, "RGBW" * 16),
        "128CH": (32, "RGBW" * 32),
    },
    "Cameo ROOT Par 6": {  # revision 04, DMX pages 168 to 174: 14 modes
        "2CH": (1, "Dx"),
        "D3CH": (1, "DxL"),
        "4CH1": (1, "DSxx"),
        "D5CH1": (1, "DSxxL"),
        "4CH2": (1, "RGBW"),
        "D5CH2": (1, "RGBWL"),
        "5CH": (1, "DSxxx"),
        "D6CH": (1, "DSxxxL"),  # the 5CH layout plus delay, not the 6CH colour mode
        "6CH": (1, "RGBWAU"),
        "D7CH": (1, "RGBWAUL"),
        "8CH": (1, "DSRGBWAU"),
        "D9CH": (1, "DSRGBWAUL"),
        "11CH": (1, "DFSRGBWAUxx"),
        "D12CH": (1, "DFSRGBWAUxxL"),
    },
    "Cameo Q-Spot 40": {  # REV 03, English tables on pp. 75 to 77; the mode names as the display prints them (p. 6)
        "02CH": (1, "Dx"),
        "03CH1": (1, "DSx"),
        "03CH2": (1, "RGB"),
        "04CH": (1, "RGBW"),
        "09CH": (1, "DFSRGBWxx"),
    },
    "Stairville BTL-30": {  # Thomann 361459
        "7CH": (1, "DRGBWxx"),
    },
    "Astera FP1 Titan Tube": {  # the manual's profile tables that people use, by number (pixels, letters of the table)
        "1: RGB": (1, "RGB"),
        "4: Dim RGB": (1, "DRGB"),
        "5: Dim RGBW": (1, "DRGBW"),
        "18: RGB RGB 4pix": (4, "RGB" * 4),
        "19: RGBW RGBW 4pix": (4, "RGBW" * 4),
        "42: RGB RGB 16pix": (16, "RGB" * 16),
        "43: RGBW RGBW 16pix": (16, "RGBW" * 16),
    },
}

# The default mode of every type (the "Mode to ship" of the candidates page)
DEFAULTS = {
    "Stairville LED Flood Panel 150": "4CH",
    "Stairville LED Bar 240-8": "24CH",
    "Stairville xBrick Quad 16x8W RGBW": "18CH",
    "Stairville SonicPulse LED Bar 10": "39CH",
    "Eurolite LED PT-100-32 Pixel DMX Tube": "96CH",
    "Ape Labs Neon Tube PIX": "128CH",
    "Astera FP1 Titan Tube": "42: RGB RGB 16pix",
    "Cameo ROOT Par 6": "8CH",
    "Cameo Q-Spot 40": "04CH",
    "Stairville BTL-30": "7CH",
}

# Values the manuals give: a constant's "no function / colour mixing" value, a strobe's open and fastest values
MANUAL_VALUES = [
    # (type, mode, channel, value or (open, strobo))
    ("Stairville LED Flood Panel 150", "8CH", "Strobe", (0, 255)),  # 0..9 none, 10..255 slow to fast
    ("Stairville LED Flood Panel 150", "8CH", "Internal Programs", 0),  # mode 0 = the RGB mix of channels 2 to 4
    ("Stairville LED Flood Panel 150", "8CH", "ID Select", 0),  # 0..9 all IDs
    ("Stairville LED Flood Panel 150", "8CH", "Dimmer Delay", 0),  # 0..250 fast fader response
    ("Stairville LED Bar 240-8", "5CH", "Strobe", (0, 255)),  # 0..255 increasing speed, no "off" printed
    ("Stairville xBrick Quad 16x8W RGBW", "6CH", "Strobe", (0, 255)),
    ("Stairville xBrick Quad 16x8W RGBW", "18CH", "Strobe", (0, 255)),
    ("Stairville xBrick Quad 16x8W RGBW", "8CH", "Function select", 0),  # 0..4 no function: the RGBW mix works
    ("Stairville SonicPulse LED Bar 10", "6CH", "Shutter / Strobe", (0, 255)),  # 0..10 none, 11..255
    ("Stairville SonicPulse LED Bar 10", "39CH", "Shutter / Strobe", (0, 255)),
    ("Stairville SonicPulse LED Bar 10", "39CH", "Mode Selection", 0),  # 0..63 RGBW colour change
    ("Eurolite LED PT-100-32 Pixel DMX Tube", "5CH", "Function", (0, 255)),  # 0 none, 11..255 strobe
    ("Eurolite LED PT-100-32 Pixel DMX Tube", "8CH", "Strobe", (0, 255)),  # 0..9 none
    ("Eurolite LED PT-100-32 Pixel DMX Tube", "8CH", "Preset Colours", 0),
    ("Eurolite LED PT-100-32 Pixel DMX Tube", "8CH", "Internal Programs", 0),
    ("Ape Labs Neon Tube PIX", "7CH", "Speed / Strobe", (0, 255)),  # 0 off, 1..255 slow to fast
    ("Ape Labs Neon Tube PIX", "7CH", "Music Mode", 0),  # 0..124 off
    ("Cameo ROOT Par 6", "8CH", "Strobe", (0, 255)),  # 0..5 open, 6..255 slow to fast
    ("Cameo ROOT Par 6", "5CH", "Strobe", (0, 255)),
    ("Cameo ROOT Par 6", "D6CH", "Strobe", (0, 255)),
    ("Cameo ROOT Par 6", "D9CH", "Strobe", (0, 255)),
    ("Cameo ROOT Par 6", "4CH1", "Strobe Multifunctional", (0, 250)),  # 128..250 is the fastest; 251..255 is open again
    ("Cameo ROOT Par 6", "11CH", "Strobe Multifunctional", (0, 250)),
    ("Cameo ROOT Par 6", "D12CH", "Strobe Multifunctional", (0, 250)),
    ("Cameo ROOT Par 6", "11CH", "Color Preset", 0),  # 0..5 colour off: anything above overrides the mix
    ("Cameo ROOT Par 6", "11CH", "Sound Control", 0),  # 0..5 off
    ("Cameo ROOT Par 6", "2CH", "Color Preset", 114),  # the only colour of the mode: white (110..117)
    ("Cameo ROOT Par 6", "D12CH", "DMX Delay", 0),  # 0..5 no delay
    ("Cameo Q-Spot 40", "03CH1", "Strobe", (0, 255)),  # 0..5 open, 6..255 slow to fast
    ("Cameo Q-Spot 40", "09CH", "Strobe functions", (0, 250)),  # 128..250 slow to fast, 251..255 open again
    ("Cameo Q-Spot 40", "09CH", "Color Macros", 0),  # 0..5 off: above overrides RGBW
    ("Cameo Q-Spot 40", "09CH", "Color Temperature", 0),  # 0..5 off: colours unchanged
    ("Cameo Q-Spot 40", "02CH", "Color Macros", 114),  # white
    ("Stairville BTL-30", "7CH", "Program", 0),  # 0..50: the colour channels act
]


def letters(mode: ChannelMode) -> str:
    out = []
    for slot in mode.channels:
        if slot.pixels == "I":
            out.append("D")
        elif slot.pixels:
            out.append(slot.pixels * mode.pixels)
        elif slot.shutter:
            out.append("S")
        else:
            name = (slot.name or "").lower()
            out.append(
                "F" if "fine" in name else "L" if "delay" in name else "D" if "dimmer" in name else "s" if "strobe" in name
                else "A" if "amber" in name else "U" if name == "uv" else "W" if "white" in name else "x"
            )
    return "".join(out)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    store = ConfigStore(tmp_path_factory.mktemp("user"), defaults=SHIPPED_CONFIG, machine=tmp_path_factory.mktemp("machine"))
    store.load_all()
    assert store.notices == []
    return store


def test_all_ten_types_load_with_their_default_mode(library):
    for name, default in DEFAULTS.items():
        ftype = library.fixture_types[name]
        assert ftype.mode_of(None).name == default, name
        assert "Open Fixture Library" in ftype.description or "Built from the manual" in ftype.description, name


@pytest.mark.parametrize("name", sorted(MANUAL))
def test_modes_channel_counts_order_and_pixels_match_the_manual(library, name):
    ftype = library.fixture_types[name]
    modes = {m.name: m for m in ftype.modes}
    assert set(modes) == set(MANUAL[name]), f"{name}: modes {sorted(modes)}"
    for mode_name, (pixels, expected) in MANUAL[name].items():
        mode = modes[mode_name]
        assert mode.pixels == pixels, f"{name} {mode_name}: pixels"
        assert letters(mode) == expected, f"{name} {mode_name}: channel order"
        assert mode.channel_count() == len(expected), f"{name} {mode_name}: channel count"


@pytest.mark.parametrize("name,mode_name,channel,expected", MANUAL_VALUES)
def test_constants_and_shutter_values_match_the_manual(library, name, mode_name, channel, expected):
    mode = next(m for m in library.fixture_types[name].modes if m.name == mode_name)
    slot = next(s for s in mode.channels if s.name == channel)
    got = (slot.shutter.open, slot.shutter.strobo) if slot.shutter else slot.value
    assert got == expected


def test_the_master_dimmer_is_held_at_full_when_the_mode_mixes_colours_and_follows_the_brightness_when_not(library):
    for ftype in library.fixture_types.values():
        for mode in ftype.modes:
            if not any(s.pixels in ("RGB", "RGBW") for s in mode.channels):
                continue
            for slot in mode.channels:
                if slot.name and slot.name.lower().startswith("dimmer") and "fine" not in slot.name.lower() and "delay" not in slot.name.lower():
                    assert slot.value in (255, 0) and slot.pixels is None, f"{ftype} {mode.name}"  # 0: a dimmer that does nothing in this function


def test_both_q_spot_types_name_their_modes_as_the_display_prints_them(library):
    """02CH, 03CH1, 03CH2, 04CH, 09CH (Q-Spot 15 manual p. 15, Q-Spot 40 manual p. 6). The ids are what rigs store: they stay."""
    q15, q40 = library.fixture_types["Cameo Q-Spot 15"], library.fixture_types["Cameo Q-Spot 40"]
    assert [m.name for m in q15.modes] == ["02CH", "03CH1", "03CH2", "04CH", "09CH"]
    assert [(m.id, m.name) for m in q15.modes] == [(m.id, m.name) for m in q40.modes]
    assert [m.id for m in q15.modes] == ["2ch", "3ch-1", "3ch-2", "4ch", "9ch"] and q15.default_mode == q40.default_mode == "4ch"
    assert q15.mode_of("3ch-2").name == "03CH2"


def test_a_rig_with_one_of_each_has_no_problems(library):
    """Each fixture in its default mode, one after the other on universe 0, and again each in its biggest mode."""
    for biggest in (False, True):
        fixtures, address = [], 1
        for name in DEFAULTS:
            ftype = library.fixture_types[name]
            mode = max(ftype.modes, key=lambda m: m.channel_count()) if biggest else None
            fixtures.append(FixtureInstance(name=name, type=name, address=address, mode=mode.id if mode else None))
            address += ftype.channel_count(mode.id if mode else None)
        library.rig = Rig(name="library", fixtures=fixtures)
        assert library.validate_rig() == []
        if not biggest:
            assert address - 1 == 4 + 24 + 18 + 39 + 96 + 128 + 48 + 8 + 4 + 7
