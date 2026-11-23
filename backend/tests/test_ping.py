"""Ping a fixture (item 104): three white flashes in a second, on top of the app's output, the routes and the manual overrides."""

import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pitchcontrol.config.loader import ConfigStore
from pitchcontrol.config.models import FixtureInstance
from pitchcontrol.engine.colors import GroupColors
from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.fixtures import Fixture, GroupBrightness
from pitchcontrol.engine.macros import MacroBank
from pitchcontrol.engine.ping import STEP_S, TOTAL_S, Pings, flash_pixels, is_lit
from pitchcontrol.io.live_input import artnet_key
from pitchcontrol.server.app import create_app

from conftest import SHIPPED_CONFIG
from test_routes import route

V3 = "PitchPls! v3 #1"  # universe 0, address 100: master, mode, 4 strip dimmers, then 24 pixels of RGB
PINSPOT = "Pinspot 1"  # one RGBW pixel, universe 0, address 6
PANEL = "Back panel"  # one RGB pixel, universe 0, address 30


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def engine(store):
    e = Engine(store, enable_hardware=False)
    e.pings.clock = Clock()
    return e


def first_pixel_channels(engine: Engine, name: str) -> int:
    """The 0-based universe index of the first pixel byte of a fixture."""
    fx = next(f for f in engine.fixtures if f.inst.name == name)
    return fx.inst.address - 1 + fx.flash_spans(1)[0][0]


def frame(engine: Engine) -> bytearray:
    engine.tick(0.0)  # time stands still, so that two frames are the same but for the ping
    return engine.universes[0]


# -- the rules


def test_three_flashes_in_one_second():
    assert TOTAL_S == pytest.approx(1.0)
    steps = [is_lit(i * STEP_S + STEP_S / 2) for i in range(5)]
    assert steps == [True, False, True, False, True]  # on, off, on, off, on
    assert not is_lit(TOTAL_S) and not is_lit(TOTAL_S + 5) and not is_lit(-0.1)
    flashes = sum(1 for a, b in zip([False] + steps, steps) if b and not a)
    assert flashes == 3


def test_the_first_tenth_of_the_pixels_and_at_least_one():
    assert [flash_pixels(n) for n in (1, 2, 10, 11, 24, 140, 300)] == [1, 1, 1, 2, 3, 14, 30]


def test_a_ping_restarts_and_ends():
    clock = Clock()
    pings = Pings(clock)
    assert not pings.lit("a")
    pings.start("a")
    assert pings.lit("a") and not pings.lit("b")
    clock.now += 0.3  # in the gap
    assert not pings.lit("a")
    pings.start("a")  # pressed again: the first flash again
    assert pings.lit("a")
    clock.now += TOTAL_S + 0.01
    assert not pings.lit("a") and "a" not in pings._started  # over, and forgotten


# -- in the output


def test_a_multi_pixel_fixture_flashes_only_its_first_tenth(engine):
    before = bytes(frame(engine))
    at = first_pixel_channels(engine, V3)
    assert engine.ping(V3)
    after = frame(engine)
    changed = [i for i in range(512) if after[i] != before[i]]
    assert changed and min(changed) >= at and max(changed) < at + 9  # 24 pixels: 3 pixels, 9 bytes, from the first one
    assert list(after[at : at + 9]) == [255] * 9
    assert list(after[at + 9 : at + 72]) == list(before[at + 9 : at + 72])  # the other 21 pixels show what they showed
    assert after[99] == before[99] == 255 and after[100:105] == before[100:105]  # the master, mode and strip dimmers are untouched


def test_the_fixture_goes_back_to_what_it_showed(engine):
    clock = engine.pings.clock
    before = bytes(frame(engine))
    engine.ping(V3)
    assert bytes(frame(engine)) != before
    clock.now += 0.3  # the gap between two flashes
    assert bytes(frame(engine)) == before
    clock.now += 0.2  # the second flash
    assert bytes(frame(engine)) != before
    clock.now += TOTAL_S  # over
    assert bytes(frame(engine)) == before


def test_a_one_pixel_fixture_and_an_rgbw_pixel(engine):
    at = first_pixel_channels(engine, PANEL)
    engine.ping(PANEL)
    assert list(frame(engine)[at : at + 3]) == [255, 255, 255]
    engine.ping(PINSPOT)
    at = first_pixel_channels(engine, PINSPOT)
    out = frame(engine)
    assert out[at + 3] == 255 and list(out[at : at + 3]) == [0, 0, 0]  # white of an RGBW pixel is its white channel


