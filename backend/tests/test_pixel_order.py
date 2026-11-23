"""Item 103: the free pixel channel order. A pixel block is a preset (I, RGB, GRB, RGBW) or a list of channel sources."""

import json

import numpy as np
import pytest

from pitchcontrol.config.loader import ConfigStore
from pitchcontrol.config.models import PIXEL_PRESETS, PIXEL_SOURCES, ChannelMode, ChannelSlot, FixtureInstance, FixtureType
from pitchcontrol.engine.colors import hsv_to_rgb, rgb_to_hue_saturation
from pitchcontrol.engine.fixtures import Fixture
from pitchcontrol.ofl.convert import convert_fixture
from pitchcontrol.ofl.importer import import_fixture


def old_pixel_bytes(rgb: np.ndarray, gamma: float, fmt: str) -> list[int]:
    """``Fixture.pixel_bytes`` as it was before item 103 (1.8.6): the reference every preset must still match."""
    rgb = np.clip(rgb, 0.0, 1.0)
    if gamma != 1.0:
        rgb = rgb**gamma
    if fmt == "RGB":
        data = rgb
    elif fmt == "RGBW":
        w = rgb.min(axis=1, keepdims=True)
        data = np.hstack([rgb - w, w])
    else:
        data = rgb.max(axis=1, keepdims=True)
    return [int(round(x * 255)) for x in data.reshape(-1)]


def fixture_with(pixels, rgb, gamma=1.0):
    rgb = np.array(rgb, dtype=float).reshape(-1, 3)
    ftype = FixtureType(name="T", gamma=gamma, modes=[ChannelMode(id="m", name="m", pixels=len(rgb), channels=[ChannelSlot(pixels=pixels)])])
    fx = Fixture(FixtureInstance(name="t", type="T", mode="m"), ftype)
    fx.rgb = rgb
    return fx


def random_colours(n=64, seed=7):
    rng = np.random.default_rng(seed)
    colours = rng.random((n, 3))
    colours[::5, 1] = colours[::5, 0]  # ties between channels
    colours[::7] = np.round(colours[::7] * 4) / 4  # exact quarter steps: rounding edge cases
    colours[0] = 0.0
    colours[min(1, n - 1)] = 1.0
    return colours


# ---------------------------------------------------------------------------- the presets are today's bytes


@pytest.mark.parametrize("fmt", ["I", "RGB", "RGBW"])
@pytest.mark.parametrize("gamma", [1.0, 2.0, 2.2, 0.5])
def test_the_old_presets_give_exactly_the_old_bytes(fmt, gamma):
    colours = random_colours()
    assert fixture_with(fmt, colours, gamma).pixel_bytes(fmt) == old_pixel_bytes(colours, gamma, fmt)


@pytest.mark.parametrize("fmt", ["I", "RGB", "RGBW"])
def test_a_list_that_spells_a_preset_is_the_preset_with_the_same_bytes(fmt):
    colours = random_colours()
    spelled = list(PIXEL_PRESETS[fmt])
    assert ChannelSlot(pixels=spelled).pixels == fmt  # saved the short way
    assert fixture_with(spelled, colours, 2.2).pixel_bytes(spelled) == old_pixel_bytes(colours, 2.2, fmt)


def test_every_shipped_type_gives_the_old_bytes():
    from conftest import SHIPPED_CONFIG

    store = ConfigStore(SHIPPED_CONFIG)
    store.load_fixture_types()
    seen = set()
    for name, ftype in store.fixture_types.items():
        for mode in ftype.modes:
            for slot in mode.channels:
                if slot.pixels is None:
                    continue
                seen.add(slot.pixels)
                assert slot.pixels in ("I", "RGB", "RGBW"), f"{name}: the shipped type must keep its short form"
                colours = random_colours(mode.pixels)
                fx = Fixture(FixtureInstance(name="t", type=name, mode=mode.id), ftype)
                fx.rgb = colours
                assert fx.pixel_bytes(slot.pixels) == old_pixel_bytes(colours, fx.gamma, slot.pixels), f"{name} / {mode.name}"
    assert seen == {"I", "RGB", "RGBW"}


def test_old_type_files_load_and_save_as_they_were():
    ftype = FixtureType.model_validate({"channels": [{"pixels": "R"}, {"pixels": "RGBW"}]})  # a pre-1.6 file
    assert [c.pixels for c in ftype.modes[0].channels] == ["I", "RGBW"]
    assert ftype.modes[0].channel_count() == 5
    assert ftype.model_dump(mode="json", exclude_none=True)["modes"][0]["channels"] == [{"pixels": "I"}, {"pixels": "RGBW"}]


# ---------------------------------------------------------------------------- the new orders


