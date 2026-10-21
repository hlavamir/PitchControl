"""Generate PitchControl's built-in fixture library (``config/fixtures/types/``) from the Open Fixture Library.

    python tools/fixture_library.py                  # download at the pinned commit, write the types and the notice
    python tools/fixture_library.py --cache DIR      # keep the downloaded OFL files in DIR (default tools/.ofl-cache)

The fixture list, the OFL commit it is pinned to and the corrections that come from the manuals are in this file; the
mapping from OFL's format is in ``ofl_convert.py``. A fixture that isn't in OFL is written by hand in OFL's format
from its manual (``tools/fixture_sources/``) and goes through the same conversion. Run it again to add a fixture or
move to a newer OFL commit: change ``OFL_COMMIT`` (and read the report, OFL's files are community-written), then
run ``tools/shipped_config_history.py`` once the files are committed (see "Releasing a version" in the README).

OFL is MIT licensed (https://github.com/OpenLightingProject/open-fixture-library, LICENSE): the notice is shipped in
``config/fixtures/Open Fixture Library notice.txt`` and each type's description names it as the source.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ofl_convert import Converted, convert_fixture  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "config" / "fixtures" / "types"
NOTICE = ROOT / "config" / "fixtures" / "Open Fixture Library notice.txt"
SOURCES = Path(__file__).resolve().parent / "fixture_sources"

OFL_REPO = "OpenLightingProject/open-fixture-library"
OFL_COMMIT = "d9d675eb686932a60f815301b8361b7d63b4e814"  # master on 2026-10-21

NOTICE_TEXT = """\
The fixture types in this folder whose description names the Open Fixture Library were generated from fixture
definitions of the Open Fixture Library (https://open-fixture-library.org, https://github.com/{repo}),
at commit {commit}, and checked against the manufacturers' manuals.

The Open Fixture Library is licensed under the MIT License:

MIT License

Copyright (c) 2017 Florian & Felix Edelmann

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


@dataclass
class Correction:
    """A value the manual gives differently from OFL (or that OFL lacks): the manual wins."""

    mode: str  # the PitchControl mode name, e.g. "8CH"
    channel: str  # the channel's name in that mode
    reason: str
    value: int | None = None
    shutter: dict | None = None


@dataclass
class LibraryFixture:
    name: str  # the type's name (its file name)
    intro: str  # the first sentences of the description
    default: str  # the mode a new fixture starts in (PitchControl mode name)
    ofl: str | None = None  # "maker/fixture" in OFL; None = built from the manual (tools/fixture_sources/)
    source_file: str = ""  # tools/fixture_sources/<this>.json when ofl is None
    manual: str = ""  # the manual's record in the PitchPlease wiki (docs/raw/2026-10-21_<this>-manual.md)
    skip: dict[str, str] = field(default_factory=dict)  # OFL mode name -> why it is left out
    corrections: list[Correction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what the manual leaves open, kept in the type's _note
    keep: list[str] = field(default_factory=list)  # only these OFL modes, by the number before the colon in their name (the rest are left out as little used)
    renames: dict[str, tuple[str, str]] = field(default_factory=dict)  # converted mode name -> (name, id) as the manual / a sibling type has it


LIBRARY: list[LibraryFixture] = [
    LibraryFixture(
        name="Stairville LED Flood Panel 150",
        intro="Stairville LED Flood Panel 150 (150 LEDs of 10 mm, red, green and blue, one colour for the whole panel; the 20° and 40° versions).",
        default="4CH",
        ofl="stairville/led-flood-panel-150",
        manual="stairville-led-flood-panel-150",
    ),
    LibraryFixture(
        name="Stairville LED Bar 240-8",
        intro=(
            "Stairville LED Bar 240/8 RGB (240 LEDs in 8 segments), also the Varytec Giga Bar Pix 8 RGB and Giga Bar Frost Pix 8 RGB "
            "(144 SMD LEDs in 8 segments; the same four modes and the same channel tables)."
        ),
        default="24CH",
        ofl="stairville/led-bar-240-8",
        manual="stairville-led-bar-240-8-rgb",
        corrections=[
            Correction(
                "5CH", "Strobe", "the manual prints 0..255 as strobe, increasing speed, with no open range (OFL says 0..2 open); open stays 0",
                shutter={"open": 0, "strobo": 255},
            )
        ],
    ),
    LibraryFixture(
        name="Stairville xBrick Quad 16x8W RGBW",
        intro="Stairville xBrick Quad 16x8W RGBW (16 quad-colour LEDs in 4 segments).",
        default="18CH",
        ofl="stairville/xbrick-quad-16x8w-rgbw",
        manual="stairville-xbrick-quad-16x8w-rgbw",
        corrections=[
            Correction("6CH", "Strobe", "the manual prints 0 % to 100 % with no open range and OFL has none either; open = 0 is an assumption", shutter={"open": 0, "strobo": 255}),
            Correction("18CH", "Strobe", "as 6CH: no open range in the manual or in OFL; open = 0 is an assumption", shutter={"open": 0, "strobo": 255}),
        ],
        notes=["in 8CH the RGBW channels only work with the function select at 0..4, dimmer and strobe only above 4, so the mode has no brightness control"],
    ),
    LibraryFixture(
        name="Stairville SonicPulse LED Bar 10",
        intro=(
            "Stairville SonicPulse LED Bar 10 (8 RGBW segments of 3 LEDs). The Bar 05 is the same with 4 segments: "
            "its 4, 5, 6 and 11CH modes are these, its 23CH mode is the 7 header channels and 4 RGBW segments."
        ),
        default="39CH",
        ofl="stairville/sonicpulse-led-bar-10",
        manual="stairville-sonicpulse-led-bar-05-10",
        notes=["that the Mode Selection at 0..63 (RGBW colour change) lets the RGBW channels act is inferred from the manual, not verified on a unit"],
    ),
    LibraryFixture(
        name="Eurolite LED PT-100-32 Pixel DMX Tube",
        intro="Eurolite LED PT-100/32 Pixel DMX Tube (32 RGB pixels of 3 LEDs). In the 48CH mode two neighbouring pixels share one colour, so that mode has 16 pixels.",
        default="96CH",
        source_file="eurolite__led-pt-100-32",
        manual="eurolite-led-pt-100-32",
        notes=[
            "the manual gives no priority between the 8CH preset colour / program channels and RGB (they are held at 0, no function)",
            "pixel 1 is at the DMX-input end only by assumption",
        ],
    ),
    LibraryFixture(
        name="Ape Labs Neon Tube PIX",
        intro=(
            "Ape Labs Neon Tube PIX (battery pixel tube, 32 pixels of red, green, blue and warm white, which is the W of the RGBW block). "
            "DMX comes through its built-in CRMX receiver or an Ape Labs CONNECT. The 32CH and 64CH modes have 8 and 16 pixels."
        ),
        default="128CH",
        source_file="ape-labs__neon-tube-pix",
        manual="ape-labs-neon-tube-pix",
        notes=["how the 8 and 16 pixels of the 32CH and 64CH modes sit on the 32 physical pixels is not in the manual (not verified on a unit)"],
    ),
    LibraryFixture(
        name="Astera FP1 Titan Tube",
        intro=(
            "Astera FP1 Titan Tube (battery pixel tube, 16 pixels). The modes are the manual's DMX profile tables that people use, named with the table "
            "number, which is set on the tube under DMX TABLE: 1 (RGB), 4 (dimmer, RGB), 5 (dimmer, RGBW), 18 and 19 (RGB and RGBW on 4 pixels), 42 and 43 (RGB and RGBW on 16 pixels). "
            "The white of the RGBW tables is the tube's emulated white."
        ),
        default="42: RGB RGB 16pix",
        ofl="astera/fp1-titan-tube",
        manual="astera-fp1-titan-tube",
        keep=["1", "4", "5", "18", "19", "42", "43"],
        notes=["the manual does not say how many LEDs one pixel of the 4-pixel tables has", "on battery the tube dims itself to meet its set runtime, a DMX show may be dimmer than on AC"],
        skip={
            "15: Effect Fix": "the effect tables: the colours are effect colours, not pixels",
            "16: Effect RGB": "the effect tables: the colours are effect colours, not pixels",
            "89: D CCT GM CRO RGB": "a table of OFL that is not among the manual's 64 profile tables",
            "90: D CCT GM HUE SAT": "a table of OFL that is not among the manual's 64 profile tables",
            "91: D16 CCT GM CRO RGB": "a table of OFL that is not among the manual's 64 profile tables",
            "92: D16 CCT GM H SAT": "a table of OFL that is not among the manual's 64 profile tables",
        },
    ),
    LibraryFixture(
        name="Cameo ROOT Par 6",
        intro=(
            "Cameo ROOT Par 6 (6 × 12 W RGBWA+UV). The modes with a D are the same layout plus a trailing DMX delay channel, held off "
            "(D6CH is the 5CH layout plus delay, not the 6CH colour mode); amber and UV are held off, the colours are mixed from R, G, B and W."
        ),
        default="8CH",
        ofl="cameo/root-par-6",
        manual="cameo-root-par-4-6",
    ),
    LibraryFixture(
        name="Cameo Q-Spot 40",
        intro=(
            "Cameo Q-Spot 40 RGBW (40 W RGBW pinspot). The same five modes as the Q-Spot 15, named as the display and the manual print them "
            "(Q-Spot 40 manual p. 6, Q-Spot 15 manual p. 15); 03CH1 and 03CH2 are different layouts."
        ),
        default="04CH",
        ofl="cameo/q-spot-40-rgbw",
        manual="cameo-q-spot-40-rgbw",
        renames={"2CH": ("02CH", "2ch"), "3CH1": ("03CH1", "3ch-1"), "3CH2": ("03CH2", "3ch-2"), "4CH": ("04CH", "4ch"), "9CH": ("09CH", "9ch")},
    ),
    LibraryFixture(
        name="Stairville BTL-30",
        intro="Stairville BTL-30 Battery Truss Light (3 LEDs of 10 W, red, green, blue and white; one 7CH mode; no wireless DMX).",
        default="7CH",
        source_file="stairville__btl-30",
        manual="stairville-btl-30",
        notes=["Program (channel 6) must stay at 0..50 for the colour channels to act; the manual lists a strobe effect there but not how it is triggered, so there is no strobe channel"],
    ),
]


# --------------------------------------------------------------------------- building


def fetch(ofl: str, cache: Path) -> dict:
    """The OFL fixture file at the pinned commit (cached by commit, maker and fixture)."""
    path = cache / OFL_COMMIT / (ofl.replace("/", "__") + ".json")
    if not path.exists():
        url = f"https://raw.githubusercontent.com/{OFL_REPO}/{OFL_COMMIT}/fixtures/{ofl}.json"
        print(f"  fetching {url}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text(encoding="utf-8"))


def source_sentence(fx: LibraryFixture) -> str:
    if fx.ofl:
        return f"Generated from the Open Fixture Library (MIT licence, {fx.ofl} at commit {OFL_COMMIT[:7]}) and checked against the manual."
    return "Built from the manual (this fixture is not in the Open Fixture Library) with the same conversion as the Open Fixture Library types."


def short_reason(why: str) -> str:
    if why.startswith("a per-pixel block"):
        return "a dimmer, amber, CCT or strobe per pixel, which PitchControl can't repeat"
    if "leaves out (null)" in why:
        return "an empty gap channel between the pixels"
    if why.startswith("pixel colours"):
        return "amber next to RGB on every pixel"
    return why


def skipped_by_reason(converted: Converted) -> dict[str, list[str]]:
    """The modes that are not in the type, grouped by why (a table's number when the name starts with one)."""
    out: dict[str, list[str]] = {}
    for name, why in converted.skipped:
        out.setdefault(short_reason(why), []).append(name.split(":")[0] if name.split(":")[0].isdigit() else name)
    return out


def build_type(fx: LibraryFixture, data: dict) -> tuple[dict, Converted, list[str]]:
    """The type file's content, the conversion report and the corrections that were applied."""
    skip = dict(fx.skip)
    if fx.keep:
        skip.update({m["name"]: "not shipped: little used, or PitchControl can't express them" for m in data["modes"] if m["name"].split(":")[0] not in fx.keep and m["name"] not in skip})
    converted = convert_fixture(data, skip)
    modes = converted.modes
    by_name = {m["name"]: m for m in modes}
    applied = []
    for fix in fx.corrections:
        mode = by_name[fix.mode]
        slot = next(s for s in mode["channels"] if s.get("name") == fix.channel)
        if fix.value is not None:
            slot.pop("shutter", None)
            slot["value"] = fix.value
        if fix.shutter is not None:
            slot["shutter"] = fix.shutter
        applied.append(f"{fix.mode} {fix.channel}: {fix.reason}")
    for old, (new_name, new_id) in fx.renames.items():
        by_name[old].update(name=new_name, id=new_id)
        by_name[new_name] = by_name.pop(old)
    if fx.default not in by_name:
        raise SystemExit(f"{fx.name}: default mode '{fx.default}' is not among {list(by_name)}")
    names = ", ".join(m["name"] for m in modes)
    description = f"{fx.intro} Modes: {names}; {fx.default} is the default. {source_sentence(fx)}"
    note = "Generated by tools/fixture_library.py (item 50)."
    if applied:
        note += " Corrections from the manual: " + "; ".join(applied) + "."
    if converted.skipped:
        note += " Left out: " + "; ".join(f"{why}: {', '.join(names)}" for why, names in skipped_by_reason(converted).items()) + "."
    if fx.notes:
        note += " Not in the manual or not verified: " + "; ".join(fx.notes) + "."
    ftype = {
        "description": description,
        "transport": "dmx",
        "modes": modes,
        "default_mode": by_name[fx.default]["id"],
        "gamma": 1.0,
        "strobo_color": {"h": 0.0, "s": 0.0, "b": 1.0},
        "_note": note,
    }
    return ftype, converted, applied


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", type=Path, default=Path(__file__).resolve().parent / ".ofl-cache")
    args = parser.parse_args()

    for fx in LIBRARY:
        data = fetch(fx.ofl, args.cache) if fx.ofl else json.loads((SOURCES / f"{fx.source_file}.json").read_text(encoding="utf-8"))
        ftype, converted, applied = build_type(fx, data)
        write_json(TYPES / f"{fx.name}.json", ftype)
        print(f"{fx.name}: {len(converted.modes)} modes ({', '.join(m['name'] for m in converted.modes)}), default {fx.default}")
        for why, names in skipped_by_reason(converted).items():
            print(f"    left out ({len(names)}): {why}: {', '.join(names)}")
        for note in converted.assumptions + applied:
            print(f"    note: {note}")
    NOTICE.write_text(NOTICE_TEXT.format(repo=OFL_REPO, commit=OFL_COMMIT), encoding="utf-8", newline="\n")
    print(f"wrote {len(LIBRARY)} types to {TYPES} and the notice to {NOTICE}")


if __name__ == "__main__":
    main()
