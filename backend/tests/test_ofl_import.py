"""Import from the Open Fixture Library (item 53): the type keeps the OFL data (the original fixture can be rebuilt from
it exactly), the extra keys survive loading, editing and saving, the report, the file and the online import, the clash.
The shape being tested is documented in ``pitchcontrol/ofl/importer.py``."""

import json
import webbrowser
from pathlib import Path

import pytest
from conftest import SHIPPED_CONFIG
from fastapi.testclient import TestClient

from pitchcontrol.config.loader import RIG_NAME, ConfigStore
from pitchcontrol.config.models import FixtureType, NetworkSettings
from pitchcontrol.engine.engine import Engine
from pitchcontrol.ofl import online
from pitchcontrol.ofl.importer import CONVERTER_VERSION, ImportProblem, Redirect, import_fixture, rebuild_ofl, type_name
from pitchcontrol.server.app import create_app
from test_fixture_library import OFL  # a made-up fixture with a dimmer, strobe, preset, switching channel, amber and a matrix

TOOLS = Path(__file__).resolve().parents[2] / "tools" / "fixture_sources"
OFL_FILES = sorted((TOOLS / "ofl").glob("*.json"))  # the seven item 50 fixtures from OFL, at the pinned commit
HAND_FILES = sorted(p for p in TOOLS.glob("*.json"))  # the three written from the manual
PHONE = ("192.168.1.50", 50000)


def key_of(path: Path) -> str:
    return path.stem.replace("__", "/")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def imported(path: Path):
    return import_fixture(load(path), fixture=key_of(path) if path.parent.name == "ofl" else None, manufacturer="Test", commit="abcdef0123456789", file=path.name)


# --------------------------------------------------------------------------- the round trip


def test_the_item_50_fixtures_are_all_there():
    assert len(OFL_FILES) == 7 and len(HAND_FILES) == 3


@pytest.mark.parametrize("path", OFL_FILES + HAND_FILES, ids=lambda p: p.stem)
def test_ofl_to_pitchcontrol_to_ofl_is_identical(path, tmp_path):
    """The acceptance test: the original fixture, rebuilt from the PitchControl type after it was saved and loaded again."""
    original = load(path)
    result = imported(path)
    store = ConfigStore(tmp_path)
    store.save_fixture_type(FixtureType.model_validate(result.ftype | {"name": "T"}))
    on_disk = json.loads((tmp_path / "fixtures" / "types" / "T.json").read_text(encoding="utf-8"))
    rebuilt = rebuild_ofl(on_disk)
    assert rebuilt == original
    assert list(rebuilt) == list(original)  # the key order too
    assert json.dumps(rebuilt, sort_keys=True) == json.dumps(original, sort_keys=True)
    reloaded = store.load_fixture_type("T")
    assert rebuild_ofl(reloaded.model_dump(mode="json", exclude_none=True)) == original


@pytest.mark.parametrize("path", OFL_FILES + HAND_FILES, ids=lambda p: p.stem)
def test_the_shipped_type_holds_its_fixture_exactly(path):
    """The types shipped with the app (regenerated in this shape): their kept data is the OFL file, nothing lost."""
    names = {load(f).get("source", {}).get("fixture") or load(f).get("source", {}).get("file"): f for f in (SHIPPED_CONFIG / "fixtures" / "types").glob("*.json") if "source" in load(f)}
    shipped = load(names[key_of(path) if path.parent.name == "ofl" else path.name])
    assert rebuild_ofl(shipped) == load(path)
    assert shipped["source"]["format"] == "ofl" and shipped["source"]["converter"] == CONVERTER_VERSION


def test_the_kept_shape():
    ftype = imported(OFL_FILES[0]).ftype
    original = load(OFL_FILES[0])
    for key in original:
        if key not in ("$schema", "name", "modes"):
            assert ftype[key] == original[key], key  # OFL's own names, untouched
    assert ftype["ofl_modes"] == original["modes"]  # OFL's mode list under a name of its own
    assert "name" not in ftype and "$schema" not in ftype  # in source: the type's name is its file's
    source = ftype["source"]
    assert source["format"] == "ofl" and source["name"] == original["name"] and source["schema"] == original["$schema"]
    assert source["fixture"] == key_of(OFL_FILES[0]) and source["commit"] == "abcdef0123456789" and source["manufacturer"] == "Test"
    assert source["key_order"] == list(original) and source["license"] == "MIT" and source["url"].endswith(source["fixture"])
    ofl_modes = {m["name"] for m in original["modes"]}
    assert all(m["ofl_mode"] in ofl_modes for m in ftype["modes"])  # each mode names the OFL mode it came from


