from fastapi.testclient import TestClient

from pitchcontrol.engine.engine import Engine
from pitchcontrol.quitguard import live_outputs, quit_reasons
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
    assert engine.ui_unsaved is None  # nothing reported yet
    client = TestClient(create_app(engine))
    assert client.post("/api/ui/unsaved", json={"pages": ["Inputs"]}).json()["ok"]
    assert engine.ui_unsaved == ["Inputs"]
    client.post("/api/ui/unsaved", json={"pages": []})
    assert engine.ui_unsaved == []
