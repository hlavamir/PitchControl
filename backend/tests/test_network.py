"""Other devices on the network: the switch, the PIN, and the listeners (``server/network.py``)."""

import json
import socket
import time
import urllib.request
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pitchcontrol.config.models import DEFAULT_PORT, NetworkSettings
from pitchcontrol.engine.engine import Engine
from pitchcontrol.server.app import create_app
from pitchcontrol.server.network import COOKIE, FAILS_BEFORE_LOCK, Network

PHONE = ("192.168.1.50", 50000)  # a device on the network
PIN = "4711"


@pytest.fixture
def app(store):
    return create_app(Engine(store, enable_hardware=False))


def set_network(store, **fields):
    store.settings = store.settings.model_copy(update={"network": NetworkSettings(**fields)})


def phone(app) -> TestClient:
    return TestClient(app, client=PHONE)


def local(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))


def refused_websocket(client: TestClient) -> bool:
    try:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
    except WebSocketDisconnect:
        return True
    return False


def test_the_switch_is_off_by_default(store):
    assert store.settings.network == NetworkSettings(enabled=False, port=DEFAULT_PORT, pin="")


def test_switch_off_refuses_other_addresses_and_serves_this_computer(store, app):
    assert not store.settings.network.enabled
    for path in ("/api/state", "/api/settings", "/"):
        assert phone(app).get(path).status_code == 403, path
    assert phone(app).put("/api/settings", json={}).status_code == 403
    assert refused_websocket(phone(app))
    assert local(app).get("/api/state").status_code == 200
    assert not refused_websocket(local(app))
    # the loopback address in its IPv6 forms is this computer too
    for host in ("::1", "::ffff:127.0.0.1"):
        assert TestClient(app, client=(host, 1)).get("/api/state").status_code == 200


def test_on_without_pin_lets_other_addresses_in(store, app):
    set_network(store, enabled=True)
    assert phone(app).get("/api/state").status_code == 200
    assert phone(app).get("/api/settings").status_code == 200
    assert not refused_websocket(phone(app))


def test_on_with_pin_refuses_without_the_cookie(store, app):
    set_network(store, enabled=True, pin=PIN)
    client = phone(app)
    api = client.get("/api/state")
    assert api.status_code == 401 and api.json() == {"detail": "PIN needed"}
    page = client.get("/")
    assert page.status_code == 401 and 'name="pin"' in page.text and "text/html" in page.headers["content-type"]
    assert client.get("/assets/x.js").status_code == 401
    assert refused_websocket(client)
    # a wrong PIN, an empty one and a guessed cookie don't open it
    assert client.post("/_pin", data={"pin": "0000"}).status_code == 401
    assert client.post("/_pin", data={}).status_code == 401
    assert COOKIE not in client.cookies
    client.cookies.set(COOKIE, PIN)
    assert client.get("/api/state").status_code == 401 and refused_websocket(client)


