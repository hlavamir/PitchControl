"""Channel modes of a fixture type (1.6): the legacy load, the default mode, overlap and the channel map per
mode, and an unknown mode."""

import json
import logging
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from pitchcontrol.config.loader import ConfigStore, load_model
from pitchcontrol.config.models import FixtureInstance, FixtureType, Rig
from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.fixtures import Fixture
from pitchcontrol.engine.macros import MacroBank
from pitchcontrol.server.app import create_app

SPOT = {
    "pixels": 1,
    "modes": [
        {"id": "3ch", "name": "3CH", "channels": [{"pixels": "RGB"}]},
        {"id": "4ch", "name": "4CH", "description": "plain RGBW", "channels": [{"pixels": "RGBW"}]},
        {"id": "6ch", "name": "6CH", "channels": [{"pixels": "RGBW"}, {"name": "master", "value": 255}, {"name": "function", "value": 0}]},
    ],
    "default_mode": "4ch",
}


def with_spot(store: ConfigStore, *fixtures: FixtureInstance) -> FixtureType:
    store.fixture_types["spot"] = ftype = FixtureType.model_validate(SPOT | {"name": "spot"})
    store.rig = Rig(name="modes", fixtures=list(fixtures))
    return ftype


def spot(name: str, address: int, mode: str | None = None, **kw) -> FixtureInstance:
    return FixtureInstance(name=name, type="spot", address=address, mode=mode, **kw)


# ---------------------------------------------------------------- the type


def test_a_legacy_channel_list_loads_as_one_mode_named_by_its_channel_count(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"app_version": "1.5.3", "pixels": 3, "channels": [{"name": "master", "value": 255}, {"pixels": "RGB"}]}))
    ftype = load_model(path, FixtureType, name="old")
    assert [(m.id, m.name) for m in ftype.modes] == [("10ch", "10CH")]  # 1 + 3 pixels x 3
    assert ftype.default_mode == "10ch" and ftype.modes[0].channels[1].pixels == "RGB"
    assert ftype.channel_count() == 10 and ftype.channel_count("nonsense") == 10
    saved = ftype.model_dump(mode="json", exclude_none=True)  # written back in the new shape
    assert "channels" not in saved and saved["modes"][0]["id"] == "10ch"
    assert FixtureType.model_validate(saved).modes == ftype.modes  # and loads the same again


def test_the_legacy_pinspot_of_the_test_config_is_one_4ch_mode(store):
    ftype = store.fixture_types["cameo_qspot15_rgbw"]  # tests/config keeps the 1.5 file with a bare channels list
    assert [m.name for m in ftype.modes] == ["4CH"] and ftype.channel_count() == 4


def test_default_mode_and_ids():
    ftype = FixtureType.model_validate(SPOT)
    assert ftype.mode_of(None).id == "4ch" and ftype.mode_of("6ch").name == "6CH"
    assert ftype.mode_of("gone").id == "4ch"  # unknown: the default (validate_rig reports it)
    assert [ftype.channel_count(m) for m in ("3ch", "4ch", "6ch", None)] == [3, 4, 6, 4]
    # a default that doesn't exist: the first mode; no id: made from the name; a duplicate id is made unique
    loose = FixtureType.model_validate(
        {"default_mode": "x", "modes": [{"name": "Two Ch", "channels": [{"value": 0}]}, {"id": "two-ch", "channels": [{"value": 1}]}]}
    )
    assert [m.id for m in loose.modes] == ["two-ch", "two-ch-2"] and loose.default_mode == "two-ch"
    assert loose.modes[1].name == "1CH"  # no name: its channel count
    assert FixtureType.model_validate({}).modes[0].channels[0].pixels == "RGB"  # a new type: one RGB mode