@pytest.mark.parametrize(
    "pixels, expected",
    [
        ("GRB", [20, 10, 30]),
        (["RGB.green", "RGB.blue", "RGB.red"], [20, 30, 10]),  # GBR
        (["RGB.blue", "RGB.green", "RGB.red"], [30, 20, 10]),  # BGR
        (["RGB.blue", "RGB.red", "RGB.green"], [30, 10, 20]),
    ],
)
def test_channel_orders(pixels, expected):
    colour = np.array([10, 20, 30]) / 255
    assert fixture_with(pixels, colour).pixel_bytes(pixels) == expected


def test_the_orders_apply_to_every_pixel_of_the_fixture():
    colours = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    bgr = ["RGB.blue", "RGB.green", "RGB.red"]
    assert fixture_with(bgr, colours).pixel_bytes(bgr) == [0, 0, 255, 0, 255, 0, 255, 0, 0]


def test_the_grb_preset_is_ws2812_order():
    assert PIXEL_PRESETS["GRB"] == ("RGB.green", "RGB.red", "RGB.blue")
    assert ChannelMode(pixels=3, channels=[ChannelSlot(pixels="GRB")]).channel_count() == 9


def test_rgbw_in_a_free_order_takes_the_white_out_of_the_colours():
    colour = np.array([200, 100, 50]) / 255
    order = ["RGBW.white", "RGBW.blue", "RGBW.green", "RGBW.red"]  # W B G R
    assert fixture_with(order, colour).pixel_bytes(order) == [50, 0, 50, 150]
    assert fixture_with("RGBW", colour).pixel_bytes("RGBW") == [150, 50, 0, 50]


def test_colours_and_white_can_be_mixed_and_repeated():
    colour = np.array([200, 100, 50]) / 255
    mixed = ["RGB.red", "RGB.red", "RGBW.white"]
    assert fixture_with(mixed, colour).pixel_bytes(mixed) == [200, 200, 50]


def test_gamma_applies_to_light_before_the_order_and_the_white():
    colour = np.array([0.8, 0.4, 0.2])
    gbr = ["RGB.green", "RGB.blue", "RGB.red"]
    assert fixture_with(gbr, colour, gamma=2.0).pixel_bytes(gbr) == [round(0.16 * 255), round(0.04 * 255), round(0.64 * 255)]


# ---------------------------------------------------------------------------- HSB


def test_hue_saturation_brightness_of_a_colour():
    hsb = ["HSB.hue", "HSB.saturation", "HSB.brightness"]
    colour = hsv_to_rgb(np.array([0.25]), np.array([0.5]), np.array([0.8]))
    assert fixture_with(hsb, colour).pixel_bytes(hsb) == [round(0.25 * 255), round(0.5 * 255), round(0.8 * 255)]


def test_the_gamma_applies_to_hsb_brightness_but_not_to_hue_and_saturation():
    hsb = ["HSB.brightness", "HSB.hue", "HSB.saturation"]
    colour = hsv_to_rgb(np.array([0.25]), np.array([0.5]), np.array([0.8]))
    with_gamma = fixture_with(hsb, colour, gamma=2.0).pixel_bytes(hsb)
    assert with_gamma == [round(0.64 * 255), round(0.25 * 255), round(0.5 * 255)]
    assert with_gamma[1:] == fixture_with(hsb, colour, gamma=1.0).pixel_bytes(hsb)[1:]
    assert fixture_with("I", colour, gamma=2.0).pixel_bytes("I") == [with_gamma[0]]  # the I preset is the same brightness


def test_hue_and_saturation_round_trip_through_hsv_to_rgb():
    rng = np.random.default_rng(3)
    h, s, v = rng.random(500), rng.random(500) * 0.99 + 0.01, rng.random(500) * 0.99 + 0.01
    h2, s2 = rgb_to_hue_saturation(hsv_to_rgb(h, s, v))
    assert np.allclose(np.mod(h2 - h + 0.5, 1.0) - 0.5, 0.0, atol=1e-9) and np.allclose(s2, s)


def test_grey_and_black_have_hue_and_saturation_zero():
    hue, sat = rgb_to_hue_saturation(np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]]))
    assert hue.tolist() == [0.0, 0.0] and sat.tolist() == [0.0, 0.0]


# ---------------------------------------------------------------------------- the type file