def test_the_shipped_modes_name_their_ofl_mode():
    ftype = load(SHIPPED_CONFIG / "fixtures" / "types" / "Stairville LED Bar 240-8.json")
    assert [(m["name"], m["ofl_mode"]) for m in ftype["modes"]] == [("2CH", "2-channel"), ("3CH", "3-channel"), ("5CH", "5-channel"), ("24CH", "24-channel")]


def test_nothing_is_lost_on_the_made_up_fixture_either(tmp_path):
    """Switching channels, a skipped mode, nulls: all of OFL's data is in the type, also for modes that were not converted."""
    result = import_fixture({"$schema": "x", **OFL, "modes": [*OFL["modes"], {"name": "Gap", "channels": ["Dimmer", None, "Strobe"]}]})
    assert [s["mode"] for s in result.report.skipped] == ["Per pixel dimmer", "Gap"]
    assert rebuild_ofl(json.loads(json.dumps(FixtureType.model_validate(result.ftype | {"name": "T"}).model_dump(mode="json", exclude_none=True)))) == {
        "$schema": "x", **OFL, "modes": [*OFL["modes"], {"name": "Gap", "channels": ["Dimmer", None, "Strobe"]}]
    }


# --------------------------------------------------------------------------- the report


def test_the_report_lists_the_modes_taken_the_modes_skipped_and_the_assumptions():
    data = {**OFL, "availableChannels": {**OFL["availableChannels"], "Strobe": {"capability": {"type": "ShutterStrobe", "shutterEffect": "Strobe", "speedStart": "slow", "speedEnd": "fast"}}}}
    result = import_fixture(data, fixture="test/test-bar", manufacturer="Test", commit="0123456789abcdef", schema_version="12.6.0")
    report = result.report.as_json()
    assert [m["name"] for m in report["modes"]] == ["4CH", "7CH", "Pixel mode"]
    assert report["modes"][2] == {"name": "Pixel mode", "ofl_mode": "Pixel mode", "pixels": 2, "channels": 8, "description": "Dimmer (held at full), 2 × RGB, Strobe."}
    assert report["skipped"] == [
        {"mode": "Per pixel dimmer", "reason": "a dimmer, amber, CCT or strobe per pixel, which PitchControl can't repeat", "detail": "a per-pixel block with Dimmer, Red $pixelKey"}
    ]
    assert report["assumptions"] == ["Strobe: OFL has no open range, open = 0 (in 3 modes)"]
    assert "manual" in report["check"]
    assert report["fixture"] == {"name": "Test Bar", "manufacturer": "Test", "key": "test/test-bar", "url": "https://open-fixture-library.org/test/test-bar"}
    assert any("default mode is 4CH" in n for n in report["notes"])
    assert report["manual"] == []


def test_the_report_gives_the_manual_links_and_warns_about_a_newer_schema():
    result = import_fixture({**OFL, "links": {"manual": ["https://example.org/m.pdf"], "productPage": ["https://example.org/p"]}}, schema_version="13.0.0")
    assert result.report.manual == ["https://example.org/m.pdf"]
    assert any("OFL schema 13.0.0" in a for a in result.report.assumptions)
    assert result.ftype["links"]["productPage"] == ["https://example.org/p"]


