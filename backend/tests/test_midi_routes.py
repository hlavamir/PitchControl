"""MIDI routes (item 59): CC and note scaling, Learn per channel, the overlap notice, the constant fallback, the layers."""

import mido
import pytest
from fastapi.testclient import TestClient

from pitchcontrol.config.models import Controller, MidiDeviceSetting, MidiMapping
from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.routes import MidiChannel, Route
from pitchcontrol.io.midi_devices import _Runtime
from pitchcontrol.io.midi_in import MidiInput, port_key
from pitchcontrol.io.midi_routes import MidiRouteHub, scale14, scale7
from pitchcontrol.server.app import create_app

DEVICE = "Fake Pad 1 MIDI In 0"
KEY = port_key(DEVICE)


def cc(hub, number, value, channel=0, device=KEY):
    hub.handle(device, mido.Message("control_change", channel=channel, control=number, value=value))


def note(hub, number, velocity=100, channel=0, device=KEY):
    hub.handle(device, mido.Message("note_on" if velocity else "note_off", channel=channel, note=number, velocity=velocity))


def midi_route(*channels: MidiChannel, **fields) -> Route:
    return Route(kind="midi", midi_device=DEVICE, midi_channel=1, count=len(channels), channels=list(channels), universe=2, first_output=1, **fields)


# -- scaling


def test_scaling_runs_0_to_255():
    assert [scale7(v) for v in (0, 1, 64, 126, 127)] == [0, 2, 129, 253, 255]
    assert [scale14(m, ll) for m, ll in ((0, 0), (127, 127), (64, 0), (0, 127))] == [0, 255, 128, 2]


def test_a_cc_a_14_bit_pair_and_a_note():
    hub = MidiRouteHub()
    cc7, cc14 = MidiChannel(type="cc", number=21), MidiChannel(type="cc14", number=1)
    velocity, onoff = MidiChannel(type="note", number=36), MidiChannel(type="note", number=37, note_mode="onoff")
    assert [hub.value(KEY, 1, s) for s in (cc7, cc14, velocity, onoff)] == [None] * 4  # nothing touched: nothing written

    cc(hub, 21, 127)
    assert hub.value(KEY, 1, cc7) == 255
    cc(hub, 21, 64)
    assert hub.value(KEY, 1, cc7) == 129

    cc(hub, 1, 127)  # the MSB alone
    assert hub.value(KEY, 1, cc14) == scale14(127, 0)
    cc(hub, 33, 127)  # and its LSB, 32 higher
    assert hub.value(KEY, 1, cc14) == 255

    note(hub, 36, 127)
    assert hub.value(KEY, 1, velocity) == 255
    note(hub, 36, 64)
    assert hub.value(KEY, 1, velocity) == 129  # the velocity of the last note
    note(hub, 36, 0)  # off (a note_off, or a note_on of velocity 0)
    assert hub.value(KEY, 1, velocity) == 0
    note(hub, 37, 30)
    assert hub.value(KEY, 1, onoff) == 255  # a soft note is still "on"
    hub.handle(KEY, mido.Message("note_off", channel=0, note=37))
    assert hub.value(KEY, 1, onoff) == 0


def test_a_control_keeps_its_last_value_and_is_told_apart_by_device_and_channel():
    hub = MidiRouteHub()
    spec = MidiChannel(type="cc", number=7)
    cc(hub, 7, 100)
    assert hub.value(KEY, 1, spec) == scale7(100)  # and keeps it for as long as nothing else comes
    assert hub.value(KEY, 1, spec) == scale7(100)
    assert hub.value(KEY, 2, spec) is None  # another MIDI channel
    assert hub.value(port_key("Other Device 2 MIDI In 0"), 1, spec) is None
    cc(hub, 7, 5, channel=1)  # the same CC on MIDI channel 2
    assert hub.value(KEY, 1, spec) == scale7(100) and hub.value(KEY, 2, spec) == scale7(5)


def test_a_constant_is_the_fallback_for_a_channel_no_control_drives():
    hub = MidiRouteHub()
    assert hub.value(KEY, 1, MidiChannel(type="const", value=200)) == 200
    assert hub.value(KEY, 1, MidiChannel(type="none")) is None


# -- the route model


