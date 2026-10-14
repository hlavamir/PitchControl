import json
import shutil
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from pitchcontrol.config.models import Scene
from pitchcontrol.engine.engine import Engine
from pitchcontrol.server.app import create_app

OLD_NAMES = Path(__file__).resolve().parent / "old_names"  # files as 1.4 wrote them


def test_engine_tick_produces_universe(store):
    for f in store.rig.fixtures:  # the shipped rig may have some switched off for an event
        f.enabled = True
    engine = Engine(store, enable_hardware=False)
    for _ in range(5):
        engine.tick(1 / 40)
    uni = engine.universes[0]
    assert uni[99:105] == bytes([255, 0, 255, 255, 255, 255])  # v3 #1 header at address 100
    assert len(engine.v2_strips) == 4 and len(engine.v2_strips[0]) == 57


def test_engine_reacts_to_kick(store):
    engine = Engine(store, enable_hardware=False)
    engine.macros.set("Strobo", 1.0)
    sr = store.settings.audio.sample_rate
    t = np.arange(sr // 40) / sr
    for i in range(80):  # 2 s: silence, then a loud 55 Hz burst
        if i == 60:
            engine.analyzer.push(0.8 * np.sin(2 * np.pi * 55 * t))
        else:
            engine.analyzer.push(np.zeros_like(t))
        engine.tick(1 / 40)
        if engine.phase.on_peak:
            break
    assert engine.peaks_total >= 1


def test_scene_save_and_load(store):
    engine = Engine(store, enable_hardware=False)
    engine.macros.set("Hue A", 0.3)
    engine.save_scene(7)
    engine.macros.set("Hue A", 0.9)
    assert engine.load_scene(7)
    assert engine.macros.control("Hue A") == 0.3


def test_api_and_websocket(store):
    engine = Engine(store, enable_hardware=False)
    engine.tick(1 / 40)
    client = TestClient(create_app(engine))
    assert len(client.get("/api/macros/defs").json()) > 40
    assert client.post("/api/macros", json={"name": "Strobo", "value": 0.5}).json()["ok"]
    assert engine.macros.control("Strobo") == 0.5
    assert client.post("/api/macros", json={"name": "Nope", "value": 1}).status_code == 404
    rig = client.get("/api/rig").json()
    rig["fixtures"][0]["address"] = 101
    assert "problems" in client.put("/api/rig", json=rig).json()
    assert client.get("/api/audio/bands").json()["trigger_weights"][0] == 1.0
    with client.websocket_connect("/ws") as ws:
        state = ws.receive_json()
        assert "fixtures" in state and "bands" in state
        preview = ws.receive_bytes()
        assert len(preview) == 256 * 256
        ws.send_json({"type": "macro", "name": "Strobo", "value": 0.25})
        ws.receive_json()
    assert engine.macros.control("Strobo") == 0.25


def test_rig_management(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    rigs = lambda: {k: v for k, v in client.get("/api/rigs").json().items() if k != "origins"}  # noqa: E731
    # the shipped rig's name changes with the events; call it "default" here so the expected
    # (sorted) rig lists below stay fixed
    if store.rig.name != "default":
        assert client.post("/api/rig/rename", json={"name": "default"}).json()["ok"]

    # live edit, then "save as": the copy gets the edit, the original file keeps its saved content
    rig = client.get("/api/rig").json()
    rig["fixtures"][0]["address"] = 101
    client.put("/api/rig?persist=false", json=rig)
    assert rigs()["unsaved"]
    assert client.post("/api/rig/duplicate", json={"name": "club"}).json()["name"] == "club"
    assert rigs() == {"active": "club", "available": ["club", "default"], "unsaved": False}
    assert store.settings.active_rig == "club"
    assert client.post("/api/rig/activate", json={"name": "default"}).json()["ok"]
    assert client.get("/api/rig").json()["fixtures"][0]["address"] == 100
    client.post("/api/rig/activate", json={"name": "club"})
    assert client.get("/api/rig").json()["fixtures"][0]["address"] == 101

    # names: taken (any case), unsafe
    assert client.post("/api/rig/duplicate", json={"name": "Default"}).status_code == 409
    assert client.post("/api/rig/new", json={"name": "../evil"}).status_code == 409
    assert client.post("/api/rig/new", json={"name": ""}).status_code == 409

    # rename keeps unsaved live changes unsaved and the saved file as it was
    rig = client.get("/api/rig").json()
    rig["fixtures"][0]["address"] = 102
    client.put("/api/rig?persist=false", json=rig)
    assert client.post("/api/rig/rename", json={"name": "club 2"}).json()["ok"]
    assert rigs() == {"active": "club 2", "available": ["club 2", "default"], "unsaved": True}
    assert (store.rigs_dir / "club 2.json").exists() and not (store.rigs_dir / "club.json").exists()
    assert client.post("/api/rig/reload").json()["fixtures"][0]["address"] == 101

    # new empty rig, delete it (switches to a neighbour), the last rig stays
    assert client.post("/api/rig/new", json={"name": "empty"}).json()["ok"]
    assert client.get("/api/rig").json()["fixtures"] == []
    assert client.delete("/api/rig").json()["active"] == "default"  # the next name, or the previous for the last
    assert client.delete("/api/rig").json()["active"] == "club 2"
    assert client.delete("/api/rig").status_code == 409
    assert rigs()["available"] == ["club 2"]


def test_dimmer_names_and_unused_dimmers_ignore_midi(store):
    import mido

    from pitchcontrol.config.models import Controller, MidiMapping
    from pitchcontrol.io.midi_in import MidiInput

    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    store.rig.dimmer_names = {"Dimmer 01": "Front"}

    # rename live: the rig is unsaved, an empty name removes the name
    res = client.post("/api/rig/dimmer-name", json={"macro": "Dimmer 02", "name": "  Back  "}).json()
    assert res["dimmer_names"] == {"Dimmer 01": "Front", "Dimmer 02": "Back"}
    assert client.get("/api/rigs").json()["unsaved"]
    client.post("/api/rig/dimmer-name", json={"macro": "Dimmer 01", "name": ""})
    assert client.get("/api/rig").json()["dimmer_names"] == {"Dimmer 02": "Back"}
    assert client.post("/api/rig/dimmer-name", json={"macro": "Strobo", "name": "x"}).status_code == 404

    # MIDI moves only dimmers that a fixture uses
    store.rig.fixtures[0].dimmer_macro = "Dimmer 02"
    for f in store.rig.fixtures[1:]:
        f.dimmer_macro = None
    ctrl = Controller(name="t", channel=1, mappings=[MidiMapping(cc=1, macro="Dimmer 01"), MidiMapping(cc=2, macro="Dimmer 02")])
    midi = MidiInput(ctrl, None, engine.macros, ignored=store.dimmer_unassigned)
    engine.macros.set("Dimmer 01", 1.0)
    engine.macros.set("Dimmer 02", 1.0)
    for cc in (1, 2):
        for value in (127, 0):  # the first message only tells where the fader is (it matches the macro), then it moves
            midi.handle(mido.Message("control_change", channel=0, control=cc, value=value))
    assert engine.macros.control("Dimmer 01") == 1.0  # unassigned: ignored
    assert engine.macros.control("Dimmer 02") == 0.0
    assert "unassigned" in midi.recent[0]["note"]
    assert not store.dimmer_unassigned("Dimmer 02") and store.dimmer_unassigned("Dimmer 01")


def test_dmx_overrides(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    engine.tick(1 / 40)
    assert client.get("/api/dmx/0").json()["values"][99] == 255  # v3 #1 master at address 100

    # an override wins over the fixture, also in a universe no fixture uses
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "override", "universe": 0, "channel": 100, "value": 7})
        ws.send_json({"type": "override", "universe": 3, "channel": 512, "value": 300})
        ws.receive_text()  # the server has handled the messages once it pushes state
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 7 and engine.universes[3][511] == 255
    assert engine.state()["overrides"] == {"0": {"100": 7}, "3": {"512": 255}}

    # saved and restored by the next engine
    engine._autosave_overrides(force=True)
    again = Engine(store, enable_hardware=False)
    assert again.overrides.snapshot() == {"0": {"100": 7}, "3": {"512": 255}}

    # release one, then reset all
    engine.overrides.set(3, 512, None)
    assert client.delete("/api/overrides").json()["released"] == 1
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 255 and len(engine.overrides) == 0


def test_fixture_type_management(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    rig_type = store.rig.fixtures[0].type
    status = lambda: client.get("/api/fixture-types/status").json()  # noqa: E731

    # live edit -> unsaved, revert restores the file
    t = client.get("/api/fixture-types").json()[rig_type]
    client.put(f"/api/fixture-types/{rig_type}?persist=false", json=t | {"gamma": 1.7})
    assert store.fixture_types[rig_type].gamma == 1.7 and rig_type in status()["unsaved"]
    assert client.post(f"/api/fixture-types/{rig_type}/reload").json()["gamma"] == t.get("gamma", 1.0)
    assert status()["unsaved"] == []

    # new / duplicate; names are unique ignoring case and file-safe
    assert client.post("/api/fixture-types", json={"name": "spot"}).json()["ok"]
    assert (store.types_dir / "spot.json").exists() and "name" not in (store.types_dir / "spot.json").read_text()
    assert client.post("/api/fixture-types", json={"name": "SPOT"}).status_code == 409
    assert client.post("/api/fixture-types", json={"name": "a/b"}).status_code == 409
    assert client.post("/api/fixture-types", json={"name": "copy", "copy_of": rig_type}).json()["ok"]
    assert store.fixture_types["copy"].channels == store.fixture_types[rig_type].channels

    # rename updates every rig that uses the type (files and the live rig)
    res = client.post(f"/api/fixture-types/{rig_type}/rename", json={"name": "renamed"}).json()
    assert store.rig.name in res["rigs_updated"] and store.rig.fixtures[0].type == "renamed"
    assert '"renamed"' in store.rig_path(store.rig.name).read_text()
    assert not store.type_path(rig_type).exists()
    # a rename that only changes letter case keeps the file
    client.post("/api/fixture-types/spot/rename", json={"name": "Spot"})
    assert "Spot" in store.fixture_types and store.type_path("Spot").exists()

    # delete: refused while used, fine otherwise
    assert client.delete("/api/fixture-types/renamed").status_code == 409
    assert client.delete("/api/fixture-types/Spot").json()["ok"] and "Spot" not in store.fixture_types


def test_first_start_uses_the_macro_defaults(store):
    # no state/macros.json yet: the defaults in macros.py (no scenes ship), a calm test pattern
    m = Engine(store, enable_hardware=False).macros
    assert m.control("Strobo Brightness") == m.control("Idle Brightness") == m.control("Dimmer 01") == 1.0
    assert m.control("Strobo") == m.control("Audio Reactivity") == 0.0
    assert round(m.value("Strobo Decay"), 2) == 1.49 and round(m.value("Idle Attack"), 2) == 2.45
    assert m.control("Mask Param A") == m.control("Mask Param B") == 64 / 127
    assert m.radio_index("preset") == 1 and m.on("Vertical Symmetry") and not m.on("Auto Color Change")


def test_saved_macro_values_win_over_the_defaults(store):
    first = Engine(store, enable_hardware=False)
    first.macros.set("Strobo Brightness", 0.25)
    first._autosave_macros(force=True)
    again = Engine(store, enable_hardware=False)
    assert again.macros.control("Strobo Brightness") == 0.25


def test_scene_and_autosave_with_the_1_4_macro_names_load_on_the_renamed_macros(store, tmp_path):
    shutil.copy(OLD_NAMES / "scene_1.4.json", store.scenes_dir / "scene_4.json")
    old = json.loads((OLD_NAMES / "scene_1.4.json").read_text(encoding="utf-8"))["values"]
    engine = Engine(store, enable_hardware=False)
    assert engine.load_scene(3)
    m = engine.macros
    assert m.control("Mask Param A") == old["Shader Speed"] and m.control("Mask Param B") == old["Shader Param"]
    assert m.radio_index("preset") == 1 and m.on("Mask B") and not m.on("Mask A")  # Preset B was on
    engine.save_scene(3)  # the file gets the new names when it is next saved
    saved = json.loads((store.scenes_dir / "scene_4.json").read_text(encoding="utf-8"))["values"]
    assert saved["Mask Param A"] == old["Shader Speed"] and saved["Mask B"] == 1.0
    assert not [k for k in saved if k.startswith(("Shader", "Preset"))]
    # the crash-recovery file is read the same way
    store.state_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(OLD_NAMES / "scene_1.4.json", store.state_dir / "macros.json")
    again = Engine(store, enable_hardware=False)  # restores the macros on start
    assert again.macros.control("Mask Param B") == old["Shader Param"] and again.macros.on("Mask B")


def test_a_name_in_both_forms_takes_the_new_one():
    assert Scene(values={"Preset A": 0.2, "Mask A": 0.7}).values == {"Mask A": 0.7}
    assert Scene(values={"Shader Speed": 0.2}).values == {"Mask Param A": 0.2}


def test_empty_scene_slot_means_the_defaults(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    engine.macros.set("Strobo Brightness", 0.25)
    engine.save_scene(2)
    assert client.delete("/api/scenes/2").json()["deleted"]
    assert not (store.scenes_dir / "scene_3.json").exists()
    assert client.get("/api/scenes").json()[2]["exists"] is False
    assert client.post("/api/scenes/2/load").json()["ok"]  # an empty slot loads the defaults
    assert engine.macros.control("Strobo Brightness") == 1.0


def test_open_url_only_for_the_projects_pages(store, monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    engine = Engine(store, enable_hardware=False)

    # not the desktop app: the endpoint does not exist
    assert TestClient(create_app(engine)).post("/api/open-url", json={"url": "https://ko-fi.com/zeys_hlvmr"}).status_code == 404

    client = TestClient(create_app(engine, desktop={"url": "http://127.0.0.1:1", "data_dir": "x"}))
    assert client.post("/api/open-url", json={"url": "https://ko-fi.com/zeys_hlvmr"}).status_code == 200
    assert client.post("/api/open-url", json={"url": "https://github.com/hlavamir/PitchControl/releases"}).status_code == 200
    assert opened == ["https://ko-fi.com/zeys_hlvmr", "https://github.com/hlavamir/PitchControl/releases"]
    for bad in ("https://evil.example/", "file:///etc/passwd", "https://ko-fi.com/zeys_hlvmr.evil.example", ""):
        assert client.post("/api/open-url", json={"url": bad}).status_code == 400, bad
    assert len(opened) == 2


def test_frame_rate_is_a_setting_the_engine_follows(store):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    settings = client.get("/api/settings").json()
    settings["fps"] = 25.0
    assert client.put("/api/settings", json=settings).json() == {"ok": True}
    assert client.get("/api/settings").json()["fps"] == 25.0
    assert store.settings.fps == 25.0