def test_on_with_pin_lets_the_device_in_with_the_cookie(store, app):
    set_network(store, enabled=True, pin=PIN)
    client = phone(app)
    answer = client.post("/_pin", data={"pin": PIN}, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == "/"
    cookie = answer.headers["set-cookie"].lower()
    assert COOKIE in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/state").status_code == 200
    assert not refused_websocket(client)
    with client.websocket_connect("/ws") as ws:
        assert "fixtures" in json.dumps(ws.receive_json())
    # another device has no cookie; a changed PIN ends the old cookie's use
    assert phone(app).get("/api/state").status_code == 401
    set_network(store, enabled=True, pin="987654")
    assert client.get("/api/state").status_code == 401 and refused_websocket(client)


def test_this_computer_is_never_asked_for_the_pin(store, app):
    set_network(store, enabled=True, pin=PIN)
    assert local(app).get("/api/state").status_code == 200
    assert local(app).get("/").status_code in (200, 404)  # 404: no built frontend in the test
    assert not refused_websocket(local(app))
    # the computer's own address on the network is this computer
    app.state.network._own = {"192.168.1.5"}
    assert TestClient(app, client=("192.168.1.5", 1)).get("/api/state").status_code == 200


def test_the_pin_page_is_only_there_with_the_switch_on(store, app):
    assert phone(app).post("/_pin", data={"pin": PIN}).status_code == 403  # off: not even the PIN page


def test_a_device_that_guesses_waits(store, app):
    set_network(store, enabled=True, pin=PIN)
    now = [1000.0]
    app.state.network.clock = lambda: now[0]
    client = phone(app)
    for _ in range(FAILS_BEFORE_LOCK):
        assert client.post("/_pin", data={"pin": "0000"}).status_code == 401
    locked = client.post("/_pin", data={"pin": PIN})  # even the right PIN waits
    assert locked.status_code == 429 and "Try again" in locked.text
    now[0] += 31
    assert client.post("/_pin", data={"pin": PIN}, follow_redirects=False).status_code == 303
    # another address is not held up by it
    for _ in range(FAILS_BEFORE_LOCK):
        TestClient(app, client=("192.168.1.77", 1)).post("/_pin", data={"pin": "1111"})
    assert TestClient(app, client=("192.168.1.78", 1)).post("/_pin", data={"pin": "1111"}).status_code == 401


def test_the_network_settings_belong_to_this_computer(store, app):
    set_network(store, enabled=True, pin=PIN)
    device = phone(app)
    device.post("/_pin", data={"pin": PIN})
    for call in (lambda c: c.get("/api/network"), lambda c: c.put("/api/network", json={"enabled": False}), lambda c: c.post("/api/open-data-folder"), lambda c: c.post("/api/open-browser")):
        assert call(device).status_code == 403
    assert device.get("/api/app-info").json()["local"] is False
    assert local(app).get("/api/app-info").json()["local"] is True
    # the PIN doesn't come out with the settings, and a page saving them can't change the network section
    got = device.get("/api/settings").json()
    assert "network" not in got
    body = {**got, "network": {"enabled": False, "port": 9000, "pin": ""}}
    assert device.put("/api/settings", json=body).status_code == 200
    assert store.settings.network == NetworkSettings(enabled=True, pin=PIN)


def test_put_network_validates_saves_and_applies(store, app):
    this = local(app)
    assert this.get("/api/network").json() == {"enabled": False, "port": DEFAULT_PORT, "pin": "", "listening": False, "error": None, "addresses": []}
    for bad in ("123", "123456789", "12a4", "٤٤٤٤"):  # too short, too long, a letter, Arabic-Indic digits
        answer = this.put("/api/network", json={"enabled": True, "pin": bad})
        assert answer.status_code == 422 and "4 to 8 digits" in answer.json()["detail"], bad
    assert this.put("/api/network", json={"enabled": True, "port": 80}).status_code == 422
    assert not store.settings.network.enabled
    app.state.network.addresses = lambda: []  # no adapters in the test; the listening itself is tested below
    answer = this.put("/api/network", json={"enabled": True, "port": 9123, "pin": "246810"})
    assert answer.status_code == 200 and answer.json()["enabled"] and answer.json()["port"] == 9123
    assert store.settings.network == NetworkSettings(enabled=True, port=9123, pin="246810")
    saved = json.loads(store.machine_path.read_text(encoding="utf-8"))  # per computer: in machine.json
    assert saved["network"] == {"enabled": True, "port": 9123, "pin": "246810"}


def test_is_local():
    net = Network(None, lambda: NetworkSettings())
    net._own = {"192.168.1.5"}
    assert all(net.is_local(h) for h in ("127.0.0.1", "127.0.0.5", "::1", "::ffff:127.0.0.1", "192.168.1.5", None, "testclient"))
    assert not any(net.is_local(h) for h in ("192.168.1.50", "10.0.0.2", "fe80::1%eth0", "8.8.8.8"))


# ---------------------------------------------------------------------------- the listeners


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch(port: int, path: str = "/api/state") -> int:
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3).status
    except HTTPError as exc:
        return exc.code


def refuses_connections(port: int) -> bool:
    try:
        fetch(port)
    except OSError:
        return True
    return False


def wait_until(condition, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_the_listeners_follow_the_switch_and_never_move_the_port(store, app):
    port = free_port()
    set_network(store, enabled=False, port=port)
    net = Network(app, lambda: store.settings.network, addresses=lambda: [("Test", "127.0.0.1")])
    try:
        net.sync()
        assert net.status()["addresses"] == [] and not net.status()["listening"]  # off: nothing listens, nothing is listed
        assert refuses_connections(port)

        set_network(store, enabled=True, port=port)
        net.sync()
        status = net.status()
        assert status["listening"] and status["error"] is None
        assert status["addresses"] == [{"name": "Test", "ip": "127.0.0.1", "url": f"http://127.0.0.1:{port}", "listening": True}]
        assert wait_until(lambda: fetch(port) == 200)

        set_network(store, enabled=False, port=port)  # off again: stops at once, no restart of the app
        net.sync()
        assert not net.status()["listening"]
        assert refuses_connections(port)
    finally:
        net.stop()


def test_a_port_that_is_taken_is_reported_and_kept(store, app):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        set_network(store, enabled=True, port=port)
        net = Network(app, lambda: store.settings.network, addresses=lambda: [("Test", "127.0.0.1")])
        try:
            net.sync()
            status = net.status()
            assert not status["listening"]
            assert f"Port {port} is already used by another program" in status["error"]
            assert status["port"] == port  # not moved
            assert net._listeners == {}
        finally:
            net.stop()
    # the program gives the port back: the next sync takes it, on the same port
    net = Network(app, lambda: store.settings.network, addresses=lambda: [("Test", "127.0.0.1")])
    try:
        net.sync()
        assert net.status()["listening"] and net.status()["port"] == port
    finally:
        net.stop()


def test_a_new_port_moves_the_listener_and_a_gone_adapter_stops_it(store, app):
    first, second = free_port(), free_port()
    adapters = [("Test", "127.0.0.1")]
    set_network(store, enabled=True, port=first)
    net = Network(app, lambda: store.settings.network, addresses=lambda: adapters)
    try:
        net.sync()
        assert wait_until(lambda: fetch(first) == 200)
        set_network(store, enabled=True, port=second)
        net.sync()
        assert wait_until(lambda: fetch(second) == 200)
        assert refuses_connections(first)
        adapters.clear()  # the wifi went away
        net.sync()
        assert not net.status()["listening"]
    finally:
        net.stop()