def test_a_midi_route_has_one_input_per_output_channel():
    r = Route(kind="midi", count=3, channels=[MidiChannel(type="cc", number=9)])
    assert [c.type for c in r.channels] == ["cc", "none", "none"]  # padded to the count
    r = Route(kind="midi", count=1, channels=[MidiChannel(type="cc"), MidiChannel(type="note")])
    assert len(r.channels) == 1  # cut to the count
    assert Route(kind="artnet", count=2, channels=[MidiChannel()]).channels == []  # only a MIDI route has them
    for bad in ({"count": 65}, {"channels": [{"type": "cc14", "number": 40}]}, {"midi_channel": 17}, {"channels": [{"type": "cc", "number": 128}]}):
        with pytest.raises(ValueError):
            Route(**{"kind": "midi", "count": 2, **bad})


# -- Learn


def test_learn_takes_the_next_control_of_the_device_on_the_route_channel():
    clock = [0.0]
    hub = MidiRouteHub(lambda: clock[0])
    got = []
    hub.on_learned = lambda route, index, spec: got.append((route, index, spec))
    assert hub.set_learning("r1", DEVICE, 1, 2) == 1

    cc(hub, 40, 10, channel=4)  # another MIDI channel: heard, not taken
    cc(hub, 41, 10, device=port_key("Another Port 3 MIDI In 0"))  # another device: ignored
    hub.handle(KEY, mido.Message("note_off", channel=0, note=60))  # a release is no control
    hub.handle(KEY, mido.Message("pitchwheel", channel=0, pitch=100))
    assert got == []
    assert hub.status()["learn"]["heard"] == {"kind": "cc", "number": 40, "channel": 5}

    cc(hub, 21, 55)
    assert got == [("r1", 2, {"type": "cc", "number": 21})]
    assert hub.status()["learn"] is None and hub.status()["learned"]["number"] == 21
    cc(hub, 22, 55)
    assert len(got) == 1  # one control per Learn


def test_learn_takes_a_note_on_and_ends_by_itself():
    clock = [0.0]
    hub = MidiRouteHub(lambda: clock[0])
    got = []
    hub.on_learned = lambda *args: got.append(args)
    hub.set_learning("r1", DEVICE, 1, 0)
    note(hub, 48, 90)
    assert got == [("r1", 0, {"type": "note", "number": 48})]

    hub.set_learning("r1", DEVICE, 1, 1)
    clock[0] += 3600  # nobody moves anything
    assert hub.status()["learn"] is None
    cc(hub, 5, 5)
    assert len(got) == 1  # too late
    hub.set_learning("r1", DEVICE, 1, 1)
    assert hub.set_learning("r1", DEVICE, 1, 1, on=False) is None  # cancelled
    note(hub, 49, 90)
    assert len(got) == 1


# -- in the engine


@pytest.fixture
def engine(store):
    return Engine(store, enable_hardware=False)


def test_midi_channels_in_the_frame_in_three_layers(engine):
    engine.routes.set_all([midi_route(
        MidiChannel(type="cc", number=21), MidiChannel(type="note", number=40, note_mode="onoff"),
        MidiChannel(type="const", value=50), MidiChannel(type="none"), MidiChannel(type="cc", number=22),
    )])
    engine.tick(1 / 40)
    u = engine.universes[2]
    assert list(u[:5]) == [0, 0, 50, 0, 0]  # only the constant is written before anything moves

    cc(engine.midi_routes, 21, 127)
    note(engine.midi_routes, 40, 80)
    engine.tick(1 / 40)
    assert list(engine.universes[2][:5]) == [255, 255, 50, 0, 0]

    engine.overrides.set(2, 1, 9)  # a manual value wins over the route
    engine.tick(1 / 40)
    assert engine.universes[2][0] == 9
    cc(engine.midi_routes, 21, 64)
    engine.overrides.set(2, 1, None)
    engine.tick(1 / 40)
    assert engine.universes[2][0] == 129  # released: the route's latest value
    for _ in range(3):
        engine.tick(1 / 40)
    assert engine.universes[2][0] == 129  # and it stays while nothing moves


def test_a_midi_route_over_a_fixture_leaves_untouched_channels_alone(engine):
    engine.routes.set_all([Route(kind="midi", midi_device=DEVICE, count=2, universe=0, first_output=100, channels=[MidiChannel(type="cc", number=1), MidiChannel(type="cc", number=2)])])
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 255  # the v3's master at address 100: the app's output
    cc(engine.midi_routes, 1, 10)
    engine.tick(1 / 40)
    assert engine.universes[0][99] == scale7(10)
    assert engine.universes[0][100] == 0  # the second channel's control hasn't moved: not written (the fixture's value, 0, shows)


