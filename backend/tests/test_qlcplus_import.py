"""Import from QLC+ (item 54): a ``.qxf`` is read into OFL's model, then goes through item 53's converter, report and kept
data. The four definitions in ``tests/qlcplus/`` were written for these tests (in QLC+'s file format; none is a copy of a
QLC+ fixture file: the licence of QLC+'s fixture files is not stated per file, so none ships with PitchControl).
The shape being tested is documented in ``pitchcontrol/ofl/importer.py`` and ``pitchcontrol/ofl/qlcplus.py``."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pitchcontrol.config.models import FixtureType, NetworkSettings
from pitchcontrol.engine.engine import Engine
from pitchcontrol.ofl import qlcplus_files
from pitchcontrol.ofl.importer import CONVERTER_VERSION, ImportProblem, rebuild_ofl
from pitchcontrol.ofl.qlcplus import import_qxf, qxf_to_ofl, template_split
from pitchcontrol.server.app import create_app

FILES = Path(__file__).parent / "qlcplus"
PAR, BAR, SPOT, DIMMER = (FILES / f"Test-Lights-{n}.qxf" for n in ("RGB-PAR", "RGBW-Bar", "Spot-16bit", "Dimmer-Pack"))
TODAY = "2026-10-22"
PHONE = ("192.168.1.50", 50000)


def imported(path: Path):
    return import_qxf(path.read_bytes(), file=path.name, today=TODAY)


def modes(path: Path) -> dict[str, dict]:
    return {m["name"]: m for m in imported(path).ftype["modes"]}


def slots(mode: dict) -> list[tuple]:
    """A mode's channels as (name or pixel format, value, shutter) for comparing with the file."""
    return [(s.get("name"), s.get("pixels") or s.get("value") or s.get("shutter")) for s in mode["channels"]]


