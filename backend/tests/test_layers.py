"""Shipped defaults (read-only) + the user's folder + this computer's folder."""

import json
import logging
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pitchcontrol import __version__
from pitchcontrol.config.layers import diff, merge, split_machine
from pitchcontrol.config.loader import ConfigStore
from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.overrides import Overrides
from pitchcontrol.server.app import create_app

from conftest import CONFIG


@pytest.fixture
def layered(tmp_path: Path) -> ConfigStore:
    """The test config as the shipped defaults, an empty user folder and machine folder."""
    defaults = tmp_path / "defaults"
    shutil.copytree(CONFIG, defaults, ignore=shutil.ignore_patterns("state", "scenes"))
    store = ConfigStore(tmp_path / "user", defaults=defaults, machine=tmp_path / "machine")
    store.load_all()
    return store


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def test_merge_diff_and_split():
    base = {"a": 1, "audio": {"device": None, "gain": 1.0, "fft_size": 2048}, "outputs": {"x": [1]}}
    new = merge(base, {"audio": {"device": "Komplete", "fft_size": 4096}, "outputs": {"x": [2]}})
    assert new["audio"] == {"device": "Komplete", "gain": 1.0, "fft_size": 4096} and base["audio"]["device"] is None
    assert diff(base, new) == {"audio": {"device": "Komplete", "fft_size": 4096}, "outputs": {"x": [2]}}
    show, machine = split_machine(new)
    assert show == {"a": 1, "audio": {"fft_size": 4096}}
    assert machine == {"audio": {"device": "Komplete", "gain": 1.0}, "outputs": {"x": [2]}}


def test_defaults_are_used_without_copying_them(layered):
    assert layered.rig.name == "default" and layered.rig.fixtures
    assert layered.fixture_types and layered.controller is not None
    assert set(layered.type_origins().values()) == {"default"} and layered.rig_origins() == {"default": "default"}
    assert files(layered.root) == []  # nothing written by just loading


def test_copy_on_save_and_reset(layered):
    engine = Engine(layered, enable_hardware=False)
    client = TestClient(create_app(engine))
    name = next(iter(layered.fixture_types))
    ftype = client.get("/api/fixture-types").json()[name]

    # saving a shipped type writes a copy into the user folder: "modified"
    client.put(f"/api/fixture-types/{name}", json=ftype | {"gamma": 2.2})
    assert (layered.types_dir / f"{name}.json").exists()
    assert client.get("/api/fixture-types/status").json()["origins"][name] == "modified"
    assert client.delete(f"/api/fixture-types/{name}").status_code == 409  # shipped: never deleted
    assert client.post(f"/api/fixture-types/{name}/reset").json()["gamma"] == ftype["gamma"]
    assert not (layered.types_dir / f"{name}.json").exists()
    assert client.get("/api/fixture-types/status").json()["origins"][name] == "default"

    # a copy with the same content counts as unchanged
    client.put(f"/api/fixture-types/{name}", json=ftype)
    assert client.get("/api/fixture-types/status").json()["origins"][name] == "default"

    # the user's own type
    client.post("/api/fixture-types", json={"name": "Mine"})
    assert client.get("/api/fixture-types/status").json()["origins"]["Mine"] == "user"
    assert client.delete("/api/fixture-types/Mine").json()["ok"]


def test_shipped_rig_copy_on_save_reset_and_rename(layered):
    engine = Engine(layered, enable_hardware=False)
    client = TestClient(create_app(engine))
    rig = client.get("/api/rig").json()
    address = rig["fixtures"][0]["address"]
    rig["fixtures"][0]["address"] = address + 1
    client.put("/api/rig", json=rig)
    assert client.get("/api/rigs").json()["origins"] == {"default": "modified"}
    assert client.delete("/api/rig").status_code == 409
    assert client.post("/api/rig/reset").json()["fixtures"][0]["address"] == address
    assert files(layered.root / "rigs") == []

    # renaming a shipped rig makes a user copy; the shipped one stays listed
    assert client.post("/api/rig/rename", json={"name": "club"}).json()["ok"]
    assert client.get("/api/rigs").json()["origins"] == {"club": "user", "default": "default"}
    assert client.delete("/api/rig").json()["active"] == "default"