def test_a_route_without_a_device_or_switched_off_writes_nothing(engine):
    cc(engine.midi_routes, 21, 127)
    engine.routes.set_all([midi_route(MidiChannel(type="const", value=7), enabled=False), Route(kind="midi", count=1, universe=3, channels=[MidiChannel(type="const", value=9)])])
    engine.tick(1 / 40)
    assert 2 not in engine.universes and 3 not in engine.universes


def test_midi_routes_are_saved_and_restored(store, engine):
    engine.routes.set_all([midi_route(MidiChannel(type="cc14", number=3), MidiChannel(type="note", number=40, note_mode="onoff"), name="Pads")])
    engine._autosave_routes(force=True)
    (r,) = Engine(store, enable_hardware=False).routes.all()
    assert r.kind == "midi" and r.midi_device == DEVICE and r.name == "Pads"
    assert [(c.type, c.number, c.note_mode) for c in r.channels] == [("cc14", 3, "velocity"), ("note", 40, "onoff")]


# -- the app's MIDI mapping


def controller() -> Controller:
    return Controller(name="LCXL", port_match="Fake Pad", channel=13, mappings=[MidiMapping(type="cc", number=21, macro="Strobo Decay"), MidiMapping(type="note", number=40, macro="Fog Machine", channel=1)])


def test_the_overlap_notice_names_the_macros_the_mapping_drives_by_that_control(engine):
    midi = MidiInput(controller(), engine.macros)
    routes = [
        Route(id="a", kind="midi", midi_device=DEVICE, midi_channel=13, count=3, channels=[MidiChannel(type="cc", number=21), MidiChannel(type="cc", number=22), MidiChannel(type="note", number=40)]),
        Route(id="b", kind="midi", midi_device=DEVICE, midi_channel=1, count=2, channels=[MidiChannel(type="cc", number=21), MidiChannel(type="note", number=40)]),
        Route(id="c", kind="midi", midi_device="Another Port 2 MIDI In 0", midi_channel=13, count=1, channels=[MidiChannel(type="cc", number=21)]),
    ]
    engine.routes.set_all(routes)
    notices = engine.routes.midi_overlaps(midi)
    assert [(n["route"], n["index"], n["kind"], n["number"], n["macros"]) for n in notices] == [
        ("a", 0, "cc", 21, ["Strobo Decay"]),  # channel 13 is the controller's: CC 21 is mapped
        ("b", 1, "note", 40, ["Fog Machine"]),  # the note is mapped on channel 1 explicitly
        ("c", 0, "cc", 21, ["Strobo Decay"]),  # the mapping listens to every device (item 89): another device overlaps too
    ]  # CC 22 isn't mapped, route b's CC 21 is on channel 1 (the mapping is on 13)
    assert notices[0]["text"] == f"CC 21 on {DEVICE} also drives Strobo Decay in the MIDI mapping: both will react"
    assert engine.routes.midi_overlaps(MidiInput(None, engine.macros)) == []  # no controller: nothing to overlap with


def test_a_14_bit_pair_overlaps_with_its_second_half_too(engine):
    midi = MidiInput(controller(), engine.macros)
    engine.routes.set_all([Route(kind="midi", midi_device=DEVICE, midi_channel=13, count=1, channels=[MidiChannel(type="cc14", number=21)])])
    assert [n["number"] for n in engine.routes.midi_overlaps(midi)] == [21]  # CC 53 isn't mapped


# -- the devices (item 89)


def test_the_stream_reaches_the_routes_and_the_mapping_of_the_engine(engine):
    engine.enable_hardware = True
    engine.store.controller = controller()
    engine.restart_midi()
    engine._midi_message(KEY, DEVICE, mido.Message("control_change", channel=12, control=21, value=64))  # the first message only says where the fader is
    engine._midi_message(KEY, DEVICE, mido.Message("control_change", channel=12, control=21, value=127))
    assert engine.midi_routes.value(KEY, 13, MidiChannel(type="cc", number=21)) == 255
    assert engine.macros.control("Strobo Decay") == 1.0  # and the mapping still works


