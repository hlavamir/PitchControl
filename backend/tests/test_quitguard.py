from fastapi.testclient import TestClient

from pitchcontrol.engine.engine import Engine
from pitchcontrol.quitguard import REPORT_MAX_AGE_S, UnsavedReports, live_outputs, quit_reasons
from pitchcontrol.server.app import create_app

OFF = {"enttec": [None], "artnet": None, "pitchpls_v2": None}
ENTTEC_UP = {"enttec": [{"connected": True, "error": None, "frames": 5, "kind": "pro"}], "artnet": None, "pitchpls_v2": None}


def test_nothing_live_and_nothing_unsaved_means_no_question():
    assert quit_reasons([], OFF) == []
    assert quit_reasons([], {}) == [] and quit_reasons([], None) == []


def test_a_live_output_is_a_reason():
    reasons = quit_reasons([], ENTTEC_UP)
    assert len(reasons) == 1 and "lights are live" in reasons[0]
    assert live_outputs({**OFF, "artnet": {"connected": True}}) and live_outputs({**OFF, "pitchpls_v2": {"connected": True}})
    assert not live_outputs({"enttec": [{"connected": False, "error": "no port", "frames": 0}], "artnet": {"connected": False}, "pitchpls_v2": None})


def test_unsaved_pages_are_a_reason_and_are_named():
    reasons = quit_reasons(["Inputs", "MIDI mapping"], OFF)
    assert len(reasons) == 1 and "Inputs, MIDI mapping" in reasons[0]


def test_both_reasons_are_both_given():
    assert len(quit_reasons(["Fog"], ENTTEC_UP)) == 2


def test_not_knowing_whether_there_are_unsaved_edits_asks_anyway():
    reasons = quit_reasons(None, OFF)
    assert len(reasons) == 1 and "couldn't check" in reasons[0]


def test_the_pages_report_their_unsaved_edits_to_the_engine(store):
    engine = Engine(store, enable_hardware=False)
    assert engine.ui_unsaved.pages() is None  # nothing reported yet
    client = TestClient(create_app(engine))
    assert client.post("/api/ui/unsaved", json={"client": "window", "pages": ["Inputs"]}).json()["ok"]
    assert engine.ui_unsaved.pages() == ["Inputs"]
    client.post("/api/ui/unsaved", json={"client": "window", "pages": []})
    assert engine.ui_unsaved.pages() == []


def test_one_pages_report_does_not_hide_anothers():
    reports = UnsavedReports()
    reports.report("window", ["MIDI mapping"], now=100.0)
    reports.report("tab", [], now=100.5)  # e.g. "Open in browser", or a reload
    assert reports.pages(now=101.0) == ["MIDI mapping"]
    reports.report("tab", ["Fog"], now=101.0)
    assert reports.pages(now=101.5) == ["Fog", "MIDI mapping"]
    assert quit_reasons(reports.pages(now=101.5), OFF) != []


def test_a_page_that_stopped_reporting_is_ignored():
    reports = UnsavedReports()
    reports.report("tab", ["Fog"], now=100.0)
    reports.report("window", [], now=104.0)
    assert reports.pages(now=104.5) == []  # the tab's last report is 4.5 s old: it was closed
    reports.report("window", ["Inputs"], now=105.0)
    assert reports.pages(now=105.5) == ["Inputs"]


def test_no_fresh_report_means_unknown_and_asks():
    reports = UnsavedReports()
    assert reports.pages(now=100.0) is None
    reports.report("window", [], now=100.0)
    assert reports.pages(now=101.0) == []
    assert reports.pages(now=100.0 + REPORT_MAX_AGE_S + 0.1) is None  # the page stopped reporting (stuck)
    assert len(quit_reasons(reports.pages(now=110.0), OFF)) == 1


def test_live_rig_and_fixture_type_edits_are_asked_about_whichever_page_is_open(store):
    # the Rig and Fixtures pages apply edits live; only Save writes the file. The quit guard asks the server, not the
    # page: a user who edited the rig and went to another page (or never reported) still gets the question
    from pitchcontrol.quitguard import with_live_edits

    app = create_app(Engine(store, enable_hardware=False))
    client = TestClient(app)
    assert app.state.unsaved_live() == []
    rig = client.get("/api/rig").json()
    client.put("/api/rig?persist=false", json=rig)
    assert app.state.unsaved_live() == ["rig"]
    name = sorted(client.get("/api/fixture-types").json())[0]
    client.put(f"/api/fixture-types/{name}?persist=false", json=client.get("/api/fixture-types").json()[name])
    assert app.state.unsaved_live() == ["rig", f"fixture type {name}"]
    reasons = quit_reasons(with_live_edits(["fog machines"], app.state.unsaved_live()), OFF)
    assert len(reasons) == 1 and "fog machines" in reasons[0] and "rig" in reasons[0] and name in reasons[0]
    client.put("/api/rig", json=rig)  # Save
    client.put(f"/api/fixture-types/{name}", json=client.get("/api/fixture-types").json()[name])
    assert app.state.unsaved_live() == []
    assert quit_reasons(with_live_edits([], app.state.unsaved_live()), OFF) == []
    assert with_live_edits(None, ["rig"]) is None  # the pages never reported: asked anyway