def test_settings_are_sparse_and_split_per_computer(layered):
    s = layered.settings
    s.fps = 30.0
    s.audio.device = "Test Interface"
    s.audio.fft_size = 4096
    s.ui.scale = 0.8
    layered.save_settings()
    show = read(layered.settings_path)
    machine = read(layered.machine_path)
    assert show == {"app_version": __version__, "fps": 30.0, "audio": {"fft_size": 4096}}
    assert machine == {"app_version": __version__, "audio": {"device": "Test Interface"}, "ui": {"scale": 0.8}}

    again = ConfigStore(layered.root, defaults=layered.defaults, machine=layered.machine)
    again.load_all()
    assert again.settings.model_dump() == s.model_dump()


@pytest.mark.parametrize("where", ["machine", "settings"])
def test_the_removed_glow_and_ui_brightness_settings_load_without_a_warning_and_are_not_written_back(layered, caplog, where):
    # item 64: a machine.json, or a settings.json from before 1.4 (everything in one file), that still has the two keys of
    # Settings → Appearance
    path = layered.machine_path if where == "machine" else layered.settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ui": {"ink": "phosphor", "glow": 0.3, "brightness": 0.5, "scale": 0.9}}), encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        layered.load_settings()
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == []
    ui = layered.settings.ui
    assert (ui.ink, ui.scale) == ("phosphor", 0.9)
    assert "glow" not in ui.model_dump() and "brightness" not in ui.model_dump() and not ui.model_extra
    layered.save_settings()
    for written in (layered.settings_path, layered.machine_path):
        text = written.read_text(encoding="utf-8")
        assert "glow" not in text and '"brightness"' not in text
    assert read(layered.machine_path)["ui"] == {"ink": "phosphor", "scale": 0.9}


def test_per_computer_values_move_out_of_settings_json(layered):
    # a settings.json from 1.3 (or written by hand): everything in one file
    full = layered.settings.model_dump(mode="json")
    full["audio"]["device"] = "Test Interface"
    full["masks"]["transition_s"] = 4.0
    layered.settings_path.parent.mkdir(parents=True, exist_ok=True)
    layered.settings_path.write_text(json.dumps(full), encoding="utf-8")
    layered.load_settings()
    assert layered.settings.audio.device == "Test Interface" and layered.settings.masks.transition_s == 4.0
    assert read(layered.machine_path)["audio"] == {"device": "Test Interface"}
    show = read(layered.settings_path)
    assert "audio" not in show and show["masks"] == {"transition_s": 4.0}  # sparse: only the change


def test_fog_machines_move_from_settings_into_the_rigs(layered):
    # 1.4 and earlier: the fog machines were in settings.json
    old = [{"name": "Hazer", "channel": 300, "interval_s": 30.0}]
    layered.settings_path.parent.mkdir(parents=True, exist_ok=True)
    layered.settings_path.write_text(json.dumps({"fog": {"machines": old}}), encoding="utf-8")
    layered.rigs_dir.mkdir(parents=True)
    (layered.rigs_dir / "club.json").write_text(json.dumps({"fixtures": []}), encoding="utf-8")
    (layered.rigs_dir / "bar.json").write_text(json.dumps({"fog_machines": []}), encoding="utf-8")
    layered.load_all()
    # the user's rig without fog machines and the shipped active rig (as the user's copy) get them,
    # a rig that already has its own keeps them, and settings.json no longer has any
    assert read(layered.rigs_dir / "club.json")["fog_machines"][0]["channel"] == 300
    assert read(layered.rig_path("default"))["fog_machines"][0]["name"] == "Hazer"
    assert read(layered.rigs_dir / "bar.json")["fog_machines"] == []
    assert "fog" not in read(layered.settings_path)
    assert [m.channel for m in layered.rig.fog_machines] == [300]
    assert any("Fog machines are now part of each rig" in n for n in layered.notices)
    layered.notices.clear()
    layered.load_all()  # once only
    assert not any("Fog machines" in n for n in layered.notices)