def test_a_file_downloaded_from_the_website_gives_its_key_and_schema_version():
    """OFL's "Download as" JSON adds fixtureKey, manufacturerKey and oflURL, and the schema version in $schema."""
    data = {
        "$schema": "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/schema-12.6.0/schemas/fixture.json",
        **OFL,
        "fixtureKey": "test-bar",
        "manufacturerKey": "american-dj",
        "oflURL": "https://open-fixture-library.org/american-dj/test-bar",
    }
    result = import_fixture(data)
    source = result.ftype["source"]
    assert source["fixture"] == "american-dj/test-bar" and source["schema_version"] == "12.6.0"
    assert result.name == "American Dj Test Bar"  # the manufacturer's key as words: only a suggestion
    assert "manufacturer" not in source  # its name is not known from the file
    assert result.ftype["oflURL"] == data["oflURL"] and result.ftype["fixtureKey"] == "test-bar"  # kept like the other keys
    assert rebuild_ofl(result.ftype) == data and list(rebuild_ofl(result.ftype)) == list(data)


def test_a_fixture_without_any_convertible_mode_imports_nothing():
    result = import_fixture({**OFL, "modes": [OFL["modes"][3]]})  # only the dimmer per pixel
    assert result.ftype is None and result.report.modes == [] and len(result.report.skipped) == 1


def test_things_that_are_not_ofl_fixtures_are_refused_with_a_reason():
    for bad in ([], {"name": "x"}, {"name": "x", "modes": []}, {"name": "x", "modes": [{"name": "m"}]}):
        with pytest.raises(ImportProblem, match="not an Open Fixture Library fixture"):
            import_fixture(bad)
    with pytest.raises(Redirect, match="stairville/other"):
        import_fixture({"$schema": "x", "name": "Old", "redirectTo": "stairville/other", "reason": "FixtureRenamed"})


def test_type_names_are_file_names():
    assert type_name("Stairville", "LED Bar 240/8") == "Stairville LED Bar 240-8"
    assert type_name("Cameo", "Cameo Q-Spot 40") == "Cameo Q-Spot 40"  # the manufacturer is already there
    assert type_name("cameo", "ROOT Par 6") == "Cameo ROOT Par 6"  # OFL's manufacturers.json has "cameo"
    assert type_name("ADB", "Warp M") == "ADB Warp M"
    assert type_name(None, "Élan Spot") == "Elan Spot"
    assert type_name(None, "///") == "Imported fixture"
    long = type_name("M", "x" * 100)
    assert len(long) == 64 and RIG_NAME.fullmatch(long)
    assert RIG_NAME.fullmatch(type_name("A&B", "Light (v2) #1 / «x»"))


# --------------------------------------------------------------------------- the app: load, edit, save


@pytest.fixture
def client(store):
    return TestClient(create_app(Engine(store, enable_hardware=False)))


def convert_file(client, path: Path):
    return client.post("/api/ofl/convert", json={"text": path.read_text(encoding="utf-8"), "file": path.name})


def test_importing_a_file_shows_the_report_then_saves_the_type(client, store):
    path = OFL_FILES[0]
    reply = convert_file(client, path).json()
    assert reply["report"]["modes"] and reply["existing"] is None and reply["name"]
    assert not (store.types_dir / f"{reply['name']}.json").exists()  # converting saves nothing
    saved = client.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]})
    assert saved.status_code == 200 and saved.json()["replaced"] is False
    file = json.loads((store.types_dir / f"{reply['name']}.json").read_text(encoding="utf-8"))
    assert rebuild_ofl(file) == load(path)
    assert file["source"]["file"] == path.name and "commit" not in file["source"]
    assert reply["name"] in client.get("/api/fixture-types").json()


def test_the_extra_keys_survive_load_edit_and_save(client, store):
    """The Fixtures page loads a type, edits it and PUTs it back; the kept data comes back unchanged from the file."""
    path = OFL_FILES[0]
    reply = convert_file(client, path).json()
    name = client.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]}).json()["name"]
    loaded = client.get("/api/fixture-types").json()[name]
    assert rebuild_ofl(loaded) == load(path)  # through the API
    loaded["gamma"] = 2.2  # an edit of the page
    loaded["modes"][0]["description"] = "edited"
    loaded["modes"][0]["channels"][0]["name"] = "Renamed"
    assert client.put(f"/api/fixture-types/{name}?persist=false", json=loaded).status_code == 200  # live
    assert client.put(f"/api/fixture-types/{name}", json=loaded).status_code == 200  # Save
    fresh = ConfigStore(store.root)
    fresh.load_all()
    again = fresh.fixture_types[name]
    assert again.gamma == 2.2 and again.modes[0].description == "edited" and again.modes[0].ofl_mode == loaded["modes"][0]["ofl_mode"]
    assert rebuild_ofl(again.model_dump(mode="json", exclude_none=True)) == load(path)
    assert load_user(store, name)["links"] == load(path)["links"] and load_user(store, name)["ofl_modes"] == load(path)["modes"]