def test_the_status_says_what_the_devices_make_of_the_routes_devices(engine):
    engine.routes.set_all([midi_route(MidiChannel(type="cc", number=1), id="r1"), Route(kind="midi", id="r2", midi_device="Gone 3 MIDI In 0", midi_channel=1, count=1, channels=[MidiChannel()])])
    engine.store.settings.midi_devices[KEY] = MidiDeviceSetting(name=DEVICE, input=False)
    engine.midi_devices._rt[KEY] = _Runtime(state="off")  # plugged in, In off
    got = {d["device"]: d for d in engine.midi_routes_status()["devices"]}
    assert got[DEVICE]["open"] is False and "In switch is off" in got[DEVICE]["error"]
    assert "no MIDI port matches" in got["Gone 3 MIDI In 0"]["error"]
    engine.midi_devices._rt[KEY] = _Runtime(state="connected")
    engine.store.settings.midi_devices[KEY].input = True
    cc(engine.midi_routes, 1, 5)
    got = {d["device"]: d for d in engine.midi_routes_status()["devices"]}
    assert got[DEVICE]["open"] is True and got[DEVICE]["error"] is None and got[DEVICE]["received"] == 1
    assert engine.routes.status({}, engine.midi_routes_status())[0]["midi_open"] is True


# -- the endpoints


def test_endpoints_for_a_channel_and_for_learn(engine):
    client = TestClient(create_app(engine))
    rid = client.post("/api/routes", json={"kind": "midi", "midi_device": DEVICE, "count": 3}).json()["routes"][0]["id"]
    got = client.get("/api/routes").json()
    assert [c["type"] for c in got["routes"][0]["channels"]] == ["none"] * 3
    assert got["midi_notices"] == []

    out = client.patch(f"/api/routes/{rid}/channels/1", json={"type": "cc", "number": 21}).json()["routes"][0]["channels"]
    assert (out[1]["type"], out[1]["number"]) == ("cc", 21) and out[0]["type"] == "none"
    assert client.patch(f"/api/routes/{rid}/channels/3", json={"type": "cc"}).status_code == 404
    assert client.patch(f"/api/routes/{rid}/channels/0", json={"type": "cc14", "number": 99}).status_code == 422
    assert client.patch(f"/api/routes/{rid}", json={"count": 5}).json()["routes"][0]["channels"][1]["number"] == 21  # a longer route keeps its inputs
    assert len(client.patch(f"/api/routes/{rid}", json={"count": 2}).json()["routes"][0]["channels"]) == 2

    assert client.post(f"/api/routes/{rid}/learn", json={"index": 5}).status_code == 404
    assert client.post("/api/routes/nope/learn", json={"index": 0}).status_code == 404
    assert client.post(f"/api/routes/{rid}/learn", json={"index": 0}).json()["learn_id"] == 1
    state = engine.state()
    assert state["io"]["midi_routes"]["learn"]["route"] == rid
    cc(engine.midi_routes, 30, 100)  # the controller moves
    assert engine.routes.all()[0].channels[0].number == 30 and engine.routes.all()[0].channels[0].type == "cc"
    assert engine.state()["io"]["midi_routes"]["learn"] is None
    assert client.post(f"/api/routes/{rid}/learn", json={"index": 0, "on": False}).json()["learn_id"] is None

    art = client.post("/api/routes", json={"kind": "artnet"}).json()["routes"][1]["id"]
    assert client.post(f"/api/routes/{art}/learn", json={"index": 0}).status_code == 404  # only a MIDI route learns
    noname = client.post("/api/routes", json={"kind": "midi", "count": 1}).json()["routes"][2]["id"]
    assert client.post(f"/api/routes/{noname}/learn", json={"index": 0}).status_code == 409


def test_learn_refuses_a_device_whose_in_is_off(engine):
    client = TestClient(create_app(engine))
    engine.routes.set_all([midi_route(MidiChannel(), id="r1")])
    engine.store.settings.midi_devices[KEY] = MidiDeviceSetting(name=DEVICE, input=False)
    assert client.post("/api/routes/r1/learn", json={"index": 0}).status_code == 409
    engine.store.settings.midi_devices[KEY].input = True
    assert client.post("/api/routes/r1/learn", json={"index": 0}).json()["learn_id"] == 1
