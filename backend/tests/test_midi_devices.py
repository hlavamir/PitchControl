"""The MIDI devices (item 89): one owner of every MIDI port, one stream, a list per computer."""

import json
import logging

import mido
import pytest
from fastapi.testclient import TestClient

import pitchcontrol.io.midi_devices as module
from pitchcontrol.config.models import Controller, MidiDeviceSetting, MidiMapping
from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.routes import MidiChannel
from pitchcontrol.io.midi_devices import MidiDevices
from pitchcontrol.io.midi_in import port_key
from pitchcontrol.io.midi_routes import scale7
from pitchcontrol.server.app import create_app

F1 = "Traktor Kontrol F1 - 1"
LC = "LCXL3 1 MIDI In"


class FakePort:
    def __init__(self, name, callback, owner):
        self.name, self.callback, self.owner, self.closed = name, callback, owner, False

    def close(self):
        self.closed = True
        self.owner.open.discard(self.name)

    def send(self, msg):
        self.callback(msg)


class FakeSystem:
    """The system's MIDI: ``names`` is the list right now (change it to plug and pull), ``fail`` the ports that won't open."""

    def __init__(self, names, fail=()):
        self.names, self.fail, self.ports, self.open = list(names), set(fail), [], set()

    def open_input(self, name, callback=None):
        if name in self.fail:
            raise OSError("MIDI port is in use")
        assert name not in self.open, f"{name} opened twice"
        self.open.add(name)
        port = FakePort(name, callback, self)
        self.ports.append(port)
        return port

    def port(self, name):
        return [p for p in self.ports if p.name == name][-1]


@pytest.fixture
def system(monkeypatch):
    fake = FakeSystem([])
    monkeypatch.setattr(module.mido, "open_input", fake.open_input)
    monkeypatch.setattr(module, "list_midi_inputs_checked", lambda: list(fake.names) if fake.names is not None else None)
    return fake


@pytest.fixture
def devices(store, system):
    return MidiDevices(store)


def state(devices):
    return {d["name"]: d["state"] for d in devices.status()["devices"]}


def saved(store):
    """What machine.json holds."""
    return json.loads(store.machine_path.read_text(encoding="utf-8")).get("midi_devices")


def test_a_device_not_seen_before_is_on_and_saved_and_opened(store, system, devices):
    system.names = [F1]
    devices.sync()
    assert state(devices) == {F1: "connected"} and system.open == {F1}
    assert store.settings.midi_devices[port_key(F1)].input is True and store.settings.midi_devices[port_key(F1)].output is False
    assert saved(store) == {port_key(F1): {"name": F1, "input": True, "output": False}}  # machine.json, not settings.json
    assert "midi_devices" not in json.loads(store.settings_path.read_text(encoding="utf-8")) if store.settings_path.exists() else True
    devices.sync()
    devices.sync()
    assert len(system.ports) == 1  # a port is opened once, however often it is looked at


def test_in_off_closes_the_port_at_once_and_in_on_opens_it_again(store, system, devices):
    system.names = [F1, LC]
    devices.sync()
    devices.set_switches(port_key(F1), input=False)
    assert state(devices) == {F1: "off", LC: "connected"}
    assert system.open == {LC} and system.port(F1).closed  # let go before the call returned: another program can take it
    assert saved(store)[port_key(F1)]["input"] is False
    devices.sync()
    assert system.open == {LC}  # and it stays off
    devices.set_switches(port_key(F1), input=True)
    assert state(devices)[F1] == "connected" and system.open == {F1, LC}
    with pytest.raises(KeyError):
        devices.set_switches("nope", input=True)


def test_an_unplugged_device_is_closed_and_opens_again_when_it_comes_back(system, devices, caplog):
    system.names = [F1]
    devices.sync()
    system.names = []
    with caplog.at_level(logging.INFO):
        devices.sync()
        devices.sync()
    assert state(devices) == {F1: "missing"} and system.open == set() and system.ports[0].closed
    assert sum("is gone" in r.getMessage() for r in caplog.records) == 1  # a change is logged, not every look
    (d,) = devices.status()["devices"]
    assert d["reconnect"] is None
    system.names = [F1]
    devices.sync()
    (d,) = devices.status()["devices"]
    assert d["state"] == "connected" and len(system.ports) == 2
    assert d["reconnect"]["lost"] is not None and d["reconnect"]["back"] >= d["reconnect"]["lost"]


def test_a_device_listed_at_the_start_is_not_a_reconnect_and_one_missing_at_the_start_is(store, system, devices):
    store.settings.midi_devices[port_key(LC)] = MidiDeviceSetting(name=LC)  # known from the last run, not plugged in
    system.names = [F1]
    devices.sync()
    got = {d["name"]: d for d in devices.status()["devices"]}
    assert got[F1]["reconnect"] is None and got[LC]["state"] == "missing"
    system.names = [F1, LC]
    devices.sync()
    got = {d["name"]: d for d in devices.status()["devices"]}
    assert got[LC]["state"] == "connected" and got[LC]["reconnect"]["lost"] is None  # "not found at start · connected …"