def test_unknown_keys_of_another_importer_survive_too(client, store):
    """Item 54 keeps what OFL can't hold under a ``qlcplus`` key: any key of a type file is carried, nested nulls included."""
    reply = convert_file(client, OFL_FILES[0]).json()
    reply["type"]["qlcplus"] = {"creator": {"name": "Q Light Controller Plus"}, "gap": None, "list": [None, 1]}
    name = client.post("/api/fixture-types/import", json={"name": "From QLC", "type": reply["type"]}).json()["name"]
    got = client.get("/api/fixture-types").json()[name]
    assert got["qlcplus"] == reply["type"]["qlcplus"]
    client.put(f"/api/fixture-types/{name}", json=got)
    assert load_user(store, name)["qlcplus"] == reply["type"]["qlcplus"]


def load_user(store, name: str) -> dict:
    return json.loads((store.types_dir / f"{name}.json").read_text(encoding="utf-8"))


def test_the_kept_keys_are_no_unknown_keys(store, caplog):
    """The loader warns about keys it doesn't know (typos); the kept OFL keys are not among them."""
    ftype = imported(OFL_FILES[0]).ftype
    store.types_dir.mkdir(parents=True, exist_ok=True)
    (store.types_dir / "Kept.json").write_text(json.dumps(ftype), encoding="utf-8")
    with caplog.at_level("WARNING"):
        store.load_fixture_types()
    assert not [r for r in caplog.records if "unknown key" in r.getMessage()]
    assert "Kept" in store.fixture_types


def test_a_file_that_is_not_json_or_not_a_fixture_is_explained(client):
    assert "not JSON" in client.post("/api/ofl/convert", json={"text": "<xml/>", "file": "a.qxf"}).json()["detail"]
    assert "not an Open Fixture Library fixture" in client.post("/api/ofl/convert", json={"text": "{\"a\": 1}"}).json()["detail"]
    assert client.post("/api/ofl/convert", json={}).status_code == 400
    redirect = client.post("/api/ofl/convert", json={"text": json.dumps({"$schema": "x", "name": "Old", "redirectTo": "a/b", "reason": "FixtureRenamed"})})
    assert redirect.status_code == 400 and "a/b" in redirect.json()["detail"]


# --------------------------------------------------------------------------- the clash


def test_a_name_that_is_taken_asks_before_overwriting(client, store):
    reply = convert_file(client, OFL_FILES[0]).json()
    body = {"name": "Clash", "type": reply["type"]}
    assert client.post("/api/fixture-types/import", json=body).status_code == 200
    again = client.post("/api/fixture-types/import", json={**body, "name": "clash"})  # the same name in another letter case
    assert again.status_code == 409 and "'Clash' already exists" in again.json()["detail"]
    other = convert_file(client, OFL_FILES[1]).json()
    assert load_user(store, "Clash")["source"]["name"] == load(OFL_FILES[0])["name"]  # nothing was overwritten
    replaced = client.post("/api/fixture-types/import", json={"name": "clash", "type": other["type"], "replace": True})
    assert replaced.status_code == 200 and replaced.json() == {"ok": True, "name": "Clash", "replaced": True, "problems": []}  # the existing spelling
    assert load_user(store, "Clash")["source"]["name"] == load(OFL_FILES[1])["name"]
    assert sorted(p.stem.lower() for p in store.types_dir.glob("*.json")).count("clash") == 1