def test_a_type_level_pixel_count_of_an_old_file_is_every_modes_count():
    old = FixtureType.model_validate({"pixels": 4, "modes": [{"channels": [{"pixels": "RGB"}]}, {"channels": [{"value": 0}, {"pixels": "RGBW"}]}]})
    assert [m.pixels for m in old.modes] == [4, 4] and [old.channel_count(m.id) for m in old.modes] == [12, 17]
    assert FixtureType.model_validate({"pixels": 3, "channels": [{"pixels": "RGB"}]}).modes[0].pixels == 3  # before 1.6 as well
    own = FixtureType.model_validate({"pixels": 4, "modes": [{"pixels": 8, "channels": [{"pixels": "R"}]}, {"channels": [{"pixels": "R"}]}]})
    assert [m.pixels for m in own.modes] == [8, 4]  # a mode's own count wins
    saved = old.model_dump(mode="json", exclude_none=True)
    assert "pixels" not in saved and [m["pixels"] for m in saved["modes"]] == [4, 4]  # written in the new shape


def test_the_shipped_types_have_their_modes():
    shipped = ConfigStore(Path(__file__).resolve().parents[2] / "config")  # the repo's config/ read as a data folder
    shipped.load_fixture_types()
    cameo, euro = shipped.fixture_types["Cameo Q-Spot 15"], shipped.fixture_types["Eurolite LED 4C-7"]
    assert [m.name for m in cameo.modes] == ["2CH", "3CH-1", "3CH-2", "4CH", "9CH"] and cameo.default_mode == "4ch"
    assert [cameo.channel_count(m.id) for m in cameo.modes] == [2, 3, 3, 4, 9]
    assert [m.name for m in euro.modes] == ["3CH", "4CH", "5CH", "6CH", "9CH"] and euro.default_mode == "4ch"
    assert [euro.channel_count(m.id) for m in euro.modes] == [3, 4, 5, 6, 9]
    assert [m.id for m in shipped.fixture_types["PitchPls v3"].modes] == ["78ch"]


# ---------------------------------------------------------------- the rig


def test_a_fixture_without_a_mode_uses_the_default(store):
    ftype = with_spot(store, spot("a", 1), spot("b", 10, "6ch"))
    a, b = (Fixture(i, ftype) for i in store.rig.fixtures)
    assert a.mode.id == "4ch" and b.mode.id == "6ch"
    a.rgb = b.rgb = np.array([[1.0, 0.5, 0.0]])
    assert len(a.dmx_bytes(MacroBank())) == 4 and len(b.dmx_bytes(MacroBank())) == 6
    assert b.dmx_bytes(MacroBank())[4:] == [255, 0]  # the constant channels of the 6CH mode
    assert "mode" not in FixtureInstance(name="x").model_dump(mode="json", exclude_none=True)  # legacy rigs have none


def test_overlap_is_checked_per_mode(store):
    with_spot(store, spot("a", 1, "3ch"), spot("b", 4, "3ch"))
    assert store.validate_rig() == []  # 1-3 and 4-6
    store.rig.fixtures[0].mode = "6ch"  # now 1-6 and 4-6
    assert any("overlaps" in p for p in store.validate_rig())
    store.rig.fixtures[0].mode = None  # the default, 4CH: 1-4 and 4-6
    assert any("overlaps" in p for p in store.validate_rig())
    store.rig.fixtures[1].address = 5
    assert store.validate_rig() == []


def test_channels_beyond_512_use_the_fixtures_mode(store):
    with_spot(store, spot("a", 508, "3ch"), spot("b", 508, "6ch", universe=1))
    problems = store.validate_rig()
    assert not any("'a'" in p for p in problems)
    assert any("'b'" in p and "508-513 exceed 512" in p for p in problems)


