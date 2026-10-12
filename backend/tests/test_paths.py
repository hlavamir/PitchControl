"""Where the files are (paths.py) and the move of a 1.3 data folder (config/migrate.py)."""

import json
import shutil
from pathlib import Path

import pytest

from pitchcontrol import paths
from pitchcontrol.config import migrate
from pitchcontrol.config.loader import content_hash

from conftest import CONFIG


@pytest.fixture
def home(monkeypatch, tmp_path: Path) -> Path:
    """Documents and the app-data folder inside tmp_path."""
    monkeypatch.setattr(paths, "documents_dir", lambda: tmp_path / "Documents" / "PitchControl")
    monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path / "AppData" / "PitchControl")
    return tmp_path


def test_downloaded_app_uses_documents_and_app_data(home):
    p = paths.resolve_paths(home / "app" / "default_config")
    assert p.user == home / "Documents" / "PitchControl" and p.machine == home / "AppData" / "PitchControl"
    assert p.logs == p.machine / "logs" and p.reason == "Documents"


def test_source_run_uses_the_repos_data_folder(home):
    repo = home / "repo"
    p = paths.resolve_paths(repo / "config", source_repo=repo)
    assert p.user == repo / "data" and p.machine == repo / "data" / ".machine"


def test_data_argument_is_self_contained(home):
    p = paths.resolve_paths(home / "defaults", data=home / "x")
    assert (p.user, p.machine, p.reason) == (home / "x", home / "x" / ".machine", "--data")
    p = paths.resolve_paths(home / "defaults", data=home / "x", machine=home / "m")
    assert p.machine == home / "m"


def test_pointer_file(home):
    docs = home / "Documents" / "PitchControl"
    docs.mkdir(parents=True)
    (docs / "data_folder.txt").write_text(str(home / "elsewhere") + "\n", encoding="utf-8")
    p = paths.resolve_paths(home / "defaults", source_repo=home / "repo")
    assert p.user == home / "elsewhere" and p.machine == home / "AppData" / "PitchControl"


def test_the_apps_own_folder_is_never_the_data_folder(home):
    repo = home / "repo"
    (repo / "config").mkdir(parents=True)
    docs = home / "Documents" / "PitchControl"
    docs.mkdir(parents=True)
    (docs / "data_folder.txt").write_text(str(repo), encoding="utf-8")  # 1.3: "use the repo's config/"
    p = paths.resolve_paths(repo / "config", source_repo=repo)
    assert p.user == docs and p.notices


def make_old_folder(user: Path, defaults: Path) -> None:
    """A data folder as 1.3 left it: config/ with copies of the defaults and the user's own files."""
    old = user / "config"
    shutil.copytree(defaults, old)
    shutil.copytree(CONFIG / "scenes", old / "scenes")
    settings = json.loads((CONFIG / "settings.json").read_text(encoding="utf-8"))
    settings["audio"]["device"] = "Test Interface"
    (old / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    rig = json.loads((defaults / "rigs" / "default.json").read_text(encoding="utf-8"))
    rig["name"] = "club"
    rig["fixtures"][0]["type"] = "old type"  # a type that no default replaces any more
    (old / "rigs" / "club.json").write_text(json.dumps(rig), encoding="utf-8")
    (old / "fixtures" / "types" / "old type.json").write_text('{"pixels": 2}', encoding="utf-8")
    (old / "state").mkdir()
    (old / "state" / "macros.json").write_text('{"values": {"Strobo": 0.5}}', encoding="utf-8")
    (old / ".DS_Store").write_text("x")
    (user / "logs").mkdir()
    (user / "logs" / "261010_120000.log").write_text("old log")


def test_migration_from_the_1_3_layout(tmp_path, monkeypatch):
    defaults, user, machine = tmp_path / "defaults", tmp_path / "Documents", tmp_path / "machine"
    shutil.copytree(CONFIG, defaults, ignore=shutil.ignore_patterns("state", "scenes"))
    make_old_folder(user, defaults)
    # the scenes the app used to ship count as unchanged copies (as recorded in shipped_history)
    shipped = {f"scenes/{p.name}": {content_hash(json.loads(p.read_text(encoding="utf-8")))} for p in (CONFIG / "scenes").glob("*.json")}
    shipped["fixtures/types/old type.json"] = {content_hash({"pixels": 2})}
    monkeypatch.setattr(migrate, "SHIPPED", shipped)

    notices = migrate.migrate_old_layout(user, machine, defaults)
    assert len(notices) == 1 and "updated" in notices[0]
    assert not (user / "config").exists() and not (user / "logs").exists()
    assert (machine / "state" / "macros.json").exists() and (machine / "logs" / "261010_120000.log").exists()
    kept = sorted(p.relative_to(user).as_posix() for p in user.rglob("*") if p.is_file())
    # the default copies and the shipped scenes are gone; the user's rig, the type it needs and the
    # settings stay
    assert kept == ["fixtures/types/old type.json", "rigs/club.json", "settings.json"]

    # loading splits the settings: this computer's audio device goes to machine.json
    store = paths.open_store(paths.DataPaths(defaults=defaults, user=user, machine=machine, reason="test"))
    assert store.settings.audio.device == "Test Interface"
    assert json.loads((machine / "machine.json").read_text(encoding="utf-8"))["audio"] == {"device": "Test Interface"}
    assert "audio" not in json.loads((user / "settings.json").read_text(encoding="utf-8"))
    assert store.rig_origins() == {"club": "user", "default": "default"}

    assert migrate.migrate_old_layout(user, machine, defaults) == []  # once only


def test_open_store_reports_an_unwritable_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "writable", lambda folder: False)
    p = paths.DataPaths(defaults=CONFIG, user=tmp_path / "u", machine=tmp_path / "m", reason="test")
    store = paths.open_store(p)
    assert store.rig.fixtures and any("can't be written" in n for n in store.notices)