def test_a_failing_open_is_an_error_with_the_reason_logged_once_and_retried(system, devices, caplog, monkeypatch):
    monkeypatch.setattr(module, "_winmm_indices", lambda: False)
    system.names, system.fail = [F1], {F1}
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            devices.sync()
    (d,) = devices.status()["devices"]
    assert (d["state"], d["error"]) == ("error", "MIDI port is in use")
    assert sum("failed to open" in r.getMessage() for r in caplog.records) == 1
    system.fail.clear()  # the other program let go
    devices.sync()
    (d,) = devices.status()["devices"]
    assert (d["state"], d["error"]) == ("connected", None) and d["reconnect"]["back"] is not None


def test_on_windows_a_failing_open_asks_whether_another_program_has_the_port(system, devices, monkeypatch):
    monkeypatch.setattr(module, "_winmm_indices", lambda: True)
    system.names, system.fail = [F1], {F1}
    devices.sync()
    assert devices.status()["devices"][0]["error"] == "in use by another program? (MIDI port is in use)"


def test_a_failed_listing_is_not_a_pulled_device(system, devices, monkeypatch):
    system.names = [F1]
    devices.sync()
    system.names = None  # the system couldn't say
    devices.sync()
    assert state(devices) == {F1: "connected"} and not system.ports[0].closed


def test_a_pulled_port_that_the_system_still_lists_without_a_name_is_no_port(monkeypatch):
    """CoreMIDI keeps a pulled port in the list of a running app, with no name (found live with a virtual port)."""
    from pitchcontrol.io import midi_in

    monkeypatch.setattr(midi_in.mido, "get_input_names", lambda: ["A", None, "", "B"])
    assert midi_in.list_midi_inputs() == ["A", "B"] and midi_in.list_midi_inputs_checked() == ["A", "B"]


def test_a_renumbered_port_is_the_same_device_on_windows(store, system, devices, monkeypatch):
    monkeypatch.setattr("pitchcontrol.io.midi_in._winmm_indices", lambda: True)
    system.names = ["LCXL3 1 MIDI In 0"]
    devices.sync()
    system.names = ["Some Keyboard 0", "LCXL3 1 MIDI In 1"]  # another device plugged in: the controller is now … 1
    devices.sync()
    got = {d["key"]: d for d in devices.status()["devices"]}
    assert got["lcxl3 1 midi in"]["state"] == "connected" and got["lcxl3 1 midi in"]["name"] == "LCXL3 1 MIDI In 1"
    assert not system.ports[0].closed and len(system.ports) == 2  # the keyboard is new; the controller's port was kept


def test_remove_takes_only_a_device_that_is_not_plugged_in(store, system, devices):
    system.names = [F1]
    devices.sync()
    with pytest.raises(ValueError):
        devices.remove(port_key(F1))
    system.names = []
    devices.sync()
    devices.remove(port_key(F1))
    assert devices.status()["devices"] == [] and saved(store) is None
    with pytest.raises(KeyError):
        devices.remove(port_key(F1))
    system.names = [F1]
    devices.sync()
    assert state(devices) == {F1: "connected"}  # seen again: added again


# -- the stream


def test_every_message_of_every_device_reaches_every_subscriber_with_the_device(system, devices):
    system.names = [F1, LC]
    seen, other = [], []
    devices.subscribe(lambda key, name, msg: seen.append((key, name, msg.type)))
    devices.subscribe(lambda key, name, msg: 1 / 0)  # a subscriber that fails stops nobody
    devices.subscribe(lambda key, name, msg: other.append(name))
    devices.sync()
    system.port(F1).send(mido.Message("control_change", channel=0, control=1, value=2))
    system.port(LC).send(mido.Message("note_on", channel=1, note=36, velocity=90))
    assert seen == [(port_key(F1), F1, "control_change"), (port_key(LC), LC, "note_on")] and other == [F1, LC]
    got = {d["name"]: d for d in devices.status()["devices"]}
    assert got[F1]["received"] == 1 and got[LC]["received"] == 1 and got[F1]["age"] is not None


def test_the_stream_reaches_the_mapping_the_routes_and_the_monitor_with_the_device_name(store, system):
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    store.controller = Controller(name="t", channel=1, mappings=[MidiMapping(number=7, macro="Fog Machine", mode="momentary")])
    engine.restart_midi()
    system.names = [F1, LC]
    engine.midi_devices.sync()
    system.port(F1).send(mido.Message("control_change", channel=0, control=7, value=127))  # the mapping listens to every device
    system.port(LC).send(mido.Message("control_change", channel=4, control=9, value=33))
    assert engine.macros.on("Fog Machine")
    assert engine.midi_routes.value(port_key(LC), 5, MidiChannel(type="cc", number=9)) == scale7(33)
    recent = engine.midi_status()["recent"]  # newest first
    assert [(e["device"], e["macro"]) for e in recent] == [(LC, None), (F1, "Fog Machine")]
    assert recent[0]["note"] == "CC 9 not mapped"
    assert engine.midi_status()["connected_devices"] == 2
    system.port(F1).send(mido.Message("clock"))
    assert engine.midi_status()["received"] == 2
    assert len(system.ports) == 2  # nothing else opened a port
    engine.stop()
    assert system.open == set()


