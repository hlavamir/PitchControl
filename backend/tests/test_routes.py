"""Routes (item 58): live input copied onto output channels, in three layers: the app's output → routes → manual overrides."""

import json

import pytest
from fastapi.testclient import TestClient

from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.routes import Route, Routes
from pitchcontrol.io.live_input import DMX_KEY, LiveInput, artnet_key
from pitchcontrol.server.app import create_app


def route(**fields) -> Route:
    return Route(**{"kind": "artnet", "artnet_universe": 1, "first_input": 1, "count": 1, "universe": 0, "first_output": 1, **fields})


@pytest.fixture
def engine(store):
    return Engine(store, enable_hardware=False)


def send(engine: Engine, universe: int, values: dict[int, int] | bytes, key: str | None = None) -> None:
    """What Art-Net universe ``universe`` carries now (channel -> value, or the bytes)."""
    if isinstance(values, dict):
        data = bytearray(512)
        for ch, v in values.items():
            data[ch - 1] = v
        values = bytes(data)
    engine.live.store.put(key or artnet_key(universe), values, "10.0.0.5")


# -- the model


def test_a_route_must_fit_its_universes():
    assert route(first_input=512, count=1, first_output=512).count == 1
    assert route(first_input=1, count=512, first_output=1).count == 512
    for bad in ({"first_input": 512, "count": 2}, {"first_output": 511, "count": 3}, {"count": 0}, {"count": 513}, {"first_output": 0}, {"artnet_universe": -1}):
        with pytest.raises(ValueError):
            route(**bad)


def test_routes_get_ids_and_the_list_is_replaced_as_a_whole():
    routes = Routes()
    routes.set_all([route(), route(), route(id="mine")])
    ids = [r.id for r in routes.all()]
    assert len(set(ids)) == 3 and "mine" in ids and routes.version == 1
    routes.set_all([route(id="a"), route(id="a")])  # a copied row gets a new id
    assert len({r.id for r in routes.all()}) == 2
    with pytest.raises(ValueError):
        routes.set_all([route() for _ in range(300)])


# -- the three layers


def test_a_manual_override_over_a_route_over_a_fixture(engine):
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 255  # the v3's master at address 100: the app's own output
    engine.routes.set_all([route(artnet_universe=1, first_input=10, count=1, universe=0, first_output=100)])

    engine.tick(1 / 40)
    assert engine.universes[0][99] == 255  # the source has never sent: the app's output stays

    send(engine, 1, {10: 77})
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 77  # the route wins over the fixture

    engine.overrides.set(0, 100, 9)
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 9  # a manual value wins over the route
    assert len(engine.routes.all()) == 1  # and doesn't delete it

    send(engine, 1, {10: 88})
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 9  # the override holds while the route follows underneath

    engine.overrides.set(0, 100, None)
    engine.tick(1 / 40)
    assert engine.universes[0][99] == 88  # released: the route's (latest) value shows again


def test_a_single_channel_and_a_whole_universe(engine):
    pattern = bytes(i % 256 for i in range(512))
    send(engine, 4, pattern)
    engine.routes.set_all([route(artnet_universe=4, first_input=1, count=512, universe=2, first_output=1), route(artnet_universe=4, first_input=300, count=1, universe=3, first_output=512)])
    engine.tick(1 / 40)
    assert bytes(engine.universes[2]) == pattern  # 512 channels, a whole universe in one row
    assert engine.universes[3][511] == 299 % 256 and engine.universes[3][0] == 0  # one channel, count 1


def test_a_block_goes_to_another_place_in_another_universe(engine):
    send(engine, 7, {5: 50, 6: 60, 7: 70, 8: 80})
    engine.routes.set_all([route(artnet_universe=7, first_input=6, count=2, universe=1, first_output=101)])
    engine.tick(1 / 40)
    assert list(engine.universes[1][99:104]) == [0, 60, 70, 0, 0]


def test_the_dmx_input_is_a_source_of_its_own(engine):
    engine.live.store.put(DMX_KEY, bytes([1, 2, 3]), "COM9")
    send(engine, 0, {1: 200})  # Art-Net universe 0 is something else
    engine.routes.set_all([Route(kind="dmx", first_input=2, count=2, universe=2, first_output=10)])
    engine.tick(1 / 40)
    assert list(engine.universes[2][9:12]) == [2, 3, 0]


def test_a_route_that_is_off_changes_nothing_and_deleting_it_lets_go(engine):
    send(engine, 1, {1: 40})
    engine.routes.set_all([route(enabled=False, universe=2, first_output=5)])
    engine.tick(1 / 40)
    assert 2 not in engine.universes or engine.universes[2][4] == 0
    engine.routes.set_all([route(universe=2, first_output=5)])
    engine.tick(1 / 40)
    assert engine.universes[2][4] == 40
    engine.routes.set_all([])
    engine.tick(1 / 40)
    assert 2 not in engine.universes  # the app's own output is back


def test_the_last_value_stays_when_the_packets_stop(engine):
    clock = [0.0]
    engine.live = LiveInput(clock=lambda: clock[0])
    send(engine, 1, {1: 123})
    engine.routes.set_all([route(universe=2, first_output=1)])
    engine.tick(1 / 40)
    assert engine.universes[2][0] == 123
    clock[0] += 3600  # an hour of silence
    for _ in range(5):
        engine.tick(1 / 40)
    assert engine.universes[2][0] == 123  # an overridden channel stays overridden
    state = engine.state()["routes"][0]
    assert state["seen"] and state["age"] == 3600 and state["pps"] == 0