def test_the_channel_map_follows_each_fixtures_mode(store):
    with_spot(store, spot("a", 1, "3ch"), spot("b", 10), spot("c", 20, "6ch"))
    for f in store.rig.fixtures:
        f.brightness_source, f.brightness = "const", 1.0
        f.hue_source, f.hue, f.saturation_source, f.saturation = "const", 0.0, "const", 1.0  # red
    engine = Engine(store, enable_hardware=False)
    engine.tick(1 / 40)
    uni = engine.universes[0]
    assert uni[0:3] == bytes([255, 0, 0]) and uni[3:9] == bytes(6)  # 3CH: RGB, nothing behind it
    assert uni[9:13] == bytes([255, 0, 0, 0]) and uni[13] == 0  # the default 4CH: RGBW
    assert uni[19:25] == bytes([255, 0, 0, 0, 255, 0])  # 6CH: RGBW, master 255, function 0
    assert [len(f["output"]) for f in engine.state()["fixtures"]] == [3, 4, 6]


def test_an_unknown_mode_is_a_rig_problem_and_plays_the_default(store, caplog):
    with_spot(store, spot("a", 1, "9ch"))
    with caplog.at_level(logging.WARNING):
        problems = store.validate_rig()
    assert len(problems) == 1 and "unknown mode '9ch' of type 'spot'" in problems[0] and "'4CH' is used" in problems[0]
    engine = Engine(store, enable_hardware=False)
    engine.tick(1 / 40)
    assert len(engine.state()["fixtures"][0]["output"]) == 4  # the default mode's four channels


def test_an_unknown_mode_in_a_rig_file_is_noticed_on_load(config_dir):
    (config_dir / "fixtures" / "types" / "spot.json").write_text(json.dumps(SPOT))
    (config_dir / "rigs" / "modes.json").write_text(json.dumps({"fixtures": [{"name": "a", "type": "spot", "address": 1, "mode": "gone"}]}))
    store = ConfigStore(config_dir)
    store.load_settings()
    store.load_fixture_types()
    store.load_rig("modes")
    assert any("unknown mode 'gone'" in n for n in store.notices)
    assert store.rig.fixtures[0].mode == "gone"  # kept as it is: saving doesn't hide the problem


