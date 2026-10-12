"""Shipped defaults (read-only) + the user's folder + this computer's folder."""

import json
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


def test_per_computer_values_move_out_of_settings_json(layered):
    # a settings.json from 1.3 (or written by hand): everything in one file
    full = layered.settings.model_dump(mode="json")
    full["audio"]["device"] = "Test Interface"
    full["fog"]["machines"] = [{"name": "Fog", "channel": 9}]
    layered.settings_path.parent.mkdir(parents=True, exist_ok=True)
    layered.settings_path.write_text(json.dumps(full), encoding="utf-8")
    layered.load_settings()
    assert layered.settings.audio.device == "Test Interface" and layered.settings.fog.machines[0].channel == 9
    assert read(layered.machine_path)["audio"] == {"device": "Test Interface"}
    show = read(layered.settings_path)
    assert "audio" not in show and show["fog"]["machines"][0]["channel"] == 9  # sparse: only the change


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