def test_later_routes_win_and_the_overlap_is_reported(engine):
    send(engine, 1, {1: 10, 2: 11, 3: 12})
    send(engine, 2, {1: 90, 2: 91})
    engine.routes.set_all([
        route(id="a", artnet_universe=1, first_input=1, count=3, universe=0, first_output=20),
        route(id="b", artnet_universe=2, first_input=1, count=2, universe=0, first_output=21),
        route(id="c", artnet_universe=2, first_input=1, count=1, universe=1, first_output=21),  # another universe: no overlap
    ])
    engine.tick(1 / 40)
    assert list(engine.universes[0][19:23]) == [10, 90, 91, 0]  # b covers 21 and 22 and comes later
    assert engine.routes.overlaps() == [{"universe": 0, "first": 21, "last": 22, "routes": ["a", "b"]}]
    assert engine.state()["route_overlaps"] == engine.routes.overlaps()
    # a disabled route covers nothing
    engine.routes.set_all([route(id="a", count=3, first_output=20), route(id="b", enabled=False, count=2, first_output=21)])
    assert engine.routes.overlaps() == []


def test_overlaps_split_where_the_routes_differ(engine):
    engine.routes.set_all([
        route(id="a", count=4, first_output=1),
        route(id="b", count=2, first_output=1),
        route(id="c", count=2, first_output=3),
    ])
    assert engine.routes.overlaps() == [
        {"universe": 0, "first": 1, "last": 2, "routes": ["a", "b"]},
        {"universe": 0, "first": 3, "last": 4, "routes": ["a", "c"]},
    ]


# -- saved across restarts


def test_routes_are_saved_and_restored(store, engine):
    engine.routes.set_all([route(name="Console", artnet_universe=5, first_input=3, count=8, universe=2, first_output=17)])
    engine._autosave_routes(force=True)
    saved = json.loads((store.state_dir / "routes.json").read_text(encoding="utf-8"))
    assert saved["routes"][0]["name"] == "Console" and "app_version" in saved
    again = Engine(store, enable_hardware=False)
    (r,) = again.routes.all()
    assert (r.name, r.artnet_universe, r.first_input, r.count, r.universe, r.first_output) == ("Console", 5, 3, 8, 2, 17)
    assert r.id  # and it works again without anything being re-entered
    send(again, 5, {3: 33, 10: 100})
    again.tick(1 / 40)
    assert again.universes[2][16] == 33 and again.universes[2][23] == 100


def test_a_broken_routes_file_starts_empty(store):
    (store.state_dir).mkdir(parents=True, exist_ok=True)
    (store.state_dir / "routes.json").write_text('{"routes": [{"count": 900}]}', encoding="utf-8")
    assert len(Engine(store, enable_hardware=False).routes) == 0


def test_autosave_writes_within_a_second_of_a_change(store, engine):
    engine.routes.set_all([route()])
    engine.frame = 0
    engine.tick(1 / 40)  # frame 0 is a multiple of the frame rate
    assert (store.state_dir / "routes.json").exists()


# -- the endpoint


def test_endpoint_lists_and_replaces_the_routes(engine):
    client = TestClient(create_app(engine))
    assert client.get("/api/routes").json() == {"routes": [], "overlaps": []}
    body = {"routes": [{"name": "a", "artnet_universe": 3, "first_input": 1, "count": 16, "universe": 1, "first_output": 33}]}
    got = client.put("/api/routes", json=body).json()
    assert got["routes"][0]["id"] and got["routes"][0]["seen"] is False and got["routes"][0]["age"] is None
    send(engine, 3, {1: 5})
    assert client.get("/api/routes").json()["routes"][0]["seen"] is True
    assert client.put("/api/routes", json={"routes": [{"count": 513}]}).status_code == 422
    assert len(engine.routes.all()) == 1  # a refused list changes nothing
    assert client.put("/api/routes", json={"routes": []}).json()["routes"] == []


def test_one_route_at_a_time_two_edits_never_undo_each_other(engine):
    client = TestClient(create_app(engine))
    added = client.post("/api/routes", json={"count": 512, "enabled": False}).json()["routes"]
    rid = added[0]["id"]
    client.post("/api/routes", json={"name": "second"})
    # quick edits of different fields of one route, each from its own request
    client.patch(f"/api/routes/{rid}", json={"name": "Console"})
    client.patch(f"/api/routes/{rid}", json={"enabled": True})
    got = client.patch(f"/api/routes/{rid}", json={"artnet_universe": 9, "universe": 2}).json()["routes"]
    assert [r["name"] for r in got] == ["Console", "second"]
    first = got[0]
    assert first["enabled"] and first["artnet_universe"] == 9 and first["universe"] == 2 and first["count"] == 512
    # moving a first channel up shrinks the count so the block still fits; an explicit count that doesn't fit is refused
    assert client.patch(f"/api/routes/{rid}", json={"first_output": 500}).json()["routes"][0]["count"] == 13
    assert client.patch(f"/api/routes/{rid}", json={"count": 30}).status_code == 422
    assert client.patch(f"/api/routes/{rid}", json={"id": "other", "first_input": 7}).json()["routes"][0]["id"] == rid  # the id stays
    assert client.patch("/api/routes/nope", json={"name": "x"}).status_code == 404
    # removing one leaves the other
    assert [r["name"] for r in client.delete(f"/api/routes/{rid}").json()["routes"]] == ["second"]
    assert client.delete(f"/api/routes/{rid}").status_code == 404
    assert client.post("/api/routes", json={"count": 0}).status_code == 422