def test_the_suggested_name_says_when_it_clashes_and_with_what(tmp_path):
    shipped = ConfigStore(tmp_path / "user", defaults=SHIPPED_CONFIG, machine=tmp_path / "machine")
    shipped.load_all()
    http = TestClient(create_app(Engine(shipped, enable_hardware=False)))
    path = SHIPPED_CONFIG.parents[0] / "tools" / "fixture_sources" / "ofl" / "stairville__led-bar-240-8.json"
    reply = http.post("/api/ofl/convert", json={"text": path.read_text(encoding="utf-8")}).json()
    assert reply["name"] == "LED Bar 240-8"  # no manufacturer known from a file: the user adds it
    assert reply["existing"] is None
    shipped_name = "Stairville LED Bar 240-8"
    assert http.post("/api/fixture-types/import", json={"name": shipped_name, "type": reply["type"]}).status_code == 409  # a shipped type is taken too
    replaced = http.post("/api/fixture-types/import", json={"name": shipped_name, "type": reply["type"], "replace": True})
    assert replaced.status_code == 200 and (tmp_path / "user" / "fixtures" / "types" / f"{shipped_name}.json").exists()  # a copy of your own


def test_bad_names_are_refused(client):
    reply = convert_file(client, OFL_FILES[0]).json()
    for name in ("", "../x", "a/b", ".hidden"):
        assert client.post("/api/fixture-types/import", json={"name": name, "type": reply["type"]}).status_code == 409, name


# --------------------------------------------------------------------------- online (mocked)

MANUFACTURERS = {"$schema": "x", "stairville": {"name": "Stairville", "website": "https://example.org"}, "cameo": {"name": "cameo"}}
BAR = load(OFL_FILES[[p.stem for p in OFL_FILES].index("stairville__led-bar-240-8")])
COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def github(monkeypatch):
    """OFL's GitHub, as a dict of address -> text; the addresses asked are kept."""
    asked: list[str] = []
    routes = {
        f"{online.API}/commits/master": COMMIT,
        f"{online.RAW}/{COMMIT}/fixtures/manufacturers.json": json.dumps(MANUFACTURERS),
        f"{online.API}/contents/fixtures/stairville?ref={COMMIT}": json.dumps([{"name": "led-bar-240-8.json"}, {"name": "old-bar.json"}, {"name": "README.md"}]),
        f"{online.RAW}/{COMMIT}/fixtures/stairville/led-bar-240-8.json": json.dumps(BAR),
        f"{online.RAW}/{COMMIT}/fixtures/stairville/old-bar.json": json.dumps({"$schema": "x", "name": "Old Bar", "redirectTo": "stairville/led-bar-240-8", "reason": "FixtureRenamed"}),
        f"{online.RAW}/{COMMIT}/schemas/fixture.json": json.dumps({"version": "12.6.0"}),
    }

    def fetch_text(url, accept=None, timeout=20.0):
        asked.append(url)
        if url not in routes:
            raise online.OnlineError("the Open Fixture Library doesn't have that fixture")
        return routes[url]

    monkeypatch.setattr(online, "fetch_text", fetch_text)
    return asked, routes


def test_the_manufacturers_and_their_fixtures_come_from_github(client, github):
    listing = client.get("/api/ofl/manufacturers").json()
    assert listing == {"commit": COMMIT, "manufacturers": [{"key": "cameo", "name": "cameo"}, {"key": "stairville", "name": "Stairville"}]}
    assert client.get(f"/api/ofl/manufacturers/stairville?commit={COMMIT}").json() == {"fixtures": ["led-bar-240-8", "old-bar"]}


def test_an_online_import_reads_one_commit_and_records_it(client, github):
    asked, _ = github
    reply = client.post("/api/ofl/convert", json={"fixture": "stairville/led-bar-240-8", "commit": COMMIT}).json()
    assert reply["name"] == "Stairville LED Bar 240-8"
    assert [m["name"] for m in reply["report"]["modes"]] == ["2CH", "3CH", "5CH", "24CH"]
    source = reply["type"]["source"]
    assert source["fixture"] == "stairville/led-bar-240-8" and source["commit"] == COMMIT and source["manufacturer"] == "Stairville"
    assert source["schema_version"] == "12.6.0" and "file" not in source
    assert rebuild_ofl(reply["type"]) == BAR
    assert all(COMMIT in url or "commits/master" in url for url in asked)  # one snapshot, not "master" here and there
    assert client.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]}).status_code == 200