def qxf(channels: str, modes: str, kind: str = "Color Changer") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE FixtureDefinition>
<FixtureDefinition xmlns="http://www.qlcplus.org/FixtureDefinition">
 <Creator><Name>Q Light Controller Plus</Name><Version>4.12.2</Version><Author>t</Author></Creator>
 <Manufacturer>M</Manufacturer><Model>X</Model><Type>{kind}</Type>
{channels}
{modes}
</FixtureDefinition>"""


def colour_channels(n: int, names: str = "RGB") -> str:
    full = {"R": ("Red", "IntensityRed"), "G": ("Green", "IntensityGreen"), "B": ("Blue", "IntensityBlue"), "W": ("White", "IntensityWhite")}
    return "\n".join(f' <Channel Name="{full[c][0]} {i}" Preset="{full[c][1]}"/>' for i in range(1, n + 1) for c in names)


def mode_xml(name: str, channels: list[str], heads: list[list[int]], extra: str = "") -> str:
    lines = [f' <Mode Name="{name}">']
    lines += [f'  <Channel Number="{i}">{c}</Channel>' for i, c in enumerate(channels)]
    lines += ["  <Head>" + "".join(f"<Channel>{i}</Channel>" for i in head) + "</Head>" for head in heads]
    return "\n".join(lines) + extra + "\n </Mode>"


# --------------------------------------------------------------------------- the four files: modes, channel order, pixels


def test_an_rgb_par_has_its_modes_in_the_files_order_with_one_pixel_each():
    result = imported(PAR)
    assert [m["name"] for m in result.ftype["modes"]] == ["3CH", "6CH"] and result.ftype["default_mode"] == "3ch"
    assert [m["ofl_mode"] for m in result.ftype["modes"]] == ["3-channel", "6-channel"]  # OFL's own names of the modes
    by_name = modes(PAR)
    assert by_name["3CH"]["pixels"] == 1 and by_name["3CH"]["channels"] == [{"pixels": "RGB"}]
    six = by_name["6CH"]  # Dimmer, Red, Green, Blue, Strobe, Macro: the dimmer is held at full, the colours are the pixel
    assert six["pixels"] == 1 and slots(six) == [("Dimmer", 255), (None, "RGB"), ("Strobe", {"open": 0, "strobo": 255}), ("Macro", None)]
    assert sum(1 for _ in six["channels"]) == 4 and imported(PAR).report.modes[1]["channels"] == 6  # 6 DMX channels, as in the file
    assert imported(PAR).report.skipped == []


def test_an_rgbw_bar_has_a_pixel_for_every_head():
    by_name = modes(BAR)
    assert list(by_name) == ["4 Pixels", "2 Pixels"]  # the two modes whose heads are the same four channels each
    four, two = by_name["4 Pixels"], by_name["2 Pixels"]
    assert four["pixels"] == 4 and two["pixels"] == 2  # as many pixels as <Head> elements
    assert slots(four) == [("Dimmer", 255), (None, "RGBW"), ("Strobe", {"open": 0, "strobo": 255})]  # Dimmer, 4 × (R G B W), Strobe
    assert slots(two) == [(None, "RGBW")]
    assert [m["channels"] for m in imported(BAR).report.modes] == [18, 8]  # 1 + 4 × 4 + 1 and 2 × 4: the file's channel counts
    assert imported(BAR).report.modes[0]["pixels"] == 4


def test_the_heads_are_an_ofl_matrix_with_template_channels():
    ofl = qxf_to_ofl(BAR.read_bytes(), today=TODAY).ofl
    assert ofl["matrix"] == {"pixelCount": [4, 1, 1]}  # the Layout of the file: 4 × 1
    assert list(ofl["templateChannels"]) == ["Red $pixelKey", "Green $pixelKey", "Blue $pixelKey", "White $pixelKey"]
    assert ofl["templateChannels"]["White $pixelKey"]["capability"] == {"type": "ColorIntensity", "color": "White"}
    four, two = ofl["modes"][0], ofl["modes"][1]
    assert four["channels"][0] == "Dimmer" and four["channels"][2] == "Strobe"
    assert four["channels"][1] == {"insert": "matrixChannels", "repeatFor": ["1", "2", "3", "4"], "channelOrder": "perPixel", "templateChannels": ["Red $pixelKey", "Green $pixelKey", "Blue $pixelKey", "White $pixelKey"]}
    assert two["channels"][0]["repeatFor"] == ["1", "2"]  # a mode with fewer heads names its pixels
    assert set(ofl["availableChannels"]) == {"Dimmer", "Strobe"} | {f"{c} {n}" for c in ("Red", "Green", "Blue") for n in (1, 2)} - {"Blue 2"}  # the plain channels some mode still lists
    assert ofl["physical"]["matrixPixels"] == {"spacing": [0, 0, 0]} and ofl["categories"] == ["Pixel Bar"]  # "LED Bar (Pixels)"


def test_modes_whose_heads_cant_be_pixels_are_left_out_with_the_reason_and_kept():
    result = imported(BAR)
    skipped = {s["mode"]: s["reason"] for s in result.report.skipped}
    assert skipped == {
        "Grouped by colour": "channels ordered per channel, not per pixel",  # RR GG BB: not what a pixel block is
        "Mixed heads": "the heads can't be pixels (the heads don't all have the same number of channels)",
    }
    assert [m["name"] for m in result.ftype["ofl_modes"]] == ["4 Pixels", "2 Pixels", "Grouped by colour", "Mixed heads"]  # all four are kept
    assert result.ftype["modes"][0]["ofl_mode"] == "4 Pixels"


def test_16bit_and_switching_channels_are_mapped_the_way_ofl_does_it():
    result = imported(SPOT)
    standard, extended = modes(SPOT)["Standard"], modes(SPOT)["Extended"]
    # the fine channels sit next to their coarse channel as held values; the dimmer is held at full
    assert slots(standard) == [("Pan", None), ("Pan Fine", None), ("Tilt", None), ("Tilt Fine", None), ("Dimmer", 255), ("Dimmer Fine", None), (None, "RGB")]
    assert result.report.modes[0]["channels"] == 9 and result.report.modes[1]["channels"] == 11
    # "Function" switches Red into Program in the extended mode; with Function at its default the channel is Red
    assert slots(extended)[-3:] == [("Function", None), (None, "RGB"), ("Gobo Wheel", None)]
    ofl = qxf_to_ofl(SPOT.read_bytes(), today=TODAY).ofl
    assert ofl["availableChannels"]["Pan"]["fineChannelAliases"] == ["Pan Fine"] and "Pan Fine" not in ofl["availableChannels"]  # a fine channel is an alias, not a channel
    assert ofl["availableChannels"]["Pan"]["capability"] == {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"}  # the angle is the Focus' PanMax
    assert ofl["modes"][1]["channels"][7] == "Red / Program"  # OFL's key of a switching channel
    assert [c["switchChannels"] for c in ofl["availableChannels"]["Function"]["capabilities"]] == [{"Red / Program": "Red"}, {"Red / Program": "Program"}]
    assert ofl["wheels"]["Gobo Wheel"]["slots"][0] == {"type": "Open"} and [s["name"] for s in ofl["wheels"]["Gobo Wheel"]["slots"][1:]] == ["Stars", "Dots"]
    assert ofl["physical"] == {"dimensions": [250, 350, 200], "weight": 7, "power": 90, "DMXconnector": "5-pin", "bulb": {"type": "LED", "colorTemperature": 6500, "lumens": 3000}, "lens": {"degreesMinMax": [12, 12]}}
    assert ofl["meta"]["authors"] == ["PitchControl tests", "Miro"] and "matrix" not in ofl and "templateChannels" not in ofl  # no heads: no matrix


def test_a_dimmer_only_fixture_follows_the_brightness():
    result = imported(DIMMER)
    (mode,) = result.ftype["modes"]
    assert (mode["name"], mode["pixels"], mode["channels"]) == ("1CH", 1, [{"name": "Intensity", "pixels": "I"}])
    assert "No colour mixing" in mode["description"] and result.report.modes[0]["channels"] == 1
    assert qxf_to_ofl(DIMMER.read_bytes(), today=TODAY).ofl["categories"] == ["Dimmer"]


# --------------------------------------------------------------------------- the kept data and the report


@pytest.mark.parametrize("path", [PAR, BAR, SPOT, DIMMER], ids=lambda p: p.stem)
def test_what_is_kept_and_the_way_back(path, tmp_path):
    from pitchcontrol.config.loader import ConfigStore

    result = imported(path)
    ofl = qxf_to_ofl(path.read_bytes(), today=TODAY).ofl
    ftype = result.ftype
    assert ftype["source"]["format"] == "ofl" and ftype["source"]["via"] == "qlcplus" and ftype["source"]["file"] == path.name
    assert ftype["source"]["converter"] == CONVERTER_VERSION and "license" not in ftype["source"] and "fixture" not in ftype["source"]
    assert "QLC+" in ftype["source"]["note"] and ftype["source"]["manufacturer"] == "Test Lights"
    assert ftype["qlcplus"]["xml"] == path.read_text(encoding="utf-8")  # the original file, whole
    assert ftype["qlcplus"]["creator"] == {"Name": "Q Light Controller Plus", "Version": "4.12.2", "Author": ftype["qlcplus"]["creator"]["Author"]}
    assert ftype["qlcplus"]["type"] and rebuild_ofl(ftype) == ofl and list(rebuild_ofl(ftype)) == list(ofl)  # OFL's fixture, in the order it was built
    store = ConfigStore(tmp_path)  # saved, loaded again: nothing is lost
    store.save_fixture_type(FixtureType.model_validate(ftype | {"name": "T"}))
    on_disk = json.loads((tmp_path / "fixtures" / "types" / "T.json").read_text(encoding="utf-8"))
    assert on_disk["qlcplus"] == ftype["qlcplus"] and rebuild_ofl(on_disk) == ofl
    assert rebuild_ofl(store.load_fixture_type("T").model_dump(mode="json", exclude_none=True)) == ofl


def test_what_the_ofl_model_cant_hold_is_reported_and_kept():
    result = imported(SPOT)
    unmapped = result.ftype["qlcplus"]["unmapped"]
    assert unmapped == [{"path": "FixtureDefinition/Physical/Focus", "attributes": {"Type": "Head"}}]  # OFL has no focus type
    assert result.report.dropped == ['Focus attribute “Type”: 1 time, first in Physical/Focus (Type="Head")']
    assert imported(DIMMER).report.dropped == [] and imported(DIMMER).ftype["qlcplus"]["unmapped"] == []  # everything of this file was used


def test_what_nothing_reads_is_listed_with_its_path():
    text = qxf(
        ' <Channel Name="Dimmer" Preset="IntensityMasterDimmer" Flavour="x"/>\n <Gadget Size="2">hello</Gadget>',
        ' <Mode Name="1 Channel"><Channel Number="0" Actuator="slider">Dimmer</Channel></Mode>',
    )
    result = import_qxf(text, file="odd.qxf")
    assert result.ftype["qlcplus"]["unmapped"] == [
        {"path": 'FixtureDefinition/Channel[@Name="Dimmer"]', "attributes": {"Flavour": "x"}},
        {"path": "FixtureDefinition/Gadget", "element": True, "attributes": {"Size": "2"}, "text": "hello"},
        {"path": "FixtureDefinition/Mode[@Name=\"1 Channel\"]/Channel", "attributes": {"Actuator": "slider"}},
    ]
    assert len(result.report.dropped) == 3 and result.report.dropped[1].startswith("element Gadget: 1 time")


def test_the_report_says_where_the_file_came_from():
    report = imported(PAR).report.as_json()
    assert report["fixture"] == {"name": "RGB PAR", "manufacturer": "Test Lights", "key": None, "url": None}
    assert "QLC+" in report["check"] and "Open Fixture Library" not in report["check"]
    assert "QLC+ fixture definition (Test-Lights-RGB-PAR.qxf)" in imported(PAR).ftype["description"]
    assert imported(PAR).name == "Test Lights RGB PAR"


# --------------------------------------------------------------------------- heads, more

def pixels_of(text: str) -> dict[str, int]:
    return {m["name"]: m["pixels"] for m in import_qxf(text).ftype["modes"]}


def test_pixel_keys_come_from_the_numbers_in_the_names():
    text = qxf(colour_channels(3).replace(" 1", " 0").replace(" 2", " 1").replace(" 3", " 2"), mode_xml("m", [f"{c} {n}" for n in range(3) for c in ("Red", "Green", "Blue")], [[0, 1, 2], [3, 4, 5], [6, 7, 8]]))
    ofl = qxf_to_ofl(text).ofl
    assert ofl["matrix"] == {"pixelKeys": [[["0", "1", "2"]]]}  # not 1, 2, 3: the file counts from 0
    assert ofl["modes"][0]["channels"][0]["repeatFor"] == ["0", "1", "2"]
    assert pixels_of(text) == {"m": 3}


def test_a_2d_layout_gives_rows_of_keys_and_other_modes_name_their_pixels():
    layout = '\n  <Physical><Layout Width="2" Height="2"/></Physical>'
    names4 = [f"{c} {n}" for n in range(1, 5) for c in ("Red", "Green", "Blue")]
    text = qxf(
        colour_channels(4),
        mode_xml("four", names4, [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]], layout) + "\n" + mode_xml("two", names4[:6], [[0, 1, 2], [3, 4, 5]]),
    )
    ofl = qxf_to_ofl(text).ofl
    assert ofl["matrix"] == {"pixelKeys": [[["1", "2"], ["3", "4"]]]}  # Layout 2 × 2
    assert pixels_of(text) == {"four": 4, "two": 2}


def test_heads_with_different_channels_are_not_pixels():
    channels = colour_channels(2) + '\n <Channel Name="Dimmer 1" Preset="IntensityDimmer"/>'
    text = qxf(channels, mode_xml("m", ["Red 1", "Green 1", "Blue 1", "Dimmer 1", "Red 2", "Green 2", "Blue 2"], [[0, 1, 2, 3], [4, 5, 6]]))
    result = import_qxf(text)
    assert result.ftype is None and "can't be pixels" in result.report.skipped[0]["reason"]  # the only mode is out: nothing to import


def test_heads_that_are_not_one_block_of_the_modes_channels_are_not_pixels():
    text = qxf(colour_channels(2) + '\n <Channel Name="Dimmer" Preset="IntensityMasterDimmer"/>', mode_xml("m", ["Red 1", "Green 1", "Blue 1", "Dimmer", "Red 2", "Green 2", "Blue 2"], [[0, 1, 2], [4, 5, 6]]))
    assert "one block" in import_qxf(text).report.skipped[0]["reason"]


def test_heads_with_fine_channels_become_template_channels_with_template_aliases():
    channels = "\n".join(f' <Channel Name="Dimmer {n}" Preset="IntensityDimmer"/>\n <Channel Name="Dimmer Fine {n}" Preset="IntensityDimmerFine"/>' for n in (1, 2))
    channels += "\n" + colour_channels(2, "R")
    names = ["Dimmer 1", "Dimmer Fine 1", "Red 1", "Dimmer 2", "Dimmer Fine 2", "Red 2"]
    ofl = qxf_to_ofl(qxf(channels, mode_xml("m", names, [[0, 1, 2], [3, 4, 5]]))).ofl
    assert list(ofl["templateChannels"]) == ["Dimmer $pixelKey", "Red $pixelKey"]
    assert ofl["templateChannels"]["Dimmer $pixelKey"]["fineChannelAliases"] == ["Dimmer Fine $pixelKey"]
    assert ofl["modes"][0]["channels"][0]["templateChannels"] == ["Dimmer $pixelKey", "Dimmer Fine $pixelKey", "Red $pixelKey"]


def test_a_channel_that_every_head_lists_is_a_plain_channel():
    channels = ' <Channel Name="Master" Preset="IntensityMasterDimmer"/>\n' + colour_channels(2)
    text = qxf(channels, mode_xml("m", ["Master", "Red 1", "Green 1", "Blue 1", "Red 2", "Green 2", "Blue 2"], [[0, 1, 2, 3], [0, 4, 5, 6]]))
    (mode,) = import_qxf(text).ftype["modes"]
    assert mode["pixels"] == 2 and slots(mode) == [("Master", 255), (None, "RGB")]  # the master is not part of a pixel


def test_heads_that_list_the_same_channels_count_as_one_pixel():
    """OFL's export gives every pixel of a pixel group a head that lists the group's channels."""
    text = qxf(colour_channels(2), mode_xml("m", ["Red 1", "Green 1", "Blue 1", "Red 2", "Green 2", "Blue 2"], [[0, 1, 2], [0, 1, 2], [3, 4, 5], [3, 4, 5]]))
    result = import_qxf(text)
    assert result.ftype["modes"][0]["pixels"] == 2
    assert any("4 heads, 2 different" in note for note in result.report.notes)


def test_one_head_is_no_matrix():
    text = qxf(' <Channel Name="Dimmer" Preset="IntensityDimmer"/>\n' + colour_channels(1), mode_xml("m", ["Dimmer", "Red 1", "Green 1", "Blue 1"], [[0, 1, 2, 3]]))
    assert "matrix" not in qxf_to_ofl(text).ofl
    (mode,) = import_qxf(text).ftype["modes"]
    assert mode["pixels"] == 1 and slots(mode) == [("Dimmer", 255), (None, "RGB")]


def test_a_mode_without_heads_that_lists_several_pixels_is_warned_about():
    text = qxf(colour_channels(3), mode_xml("m", [f"{c} {n}" for n in (1, 2, 3) for c in ("Red", "Green", "Blue")], []))
    result = import_qxf(text)
    assert any("no <Head> elements" in note and "3 red channels" in note for note in result.report.notes)
    assert result.ftype["modes"][0]["pixels"] == 1  # one pixel, the rest held: the note says so


def test_template_names():
    assert template_split(["Red 1", "Red 2", "Red 3"]) == ("Red $pixelKey", ["1", "2", "3"])
    assert template_split(["R1 Fine", "R2 Fine"]) == ("R$pixelKey Fine", ["1", "2"])
    assert template_split(["Red", "Green"]) is None and template_split(["Red 1"]) is None and template_split(["Red 1", "Green 2"]) is None


# --------------------------------------------------------------------------- the reader


def test_a_capability_preset_and_a_guessed_capability_become_ofl_capabilities():
    text = qxf(
        ''' <Channel Name="Strobe">
  <Group Byte="0">Shutter</Group>
  <Capability Min="0" Max="9">Closed</Capability>
  <Capability Min="10" Max="99" Preset="StrobeFreqRange" Res1="1" Res2="10">Strobe 1-10 Hz</Capability>
  <Capability Min="100" Max="199">Random strobe slow-fast</Capability>
  <Capability Min="200" Max="255" Preset="Bogus">Whatever</Capability>
 </Channel>''',
        ' <Mode Name="1 Channel"><Channel Number="0">Strobe</Channel></Mode>',
    )
    caps = qxf_to_ofl(text).ofl["availableChannels"]["Strobe"]["capabilities"]
    assert caps[0] == {"dmxRange": [0, 9], "type": "ShutterStrobe", "shutterEffect": "Closed"}
    assert caps[1] == {"dmxRange": [10, 99], "type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": "1Hz", "speedEnd": "10Hz", "comment": "Strobe 1-10 Hz"}
    assert caps[2]["randomTiming"] is True and caps[2]["speedStart"] == "slow" and caps[2]["speedEnd"] == "fast"
    assert caps[3]["type"] == "Generic" and "Unknown QLC+ capability preset Bogus" in caps[3]["helpWanted"]  # an unknown preset is kept as Generic


def test_a_shutter_channel_gives_the_open_value_and_the_fastest_strobe():
    result = import_qxf(
        qxf(
            ' <Channel Name="Shutter"><Group Byte="0">Shutter</Group><Capability Min="0" Max="19" Preset="ShutterClose">Closed</Capability><Capability Min="20" Max="39" Preset="ShutterOpen">Open</Capability>'
            '<Capability Min="40" Max="255" Preset="StrobeSlowToFast">Strobe</Capability></Channel>\n' + colour_channels(1),
            mode_xml("m", ["Shutter", "Red 1", "Green 1", "Blue 1"], []),
        )
    )
    assert result.ftype["modes"][0]["channels"][0] == {"name": "Shutter", "shutter": {"open": 30, "strobo": 255}}  # the middle of "Open", as for OFL fixtures


def test_a_channel_without_capabilities_is_the_whole_range_and_the_group_decides_its_type():
    text = qxf(
        ' <Channel Name="Amber"><Group Byte="0">Intensity</Group><Colour>Amber</Colour></Channel>\n <Channel Name="Zoom"><Group Byte="0">Beam</Group></Channel>',
        ' <Mode Name="2 Channel"><Channel Number="0">Amber</Channel><Channel Number="1">Zoom</Channel></Mode>',
    )
    channels = qxf_to_ofl(text).ofl["availableChannels"]
    assert channels["Amber"]["capability"] == {"type": "ColorIntensity", "color": "Amber"}
    assert channels["Zoom"]["capability"] == {"type": "Generic"}


def test_mode_names_are_shortened_like_ofl_does():
    text = qxf(' <Channel Name="D" Preset="IntensityDimmer"/>', "\n".join(f' <Mode Name="{n}"><Channel Number="0">D</Channel></Mode>' for n in ("8 Channel Mode", "Mode 12ch", "Basic")))
    ofl = qxf_to_ofl(text).ofl
    assert [(m["name"], m.get("shortName")) for m in ofl["modes"]] == [("8-channel", "8ch"), ("12-channel", "12ch"), ("Basic", None)]


def test_the_file_may_be_text_or_bytes_and_have_a_byte_order_mark():
    assert imported(DIMMER).name == import_qxf(DIMMER.read_text(encoding="utf-8")).name == import_qxf(b"\xef\xbb\xbf" + DIMMER.read_bytes()).name


def test_things_that_are_not_qlcplus_fixtures_are_refused_with_a_reason():
    cases = {
        "": "not a readable XML file",
        "<other/>": "no FixtureDefinition",
        '<FixtureDefinition xmlns="http://www.qlcplus.org/FixtureDefinition"><Model>x</Model></FixtureDefinition>': "no modes",
        '<FixtureDefinition><Mode Name="a"/></FixtureDefinition>': "no Model",
        '<!DOCTYPE x [<!ENTITY a "aaaa">]><FixtureDefinition>&a;</FixtureDefinition>': "XML entities",
        "x" * 8_100_000: "a few kB",
    }
    for text, why in cases.items():
        with pytest.raises(ImportProblem, match=why):
            import_qxf(text)
    with pytest.raises(ImportProblem, match="looks like an Open Fixture Library"):
        import_qxf('{"$schema": "x", "name": "A", "modes": []}')


# --------------------------------------------------------------------------- QLC+'s own folders


def make_folders(tmp_path: Path, monkeypatch) -> list[Path]:
    main, user = tmp_path / "QLC+" / "Fixtures", tmp_path / "home" / "QLC+" / "Fixtures"
    for folder in (main, user):
        folder.mkdir(parents=True)
    (main / "Test-Lights-RGB-PAR.qxf").write_bytes(PAR.read_bytes())
    (main / "Test-Lights-RGBW-Bar.qxf").write_bytes(BAR.read_bytes())
    (main / "notes.txt").write_text("not a fixture")
    (user / "Mine-Odd.qxf").write_text("<broken", encoding="utf-8")  # no readable header: named by its file name
    (user / "Test-Lights-Dimmer-Pack.qxf").write_bytes(DIMMER.read_bytes())
    monkeypatch.setattr(qlcplus_files, "candidate_dirs", lambda *a, **k: [("QLC+", tmp_path / "QLC+"), ("your QLC+ fixtures", tmp_path / "home" / "QLC+"), ("QLC+", tmp_path / "missing")])
    return [main, user]


def test_the_candidate_folders_are_the_ones_oflS_plugin_names_per_os(tmp_path):
    win = [(label, str(p).replace("\\", "/")) for label, p in qlcplus_files.candidate_dirs("win32", {"ProgramFiles": "C:/Program Files"}, Path("C:/Users/me"))]
    assert ("QLC+", "C:/QLC+") in win and ("your QLC+ fixtures", "C:/Users/me/QLC+") in win and ("QLC+", "C:/Program Files/QLC+") in win
    mac = [(label, p.as_posix()) for label, p in qlcplus_files.candidate_dirs("darwin", {}, Path("/Users/me"))]
    assert ("QLC+", "/Applications/QLC+.app/Contents/Resources") in mac and ("your QLC+ fixtures", "/Users/me/Library/Application Support/QLC+") in mac
    linux = [(label, p.as_posix()) for label, p in qlcplus_files.candidate_dirs("linux", {}, Path("/home/me"))]
    assert ("QLC+", "/usr/share/qlcplus") in linux and ("your QLC+ fixtures", "/home/me/.qlcplus") in linux


def test_only_folders_that_exist_are_listed_with_what_is_in_them(tmp_path, monkeypatch):
    main, user = make_folders(tmp_path, monkeypatch)
    places = qlcplus_files.folders()
    assert [(f.label, f.path) for f in places] == [("QLC+", main), ("your QLC+ fixtures", user)]
    listed = qlcplus_files.listing(places)
    assert [(f["folder"], f["file"], f["manufacturer"], f["model"], f["type"]) for f in listed] == [
        (0, "Test-Lights-RGB-PAR.qxf", "Test Lights", "RGB PAR", "Color Changer"),
        (0, "Test-Lights-RGBW-Bar.qxf", "Test Lights", "RGBW Bar 4", "LED Bar (Pixels)"),
        (1, "Mine-Odd.qxf", "Mine", "Odd", ""),
        (1, "Test-Lights-Dimmer-Pack.qxf", "Test Lights", "Dimmer 1", "Dimmer"),
    ]


def test_without_qlcplus_there_is_nothing_to_list(tmp_path, monkeypatch):
    monkeypatch.setattr(qlcplus_files, "candidate_dirs", lambda *a, **k: [("QLC+", tmp_path / "nope")])
    assert qlcplus_files.folders() == [] and qlcplus_files.listing() == []


def test_only_listed_qxf_files_can_be_read(tmp_path, monkeypatch):
    main, _ = make_folders(tmp_path, monkeypatch)
    (tmp_path / "secret.qxf").write_text("x")
    places = qlcplus_files.folders()
    assert qlcplus_files.read(places, 0, "Test-Lights-RGB-PAR.qxf") == PAR.read_bytes()
    for folder, file in ((0, "../../secret.qxf"), (0, "notes.txt"), (5, "a.qxf"), (-1, "a.qxf"), (0, str(tmp_path / "secret.qxf"))):
        with pytest.raises(FileNotFoundError):
            qlcplus_files.read(places, folder, file)


# --------------------------------------------------------------------------- the app


@pytest.fixture
def client(store):
    return TestClient(create_app(Engine(store, enable_hardware=False)))


def convert_file(client, path: Path):
    return client.post("/api/qlcplus/convert", json={"text": path.read_text(encoding="utf-8"), "file": path.name})


def test_importing_a_file_shows_the_report_then_saves_the_type(client, store):
    reply = convert_file(client, BAR).json()
    assert reply["name"] == "Test Lights RGBW Bar 4" and reply["existing"] is None
    assert [(m["name"], m["pixels"], m["channels"]) for m in reply["report"]["modes"]] == [("4 Pixels", 4, 18), ("2 Pixels", 2, 8)]
    assert [s["mode"] for s in reply["report"]["skipped"]] == ["Grouped by colour", "Mixed heads"]
    assert not (store.types_dir / f"{reply['name']}.json").exists()  # converting saves nothing
    saved = client.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]})
    assert saved.status_code == 200 and saved.json()["problems"] == []
    on_disk = json.loads((store.types_dir / f"{reply['name']}.json").read_text(encoding="utf-8"))
    assert on_disk["qlcplus"]["xml"] == BAR.read_text(encoding="utf-8") and on_disk["source"]["via"] == "qlcplus"
    assert rebuild_ofl(on_disk) == qxf_to_ofl(BAR.read_bytes(), today=on_disk["meta"]["createDate"]).ofl
    engine_type = client.get("/api/fixture-types").json()[reply["name"]]  # the engine has the pixels of the heads
    assert [m["pixels"] for m in engine_type["modes"]] == [4, 2] and engine_type["qlcplus"]["type"] == "LED Bar (Pixels)"


def test_a_name_that_is_taken_asks_before_overwriting(client, store):
    reply = convert_file(client, PAR).json()
    assert client.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]}).status_code == 200
    again = convert_file(client, PAR).json()
    assert again["existing"]["name"] == "Test Lights RGB PAR" and again["existing"]["origin"] == "user"
    assert client.post("/api/fixture-types/import", json={"name": reply["name"], "type": again["type"]}).status_code == 409
    assert client.post("/api/fixture-types/import", json={"name": reply["name"], "type": again["type"], "replace": True}).json()["replaced"] is True


def test_the_file_of_a_qlcplus_folder_is_converted_and_unknown_ones_are_refused(client, tmp_path, monkeypatch):
    make_folders(tmp_path, monkeypatch)
    listing = client.get("/api/qlcplus/fixtures").json()
    assert [f["label"] for f in listing["folders"]] == ["QLC+", "your QLC+ fixtures"] and len(listing["fixtures"]) == 4
    first = listing["fixtures"][0]
    reply = client.post("/api/qlcplus/convert", json={"folder": first["folder"], "file": first["file"]}).json()
    assert reply["name"] == "Test Lights RGB PAR" and reply["type"]["source"]["file"] == "Test-Lights-RGB-PAR.qxf"
    for body in ({"folder": 0, "file": "../x.qxf"}, {"folder": 9, "file": "a.qxf"}, {"folder": 0, "file": "notes.txt"}, {}, {"folder": 0}):
        assert client.post("/api/qlcplus/convert", json=body).status_code == 400, body


def test_a_broken_file_is_explained(client):
    assert "not a readable XML" in client.post("/api/qlcplus/convert", json={"text": "<broken", "file": "a.qxf"}).json()["detail"]
    assert "no FixtureDefinition" in client.post("/api/qlcplus/convert", json={"text": "<a/>"}).json()["detail"]
    assert "Open Fixture Library" in client.post("/api/qlcplus/convert", json={"text": "{}"}).json()["detail"]
    # and the other way round: an OFL dialog given a QLC+ file points to the right menu item
    assert "QLC+" in client.post("/api/ofl/convert", json={"text": "<xml/>", "file": "a.qxf"}).json()["detail"]


def test_a_file_the_reader_does_not_expect_is_reported_not_a_500(client, monkeypatch):
    from pitchcontrol.server import app as app_module

    def broken(*a, **k):
        raise KeyError("surprise")

    monkeypatch.setattr(app_module, "import_qxf", broken)
    reply = client.post("/api/qlcplus/convert", json={"text": "<x/>", "file": "a.qxf"})
    assert reply.status_code == 400 and "KeyError" in reply.json()["detail"]


def test_a_device_on_the_network_cannot_import_from_qlcplus(store):
    store.settings = store.settings.model_copy(update={"network": NetworkSettings(enabled=True, port=8000, pin="")})
    phone = TestClient(create_app(Engine(store, enable_hardware=False)), client=PHONE)
    for method, path, body in (("get", "/api/qlcplus/fixtures", None), ("post", "/api/qlcplus/convert", {"text": "<x/>"}), ("post", "/api/qlcplus/convert", {"folder": 0, "file": "a.qxf"})):
        assert phone.request(method, path, json=body).status_code == 403, path