def test_modes_go_through_the_api_and_the_file(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    assert client.post("/api/fixture-types", json={"name": "spot"}).json()["ok"]
    body = client.get("/api/fixture-types").json()["spot"]
    assert [m["name"] for m in body["modes"]] == ["3CH"] and body["default_mode"] == "3ch" and "channels" not in body
    body["modes"].append({"id": "4ch", "name": "4CH", "description": "plain RGBW", "channels": [{"pixels": "RGBW"}]})
    assert client.put("/api/fixture-types/spot", json=body).json()["ok"]
    saved = json.loads((store.types_dir / "spot.json").read_text())
    assert [m["id"] for m in saved["modes"]] == ["3ch", "4ch"] and "channels" not in saved
    rig = client.get("/api/rig").json()
    rig["fixtures"], rig["fog_machines"] = [{"name": "a", "type": "spot", "address": 1, "mode": "4ch"}], []
    assert client.put("/api/rig", json=rig).json()["problems"] == []
    assert store.rig_path(store.rig.name).read_text().count('"mode": "4ch"') == 1


def test_a_type_with_three_modes_is_saved_and_reloaded(store):
    ftype = FixtureType.model_validate(SPOT | {"name": "spot", "description": "three modes"})
    store.save_fixture_type(ftype)
    saved = json.loads((store.types_dir / "spot.json").read_text())
    assert [m["id"] for m in saved["modes"]] == ["3ch", "4ch", "6ch"] and saved["default_mode"] == "4ch" and "channels" not in saved
    again = ConfigStore(store.root)
    again.load_all()
    assert again.fixture_types["spot"].modes == ftype.modes and again.fixture_types["spot"].default_mode == "4ch"
    assert [again.fixture_types["spot"].channel_count(m.id) for m in ftype.modes] == [3, 4, 6]


TUBE = {
    "modes": [
        {"id": "1px", "name": "1 pixel", "pixels": 1, "channels": [{"pixels": "RGB"}]},
        {"id": "8px", "name": "8 pixels", "pixels": 8, "channels": [{"pixels": "RGB"}]},
        {"id": "8px-dim", "name": "8 pixels + dimmer", "pixels": 8, "channels": [{"name": "dimmer", "value": 255}, {"pixels": "RGB"}]},
    ],
    "default_mode": "8px",
}


def with_tube(store: ConfigStore, *fixtures: FixtureInstance) -> FixtureType:
    store.fixture_types["tube"] = ftype = FixtureType.model_validate(TUBE | {"name": "tube"})
    store.rig = Rig(name="pixels", fixtures=list(fixtures))
    return ftype


def tube(name: str, address: int, mode: str | None = None, **kw) -> FixtureInstance:
    return FixtureInstance(name=name, type="tube", address=address, mode=mode, **kw)


def test_modes_with_different_pixel_counts_have_their_own_channel_count(store):
    ftype = with_tube(store, tube("a", 1, "1px"), tube("b", 4, "8px"), tube("c", 30, "8px-dim"))
    assert [ftype.pixel_count(m) for m in ("1px", "8px", "8px-dim", None)] == [1, 8, 8, 8]
    assert [ftype.channel_count(m) for m in ("1px", "8px", "8px-dim", None)] == [3, 24, 25, 24]
    assert store.validate_rig() == []  # 1-3, 4-27, 30-54
    store.rig.fixtures[0].mode = "8px"  # 1-24 now runs into 4-27
    assert any("overlaps" in p for p in store.validate_rig())


def test_the_engine_samples_the_pixels_of_each_fixtures_mode(store):
    with_tube(store, tube("a", 1, "1px", position=(0.2, 0.5), length=0.4), tube("b", 10, "8px", position=(0.8, 0.5), length=0.4))
    engine = Engine(store, enable_hardware=False)
    engine.tick(1 / 40)
    state = engine.state()["fixtures"]
    assert [len(f["uv"]) for f in state] == [1, 8] and [len(f["rgb"]) for f in state] == [1, 8]  # the Rig preview's points
    assert [len(f["output"]) for f in state] == [3, 24]
    assert list(engine._offsets) == [0, 1, 9]  # the mask is sampled for 9 pixels in all


def test_switching_a_fixtures_mode_changes_its_pixels_and_keeps_position_and_length(store):
    with_tube(store, tube("a", 1, "1px", position=(0.3, 0.6), length=0.5, rotation=90))
    engine = Engine(store, enable_hardware=False)
    engine.tick(1 / 40)
    assert len(engine.fixtures[0].uv) == 1
    store.rig.fixtures[0].mode = "8px"
    engine.rebuild_fixtures()
    engine.tick(1 / 40)
    fx = engine.fixtures[0]
    uv = fx.uv
    assert len(uv) == 8 and len(fx.rgb) == 8 and len(fx.last_output) == 24
    assert fx.inst.position == (0.3, 0.6) and fx.inst.length == 0.5
    assert abs(uv[:, 0].mean() - 0.3) < 1e-9 and abs(uv[:, 1].mean() - 0.6) < 1e-9  # still centred there, spread along the length
    assert abs((uv[-1, 1] - uv[0, 1]) - 0.5 * 7 / 8) < 1e-9


def test_the_api_takes_a_pixel_count_per_mode(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    body = client.post("/api/fixture-types", json={"name": "bar"}).json()
    body = client.get("/api/fixture-types").json()["bar"]
    assert "pixels" not in body and body["modes"][0]["pixels"] == 1
    body["modes"][0]["pixels"] = 4
    body["modes"].append({"id": "16", "name": "16px", "pixels": 16, "channels": [{"pixels": "RGB"}]})
    assert client.put("/api/fixture-types/bar", json=body).json()["ok"]
    saved = json.loads((store.types_dir / "bar.json").read_text())
    assert "pixels" not in saved and [m["pixels"] for m in saved["modes"]] == [4, 16]