def test_the_monitor_records_also_when_no_mapping_is_active(store, system):
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    store.controller = None
    engine.restart_midi()
    system.names = [F1]
    engine.midi_devices.sync()
    system.port(F1).send(mido.Message("control_change", channel=0, control=1, value=2))
    (e,) = engine.midi_status()["recent"]
    assert (e["device"], e["note"]) == (F1, "no controller selected")
    engine.stop()


# -- the setting of an earlier version


def test_the_midi_port_of_an_earlier_version_turns_that_devices_in_on_once(store, system, devices):
    store.settings.midi_devices[port_key(LC)] = MidiDeviceSetting(name=LC, input=False)
    store.settings.midi_input = "lcxl3"  # a part of the name, as the controller file had it
    system.names = [LC, F1]
    devices.sync()
    assert store.settings.midi_devices[port_key(LC)].input is True and store.settings.midi_input is None
    assert state(devices) == {LC: "connected", F1: "connected"}
    devices.set_switches(port_key(LC), input=False)  # the user's later choice stands: the setting is gone
    devices.sync()
    assert state(devices)[LC] == "off"
    assert "midi_input" not in json.loads(store.machine_path.read_text(encoding="utf-8"))


def test_a_port_of_an_earlier_version_that_is_not_plugged_in_is_listed_as_missing(store, system, devices):
    store.settings.midi_input = "Launch Control XL 3"
    system.names = []
    devices.sync()
    (d,) = devices.status()["devices"]
    assert (d["name"], d["input"], d["state"]) == ("Launch Control XL 3", True, "missing")
    system.names = ["Launch Control XL 3"]
    devices.sync()
    assert state(devices) == {"Launch Control XL 3": "connected"}


def test_the_controller_files_port_match_no_longer_chooses_a_port(store, system):
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    store.controller = Controller(name="t", port_match="lcxl3", mappings=[])
    engine.restart_midi()
    system.names = [F1]
    engine.midi_devices.sync()
    assert state(engine.midi_devices) == {F1: "connected"}  # every device that is on is listened to, whatever the file says
    engine.stop()


# -- the endpoints


def test_the_endpoints_list_switch_and_remove(store, system):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    system.names = [F1]
    engine.midi_devices.sync()
    got = client.get("/api/midi/devices").json()
    assert got["connected_devices"] == 1 and got["devices"][0]["key"] == port_key(F1) and got["devices"][0]["input"] is True
    got = client.put(f"/api/midi/devices/{port_key(F1)}", json={"input": False}).json()
    assert got["devices"][0]["state"] == "off" and got["connected_devices"] == 0 and system.open == set()
    assert client.put("/api/midi/devices/nope", json={"input": True}).status_code == 404
    assert client.delete(f"/api/midi/devices/{port_key(F1)}").status_code == 409  # plugged in
    system.names = []
    engine.midi_devices.sync()
    assert client.delete(f"/api/midi/devices/{port_key(F1)}").json()["devices"] == []
    assert client.delete(f"/api/midi/devices/{port_key(F1)}").status_code == 404


def test_saving_the_settings_from_the_page_leaves_the_devices_alone(store, system):
    engine = Engine(store, enable_hardware=False)
    client = TestClient(create_app(engine))
    system.names = [F1]
    engine.midi_devices.sync()
    page = client.get("/api/settings").json()
    page["midi_devices"] = {}  # a page that doesn't know the list (or an old one)
    page["midi_input"] = "something"
    assert client.put("/api/settings", json=page).status_code == 200
    assert port_key(F1) in store.settings.midi_devices and store.settings.midi_input is None


def test_a_change_from_the_page_uses_the_last_look_and_lists_nothing_itself(store, system, devices, monkeypatch):
    # item 92: on macOS a list read on a request thread shows only the devices of the start and would close the others
    system.names = [F1, LC]
    devices.sync()
    assert devices.names() == [F1, LC]

    def must_not_list():
        raise AssertionError("listed on the page's thread")

    monkeypatch.setattr(module, "list_midi_inputs_checked", must_not_list)
    devices.set_switches(port_key(LC), input=False)
    assert state(devices) == {F1: "connected", LC: "off"}


def test_the_names_are_none_before_the_first_look(devices):
    assert devices.names() is None


def test_the_watchdog_pause_ends_at_once_when_stopped():
    import threading

    stop = threading.Event()
    stop.set()
    assert module.wait_between_looks(stop, 5.0) is True  # also with the run loop on macOS: no 5 s wait at a stop