def test_fog_page_writes_only_the_fog_machines(layered):
    engine = Engine(layered, enable_hardware=False)
    client = TestClient(create_app(engine))
    rig = client.get("/api/rig").json()
    rig["description"] = "unsaved"
    client.put("/api/rig?persist=false", json=rig)
    res = client.put("/api/rig/fog", json=[{"name": "Fog", "channel": 1}])
    assert res.json()["ok"] and client.get("/api/rig/fog").json()["machines"][0]["channel"] == 1
    saved = read(layered.rig_path("default"))
    assert saved["fog_machines"][0]["channel"] == 1 and saved["description"] != "unsaved"
    assert client.get("/api/rig").json()["description"] == "unsaved"  # still live, still unsaved
    # a fog channel inside a fixture's channels is a rig problem
    fx = layered.rig.fixtures[0]
    res = client.put("/api/rig/fog", json=[{"name": "Fog", "universe": fx.universe, "channel": fx.address}])
    assert any("fog machine 'Fog'" in p for p in res.json()["problems"])
    # the engine fogs from the active rig
    client.put("/api/rig/fog", json=[{"name": "Fog", "universe": 3, "channel": 500, "on_value": 200}])
    engine.macros.set("Fog Machine", 1.0)
    engine.tick(1 / 40)
    assert engine.universes[3][499] == 200


def test_broken_user_file_is_kept_aside_and_the_default_used(layered):
    layered.rigs_dir.mkdir(parents=True)
    (layered.rigs_dir / "default.json").write_text("{ not json", encoding="utf-8")
    layered.load_rig("default")
    assert layered.rig.fixtures  # the shipped rig
    assert [p.name.startswith("default.json.broken-") for p in layered.rigs_dir.iterdir()] == [True]
    assert any("could not be read" in n for n in layered.notices)
    assert layered.rig_names() == ["default"]  # the broken file isn't listed as a rig

    layered.settings_path.write_text('{"fps": "fast"}', encoding="utf-8")
    layered.load_settings()
    assert layered.settings.fps == 40.0 and not layered.settings_path.exists()


def test_missing_active_rig_falls_back(layered):
    layered.load_rig("gone")
    assert layered.rig.name == "default" and layered.settings.active_rig == "default"
    assert any("gone" in n for n in layered.notices)


def test_missing_controller_is_reported(layered):
    layered.load_controller("nope")
    assert layered.controller is None and any("nope" in n for n in layered.notices)


def test_saved_files_record_the_app_version(layered, tmp_path):
    layered.save_rig()
    assert read(layered.rig_path("default"))["app_version"] == __version__
    engine = Engine(layered, enable_hardware=False)
    engine.save_scene(0)
    assert read(layered.scene_path(0))["app_version"] == __version__
    engine._autosave_macros(force=True)
    assert read(layered.state_dir / "macros.json")["app_version"] == __version__

    # Control Desk overrides: the new format, and the one before 1.4
    o = Overrides()
    o.set(0, 5, 200)
    o.save(tmp_path / "o.json")
    assert read(tmp_path / "o.json") == {"app_version": __version__, "universes": {"0": {"5": 200}}}
    (tmp_path / "old.json").write_text('{"1": {"7": 100}}', encoding="utf-8")
    old = Overrides()
    old.load(tmp_path / "old.json")
    assert old.snapshot() == {"1": {"7": 100}}


# --------------------------------------------------------------------------- controller files