def test_the_flash_is_above_routes_and_overrides(engine):
    at = first_pixel_channels(engine, V3)
    engine.routes.set_all([route(artnet_universe=1, first_input=1, count=512, universe=0, first_output=1)])
    engine.live.store.put(artnet_key(1), bytes([7]) * 512, "10.0.0.5")
    engine.overrides.set(0, at + 2, 9)  # DMX channels are 1-based: the second pixel byte
    out = frame(engine)
    assert out[at] == 7 and out[at + 1] == 9 and out[at + 30] == 7  # the route over the fixture, the override over the route
    engine.ping(V3)
    out = frame(engine)
    assert list(out[at : at + 9]) == [255] * 9  # the flash over both
    assert out[at + 9] == 7 and out[at + 30] == 7  # the pixels that don't flash: the route as before
    engine.pings.clock.now += 0.3
    out = frame(engine)
    assert out[at] == 7 and out[at + 1] == 9  # and both back


def test_the_flash_shows_in_the_state_and_the_preview_colours(engine):
    engine.tick(1 / 40)
    engine.ping(V3)
    engine.tick(1 / 40)
    fx = next(f for f in engine.state()["fixtures"] if f["name"] == V3)
    assert fx["rgb"][0] == [255, 255, 255] and fx["rgb"][2] == [255, 255, 255]  # what the Output monitor draws
    assert fx["rgb"][3] != [255, 255, 255]  # the fourth pixel is not part of it
    assert fx["output"][6:15] == [255] * 9  # the channel values, after the 6 channels in front of the pixels


def test_the_v2_serial_strip_flashes_too(engine):
    engine.store.rig.fixtures[next(i for i, f in enumerate(engine.store.rig.fixtures) if f.name == "PitchPls! v2 strip 1")].enabled = True
    engine.rebuild_fixtures()
    engine.tick(1 / 40)
    engine.ping("PitchPls! v2 strip 1")
    engine.tick(1 / 40)
    fx = next(f for f in engine.fixtures if f.inst.name == "PitchPls! v2 strip 1")
    n = flash_pixels(fx.pixels)
    assert fx.last_output[: 3 * n] == [255] * (3 * n)
    assert engine.v2_strips[0] == fx.last_output


# -- the API


def test_the_ping_endpoint(engine):
    client = TestClient(create_app(engine))
    assert client.post("/api/rig/ping", json={"name": V3}).json() == {"ok": True}
    assert engine.pings.lit(V3)
    assert client.post("/api/rig/ping", json={"name": "nobody"}).status_code == 404
    engine.store.rig.fixtures[0].enabled = False
    engine.rebuild_fixtures()
    assert client.post("/api/rig/ping", json={"name": engine.store.rig.fixtures[0].name}).status_code == 404  # a disabled fixture sends nothing


# -- the layout walk of flash_spans against dmx_bytes, on the shipped fixture types in every mode


def test_the_flash_spans_match_the_bytes_of_every_shipped_type_and_mode(tmp_path):
    shutil.copytree(SHIPPED_CONFIG, tmp_path / "config", ignore=shutil.ignore_patterns("state", "scenes"))
    shipped = ConfigStore(tmp_path / "config")
    shipped.load_all()
    macros = MacroBank()
    checked = 0
    for name, ftype in shipped.fixture_types.items():
        for mode in ftype.modes:
            fx = Fixture(FixtureInstance(name="x", type=name, mode=mode.id), ftype)
            fx.update(np.zeros(fx.pixels), 0.0, GroupColors(), GroupBrightness(0.0, 0.0), macros)
            plain = fx.dmx_bytes(macros)
            fx.flash(flash_pixels(fx.pixels))
            flashed = fx.dmx_bytes(macros)
            spans = fx.flash_spans(flash_pixels(fx.pixels))
            assert len(plain) == len(flashed)
            inside = {i for offset, length in spans for i in range(offset, offset + length)}
            assert all(i < len(plain) for i in inside), (name, mode.id)
            assert all(plain[i] == flashed[i] for i in range(len(plain)) if i not in inside), (name, mode.id)  # only the pixel bytes of a flash differ
            if any(ch.pixels for ch in fx.mode.channels):
                assert inside and any(flashed[i] == 255 for i in inside), (name, mode.id)  # something lights up at full (an RGBW pixel lights only its white)
            checked += 1
    assert checked >= 4