def test_a_page_address_or_a_redirect_gives_the_fixture_it_points_to(client, github):
    for text in ("https://open-fixture-library.org/stairville/led-bar-240-8", "stairville/led-bar-240-8", "https://github.com/OpenLightingProject/open-fixture-library/blob/master/fixtures/stairville/led-bar-240-8.json"):
        assert client.post("/api/ofl/convert", json={"fixture": text}).json()["type"]["source"]["fixture"] == "stairville/led-bar-240-8", text
    moved = client.post("/api/ofl/convert", json={"fixture": "stairville/old-bar"}).json()
    assert moved["type"]["source"]["fixture"] == "stairville/led-bar-240-8"
    assert "moved stairville/old-bar to stairville/led-bar-240-8" in moved["report"]["notes"][0]


def test_online_problems_are_explained(client, github, monkeypatch):
    assert client.post("/api/ofl/convert", json={"fixture": "nobody/nothing"}).status_code == 502
    bad = client.post("/api/ofl/convert", json={"fixture": "../../etc/passwd"})
    assert bad.status_code == 502 and "manufacturer/fixture" in bad.json()["detail"]
    assert client.get("/api/ofl/manufacturers/Not%20A%20Key").status_code == 502

    def offline(url, accept=None, timeout=20.0):
        raise online.OnlineError("can't reach the Open Fixture Library on GitHub (no route): is this computer online?")

    monkeypatch.setattr(online, "fetch_text", offline)
    gone = client.get("/api/ofl/manufacturers")
    assert gone.status_code == 502 and "online" in gone.json()["detail"]
    assert client.post("/api/ofl/convert", json={"fixture": "stairville/led-bar-240-8"}).status_code == 502


def test_without_github_answering_the_ref_is_master(client, monkeypatch):
    def fetch_text(url, accept=None, timeout=20.0):
        if "commits/master" in url or "schemas" in url:
            raise online.OnlineError("rate limit")
        return json.dumps({"$schema": "x", **{"stairville": {"name": "Stairville"}}}) if url.endswith("manufacturers.json") else json.dumps(BAR)

    monkeypatch.setattr(online, "fetch_text", fetch_text)
    source = client.post("/api/ofl/convert", json={"fixture": "stairville/led-bar-240-8"}).json()["type"]["source"]
    assert "commit" not in source and "schema_version" not in source  # not known: not claimed


# --------------------------------------------------------------------------- a device on the network


def test_a_device_on_the_network_cannot_import(store):
    store.settings = store.settings.model_copy(update={"network": NetworkSettings(enabled=True, port=8000, pin="")})
    phone = TestClient(create_app(Engine(store, enable_hardware=False)), client=PHONE)
    assert phone.get("/api/fixture-types").status_code == 200  # it may look
    for method, path, body in (
        ("get", "/api/ofl/manufacturers", None),
        ("get", "/api/ofl/manufacturers/stairville", None),
        ("post", "/api/ofl/convert", {"text": "{}"}),
        ("post", "/api/fixture-types/import", {"name": "x", "type": {}}),
    ):
        reply = phone.request(method, path, json=body)
        assert reply.status_code == 403, path


# --------------------------------------------------------------------------- the links of a type


def test_a_link_of_a_fixture_type_can_be_opened_but_no_other_address(store, monkeypatch):
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    http = TestClient(create_app(Engine(store, enable_hardware=False), desktop={"url": "http://127.0.0.1:1", "data_dir": "x"}))
    link = "https://images.static-thomann.de/pics/atg/atgdata/document/manual/294835_c_294835_v3_r3_en_online.pdf"
    assert http.post("/api/open-url", json={"url": link}).status_code == 400  # not in any type yet
    reply = convert_file(http, OFL_FILES[[p.stem for p in OFL_FILES].index("stairville__led-bar-240-8")]).json()
    http.post("/api/fixture-types/import", json={"name": reply["name"], "type": reply["type"]})
    assert http.post("/api/open-url", json={"url": link}).status_code == 200
    assert http.post("/api/open-url", json={"url": "https://evil.example/x.pdf"}).status_code == 400
    assert http.post("/api/open-url", json={"url": "file:///C:/Windows/system32/calc.exe"}).status_code == 400
    assert opened == [link]