def test_editing_a_shipped_controller_makes_a_user_copy_and_reset_removes_it(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    assert client.get("/api/controllers").json()["origins"] == {"lcxl3": "default"}
    data = client.get("/api/controllers/lcxl3").json()
    data["author"] = "Me"
    data["mappings"].append({"number": 99, "macro": "Fog Machine", "mode": "momentary"})
    saved = client.put("/api/controllers/lcxl3", json=data).json()
    assert saved["modified"] and saved["author"] == "Me"
    user = layered.root / "controllers" / "lcxl3.json"
    stored = read(user)
    assert stored["app_version"] == __version__ and stored["modified"] == saved["modified"]  # when and with which version
    assert stored["mappings"][-1] == {"number": 99, "macro": "Fog Machine", "mode": "momentary"}  # defaults are left out
    assert client.get("/api/controllers").json()["origins"] == {"lcxl3": "modified"}
    assert layered.controller.author == "Me"  # it is the active one: live
    assert client.delete("/api/controllers/lcxl3").status_code == 409  # shipped
    again = client.post("/api/controllers/lcxl3/reset").json()
    assert again["author"] == "" and not user.exists()  # the test config has no author


def test_a_controller_file_with_port_match_loads_and_is_written_without_it(layered):
    # item 90: the port is no longer part of a mapping; the old text is kept as the note "designed for"
    user = layered.root / "controllers" / "old.json"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(json.dumps({"name": "old", "port_match": "LCXL3", "channel": 13, "mappings": [{"number": 5, "macro": "Strobo"}]}), encoding="utf-8")
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    data = client.get("/api/controllers/old").json()
    assert data["designed_for"] == "LCXL3" and data["channel"] == 13 and "port_match" not in data
    data["mode"] = "factory template 1"
    data["channel_out"] = 5
    client.put("/api/controllers/old", json=data)
    stored = read(user)
    assert "port_match" not in stored
    assert (stored["designed_for"], stored["mode"], stored["channel"], stored["channel_out"]) == ("LCXL3", "factory template 1", 13, 5)


def test_new_duplicate_and_delete_controller(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    assert client.post("/api/controllers", json={"name": "bad/name"}).status_code == 409
    assert client.post("/api/controllers", json={"name": "LCXL3"}).status_code == 409  # exists, ignoring case
    assert client.post("/api/controllers", json={"name": "Mine"}).json()["name"] == "Mine"
    assert client.post("/api/controllers", json={"name": "Copy", "copy_of": "lcxl3"}).status_code == 200
    copy = client.get("/api/controllers/Copy").json()
    assert copy["name"] == "Copy" and len(copy["mappings"]) == len(client.get("/api/controllers/lcxl3").json()["mappings"])
    assert client.get("/api/controllers").json()["origins"]["Mine"] == "user"
    assert client.delete("/api/controllers/Mine").status_code == 200
    assert "Mine" not in client.get("/api/controllers").json()["available"]
    assert client.get("/api/controllers/Mine").status_code == 404


def test_active_controller_cannot_be_deleted_and_bad_content_is_refused(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    client.post("/api/controllers", json={"name": "Mine"})
    layered.settings.active_controller = "Mine"
    assert client.delete("/api/controllers/Mine").status_code == 409
    res = client.put("/api/controllers/Mine", json={"mappings": [{"number": 5, "macro": "Strobo"}, {"number": 1}]})  # no macro
    assert res.status_code == 422
    assert res.json()["detail"] == "invalid content: mappings[1]: a mapping needs a macro (except shift)"


def test_invalid_settings_rigs_and_fixture_types_are_refused_with_a_readable_422(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    client.post("/api/controllers", json={"name": "Mine"})
    res = client.put("/api/settings", json={"fps": "fast"})
    assert res.status_code == 422 and res.json()["detail"].startswith("invalid content: fps: ")
    res = client.put("/api/rig", json={"fixtures": [{"channel": 0}, "x"]})
    assert res.status_code == 422 and "fixtures[1]" in res.json()["detail"]
    res = client.put("/api/fixture-types/rgb_panel", json={"pixels": 0})
    assert res.status_code == 422 and res.json()["detail"].startswith("invalid content: modes[0].pixels: ")
    many = client.put("/api/controllers/Mine", json={"mappings": [{"number": n} for n in range(8)]}).json()["detail"]
    assert many.count("a mapping needs a macro") == 5 and many.endswith("(and 3 more)")


def test_midi_learning_endpoint(layered):
    from pitchcontrol.io.midi_in import MidiInput

    engine = Engine(layered, enable_hardware=False)
    engine.midi = MidiInput(layered.controller, engine.macros)
    client = TestClient(create_app(engine))
    res = client.post("/api/midi/learning", json={"on": True, "shifts": [{"type": "cc", "number": 60, "channel": 1}], "macro": "Fog Machine"})
    assert res.status_code == 200
    body = res.json()
    assert body["learn_id"] == engine.midi.learn_id and body["seconds"] == 20.0
    assert engine.midi.learning and engine.midi.status()["learn_seconds"] == body["seconds"]
    assert engine.midi._learn_shifts == {("cc", 60, 1)} and engine.midi._learn_macro == "Fog Machine"  # item 93
    assert client.post("/api/midi/learning", json={"on": False}).json()["learn_id"] is None
    assert not engine.midi.learning


def test_controller_list_shows_the_name_from_the_file_or_the_file_name(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    client.post("/api/controllers", json={"name": "Blank"})
    data = {"name": "", "mappings": []}
    client.put("/api/controllers/Blank", json=data)
    labels = client.get("/api/controllers").json()["labels"]
    assert labels["Blank"] == "Blank"  # no name inside the file: the file name
    client.put("/api/controllers/Blank", json={"name": "Akai APC40 (mine)", "mappings": []})
    assert client.get("/api/controllers").json()["labels"]["Blank"] == "Akai APC40 (mine)"


def test_a_controller_file_with_the_1_4_macro_names_loads_on_the_renamed_macros(layered):
    layered.controllers_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(__file__).parent / "old_names" / "controller_1.4.json", layered.controllers_dir / "mine.json")
    layered.notices.clear()
    layered.load_controller("mine")
    assert [m.macro for m in layered.controller.mappings] == [
        "Mask Param A", "Mask Param B", "Mask A", "Mask B", "Mask C", "Mask D", "Strobo Decay",
    ]
    assert layered.notices == []
    layered.save_controller("mine", layered.controller)  # saving writes the new names
    assert "Shader" not in (layered.controllers_dir / "mine.json").read_text(encoding="utf-8")
    assert "Preset" not in (layered.controllers_dir / "mine.json").read_text(encoding="utf-8")


def test_a_controller_file_with_a_page_knob_gets_a_notice(layered):
    layered.controllers_dir.mkdir(parents=True, exist_ok=True)
    old = {"name": "mine", "page_knob": 13, "pages": {"general": [{"cc": 29, "macro": "Strobo Decay"}]}}
    (layered.controllers_dir / "mine.json").write_text(json.dumps(old), encoding="utf-8")
    layered.load_controller("mine")
    assert [m.macro for m in layered.controller.mappings] == ["Strobo Decay"]  # it still loads, without the knob
    assert sum("page knob" in n and "“mine”" in n for n in layered.notices) == 1
    layered.load_controller("mine")
    assert sum("“mine”" in n for n in layered.notices) == 1  # not repeated

    layered.notices.clear()
    (layered.controllers_dir / "mine.json").write_text(
        json.dumps({"name": "mine", "mappings": [{"number": 13, "mode": "page_knob"}, {"number": 1, "macro": "Strobo"}]}), encoding="utf-8"
    )
    layered.load_controller("mine")
    assert any("mine" in n and "page knob" in n for n in layered.notices)

    layered.notices.clear()
    layered.save_controller("mine", layered.controller)  # saving writes the new form
    layered.load_controller("mine")
    assert layered.notices == []  # (the shipped LCXL3 gives none either: test_shipped_config_loads)


# --- the shipped LCXL3 layout changed in 1.5.0: users of the shipped mapping get one notice


def upgrade_store(tmp_path: Path, monkeypatch, version: str, recorded: str | None = None, used: bool = True) -> ConfigStore:
    """A store (not loaded yet) that runs as ``version``; ``recorded`` is the version of the last start, ``used`` says
    whether the user folder holds anything (an earlier run of 1.4.1)."""
    monkeypatch.setattr("pitchcontrol.config.loader.__version__", version)
    defaults = tmp_path / "defaults"
    if not defaults.exists():
        shutil.copytree(CONFIG, defaults, ignore=shutil.ignore_patterns("state", "scenes"))
    store = ConfigStore(tmp_path / "user", defaults=defaults, machine=tmp_path / "machine")
    if used:
        store.root.mkdir(parents=True, exist_ok=True)
        (store.root / "settings.json").write_text("{}", encoding="utf-8")
    if recorded is not None:
        store.machine.mkdir(parents=True, exist_ok=True)
        (store.machine / "last_version").write_text(recorded + "\n", encoding="utf-8")
    return store


def layout_notices(store: ConfigStore) -> list[str]:
    return [n for n in store.notices if "new layout" in n]


@pytest.mark.parametrize("recorded", [None, "1.4.1"])  # 1.4.1 itself recorded nothing; later builds record their version
def test_upgrade_with_the_shipped_lcxl3_gives_one_notice(tmp_path, monkeypatch, recorded):
    store = upgrade_store(tmp_path, monkeypatch, "1.5.0", recorded)
    store.load_all()
    notice = layout_notices(store)
    assert len(notice) == 1
    for part in ("page", "top knob row is unused", "middle knob row is Dimmer 01-08", "scenes 1-7", "Fog", "MIDI mapping"):
        assert part in notice[0]
    assert (store.machine / "last_version").read_text(encoding="utf-8").strip() == "1.5.0"
    store.notices.clear()
    store.load_all()  # the same session
    assert layout_notices(store) == []
    again = upgrade_store(tmp_path, monkeypatch, "1.5.0")  # the next start
    again.load_all()
    assert layout_notices(again) == []


def test_a_fresh_install_gets_no_lcxl3_notice(tmp_path, monkeypatch):
    store = upgrade_store(tmp_path, monkeypatch, "1.5.0", used=False)
    (store.root / ".machine").mkdir(parents=True)  # a portable data folder has this before the first load
    store.load_all()
    assert layout_notices(store) == []
    assert (store.machine / "last_version").read_text(encoding="utf-8").strip() == "1.5.0"


def test_a_machine_with_an_earlier_run_but_an_empty_data_folder_counts_as_an_upgrade(tmp_path, monkeypatch):
    store = upgrade_store(tmp_path, monkeypatch, "1.5.0", used=False)
    (store.machine / "state").mkdir(parents=True)  # the macro autosave of an earlier run
    store.load_all()
    assert len(layout_notices(store)) == 1


def test_an_own_copy_of_lcxl3_gets_only_the_page_knob_notice(tmp_path, monkeypatch):
    store = upgrade_store(tmp_path, monkeypatch, "1.5.0", "1.4.1")
    (store.root / "controllers").mkdir(parents=True)
    old = {"name": "lcxl3", "page_knob": 13, "mappings": [{"number": 5, "macro": "Audio Reactivity"}]}
    (store.root / "controllers" / "lcxl3.json").write_text(json.dumps(old), encoding="utf-8")
    store.load_all()
    assert layout_notices(store) == []
    assert sum("page knob" in n for n in store.notices) == 1


def test_no_lcxl3_notice_before_1_5_0_or_after_it_was_shown(tmp_path, monkeypatch):
    dev = upgrade_store(tmp_path, monkeypatch, "1.4.1", "1.4.1")  # a build before the release
    dev.load_all()
    assert layout_notices(dev) == []
    done = upgrade_store(tmp_path, monkeypatch, "1.5.1", "1.5.0")  # already past it
    done.load_all()
    assert layout_notices(done) == []
    assert (done.machine / "last_version").read_text(encoding="utf-8").strip() == "1.5.1"


def test_saving_a_shipped_controller_unchanged_is_not_a_modification(layered):
    client = TestClient(create_app(Engine(layered, enable_hardware=False)))
    data = client.get("/api/controllers/lcxl3").json()
    saved = client.put("/api/controllers/lcxl3", json=data).json()
    assert saved["modified"]  # the edit time is recorded ...
    assert client.get("/api/controllers").json()["origins"] == {"lcxl3": "default"}  # ... but it isn't a change


def test_a_validation_error_in_the_servers_own_code_shows_in_the_log(layered, caplog):
    from pydantic import ValidationError

    from pitchcontrol.config.models import Controller

    engine = Engine(layered, enable_hardware=False)
    app = create_app(engine)

    @app.get("/api/_boom")
    def boom():
        Controller.model_validate({"mappings": [{"number": 1}]})

    with caplog.at_level("WARNING"):
        res = TestClient(app).get("/api/_boom")
    assert res.status_code == 422
    assert any("/api/_boom" in r.getMessage() and "a mapping needs a macro" in r.getMessage() for r in caplog.records)