def test_a_custom_order_loads_saves_and_counts_its_channels(tmp_path):
    body = {
        "transport": "dmx",
        "modes": [
            {"id": "bgr", "name": "BGR", "pixels": 4, "channels": [{"pixels": ["RGB.blue", "RGB.green", "RGB.red"]}]},
            {"id": "w", "name": "W first", "pixels": 2, "channels": [{"pixels": ["RGBW.white", "RGBW.red", "RGBW.green", "RGBW.blue"]}, {"value": 7}]},
            {"id": "grb", "name": "GRB", "pixels": 2, "channels": [{"pixels": ["RGB.green", "RGB.red", "RGB.blue"]}]},
        ],
    }
    store = ConfigStore(tmp_path)
    store.save_fixture_type(FixtureType.model_validate(body | {"name": "Strip"}))
    on_disk = json.loads((tmp_path / "fixtures" / "types" / "Strip.json").read_text(encoding="utf-8"))
    assert on_disk["modes"][0]["channels"] == [{"pixels": ["RGB.blue", "RGB.green", "RGB.red"]}]
    assert on_disk["modes"][1]["channels"][0] == {"pixels": ["RGBW.white", "RGBW.red", "RGBW.green", "RGBW.blue"]}
    assert on_disk["modes"][2]["channels"] == [{"pixels": "GRB"}]  # a list that spells a preset is saved as the preset
    loaded = store.load_fixture_type("Strip")
    assert [m.channel_count() for m in loaded.modes] == [12, 9, 6]
    assert loaded.modes[0].channels[0].sources == ("RGB.blue", "RGB.green", "RGB.red")
    assert loaded.model_dump(mode="json", exclude_none=True)["modes"] == on_disk["modes"]


def test_source_names_are_case_insensitive_and_unknown_ones_are_refused():
    assert ChannelSlot(pixels=["rgb.BLUE", " RGB.green", "RGB.red"]).pixels == ["RGB.blue", "RGB.green", "RGB.red"]
    for bad in (["RGB.red", "RGB.green"], ["RGB.red", "RGB.green", "RGB.blue", "RGBW.white", "HSB.hue"], ["RGB.cyan"], "BGR", [], ["RGB.red", 5, "RGB.blue"]):
        with pytest.raises(ValueError):
            ChannelSlot(pixels=bad)


def test_every_source_has_a_value():
    fx = fixture_with("RGB", [0.2, 0.4, 0.6])
    for name in PIXEL_SOURCES:
        assert len(fx.pixel_bytes([name])) == 1
    assert len(PIXEL_SOURCES) == 10


# ---------------------------------------------------------------------------- the OFL and QLC+ imports


def ofl_bar(colours):
    channels = {c: {"capability": {"type": "ColorIntensity", "color": c}} for c in colours}
    return {
        "$schema": "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/schemas/fixture.json",
        "name": "Strip",
        "categories": ["Pixel Bar"],
        "meta": {"authors": ["t"], "createDate": "2026-01-01", "lastModifyDate": "2026-01-01"},
        "physical": {},
        "availableChannels": channels,
        "modes": [{"name": "3ch", "channels": list(colours)}],
    }


@pytest.mark.parametrize(
    "colours, pixels",
    [
        (["Green", "Red", "Blue"], "GRB"),
        (["Red", "Green", "Blue"], "RGB"),
        (["Blue", "Green", "Red"], ["RGB.blue", "RGB.green", "RGB.red"]),
        (["Green", "Blue", "Red"], ["RGB.green", "RGB.blue", "RGB.red"]),
        (["White", "Red", "Green", "Blue"], ["RGBW.white", "RGBW.red", "RGBW.green", "RGBW.blue"]),
        (["Blue", "Green", "Red", "Warm White"], ["RGBW.blue", "RGBW.green", "RGBW.red", "RGBW.white"]),
        (["Red", "Green", "Blue", "White"], "RGBW"),
    ],
)
def test_the_ofl_converter_keeps_the_colour_order(colours, pixels):
    result = convert_fixture(ofl_bar(colours))
    assert not result.skipped, result.skipped
    assert result.modes[0]["channels"] == [{"pixels": pixels}]
    assert result.modes[0]["description"].startswith(("GRB", "RGB", "BGR", "GBR", "WRGB", "BGRW", "RGBW"))


def test_the_ofl_import_keeps_a_non_rgb_order_through_save_and_load(tmp_path):
    result = import_fixture(ofl_bar(["Blue", "Green", "Red"]))
    store = ConfigStore(tmp_path)
    store.save_fixture_type(FixtureType.model_validate(result.ftype | {"name": "T"}))
    loaded = store.load_fixture_type("T")
    assert loaded.modes[0].channels[0].sources == ("RGB.blue", "RGB.green", "RGB.red")
    assert loaded.modes[0].channel_count() == 3
    on_disk = json.loads((tmp_path / "fixtures" / "types" / "T.json").read_text(encoding="utf-8"))
    assert on_disk["ofl_modes"][0]["channels"] == ["Blue", "Green", "Red"]  # OFL's own data is kept as it was


def test_a_colour_that_is_not_part_of_the_run_still_skips_the_mode():
    result = convert_fixture(ofl_bar(["Amber", "Red", "Green"]))
    assert result.skipped and "aren't a run of red, green and blue" in result.skipped[0][1]
