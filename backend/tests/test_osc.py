"""OSC out: the wire format, the file rules, the change detection, a real UDP round trip."""

import json
import socket
import struct
import time

import pytest
from conftest import SHIPPED_CONFIG

from pitchcontrol.config.models import OscSettings, OutputSettings
from pitchcontrol.io import osc
from pitchcontrol.io.osc import OscOutput, OscRoute, encode, parse_routes
from pitchcontrol.io.outputs import OutputManager

RGBA = OscRoute("color_a.rgba", "/color_a", "r")


def decode(message: bytes) -> tuple[str, str, bytes]:
    """(address, type tags, argument bytes) of one OSC message, checking the padding as it goes."""
    end = message.index(b"\x00")
    address = message[:end].decode("ascii")
    pos = (end // 4 + 1) * 4
    tag_end = message.index(b"\x00", pos)
    tags = message[pos:tag_end].decode("ascii")
    return address, tags, message[(tag_end // 4 + 1) * 4 :]


# -- the wire format


def test_rgba_is_one_osc_colour():
    msg = encode(RGBA, (1.0, 0.5, 0.0))
    assert msg == b"/color_a\x00\x00\x00\x00" + b",r\x00\x00" + bytes((255, 128, 0, 255))
    assert len(msg) % 4 == 0


def test_float_and_integer_single_channels():
    green_f = encode(OscRoute("color_b.g", "/b/green", "f"), (0.1, 0.25, 0.9))
    address, tags, body = decode(green_f)
    assert (address, tags) == ("/b/green", ",f")
    assert struct.unpack(">f", body)[0] == pytest.approx(0.25)
    blue_i = encode(OscRoute("color_a.b", "/a/blue", "i"), (0.1, 0.25, 1.0))
    address, tags, body = decode(blue_i)
    assert (address, tags) == ("/a/blue", ",i") and struct.unpack(">i", body)[0] == 255


def test_values_are_clipped():
    _, _, body = decode(encode(OscRoute("color_a.r", "/r", "i"), (1.7, 0, 0)))
    assert struct.unpack(">i", body)[0] == 255
    _, _, body = decode(encode(RGBA, (-1, 2, 0.5)))
    assert body == bytes((0, 255, 128, 255))


def test_address_padding_for_every_length():
    for n in range(1, 9):
        msg = encode(OscRoute("color_a.r", "/" + "x" * n, "f"), (0, 0, 0))
        assert len(msg) % 4 == 0
        assert decode(msg)[0] == "/" + "x" * n


# -- the file rules


def test_valid_entries_and_everything_else_ignored():
    routes, ignored = parse_routes(
        [
            {"what": "color_a.rgba", "address": "/a", "format": "r"},
            {"what": "color_b.g", "address": "/b/g", "format": "i"},
            {"what": "color_a.rgb", "address": "/a/rgb", "format": "f"},  # no .rgb
            {"what": "color_a.rgba", "address": "/a", "format": "f"},  # rgba only as r
            {"what": "color_a.r", "address": "/a/r", "format": "r"},  # r/g/b only f or i
            {"what": "color_a.r", "address": "a/r", "format": "f"},  # not an address
            {"what": "color_a.r", "address": "/a r", "format": "f"},  # space
            {"what": "hue_a", "address": "/h", "format": "f"},
            {"what": "color_a.r", "address": "/a/r"},  # no format
            "nonsense",
        ]
    )
    assert [r.what for r in routes] == ["color_a.rgba", "color_b.g"]
    assert len(ignored) == 8 and all(text.startswith("entry ") for text in ignored)


def test_case_and_spaces_around_what_and_format_are_forgiven():
    routes, ignored = parse_routes([{"what": " Color_A.RGBA ", "address": "/a", "format": "R"}])
    assert routes == [OscRoute("color_a.rgba", "/a", "r")] and not ignored


def test_a_file_that_is_not_an_array_is_an_error():
    with pytest.raises(ValueError):
        parse_routes({"what": "color_a.r"})


def test_the_shipped_examples_are_all_valid():
    files = sorted((SHIPPED_CONFIG / "osc").glob("*.json"))
    assert len(files) >= 3
    for path in files:
        routes, ignored = parse_routes(json.loads(path.read_text(encoding="utf-8")))
        assert routes and not ignored, path.name


# -- sending: a real UDP round trip


@pytest.fixture
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.3)
    yield sock
    sock.close()


def drain(sock: socket.socket, wait: float = 0.4) -> list[bytes]:
    out = []
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            out.append(sock.recv(2048))
        except TimeoutError:
            break
    return out


def make_output(tmp_path, receiver, entries, name="test"):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    settings = OscSettings(enabled=True, host="127.0.0.1", port=receiver.getsockname()[1], file=name)
    out = OscOutput(settings, lambda n: path if n == name else None)
    out.start()
    return out, path


A = (1.0, 0.0, 0.0)
B = (0.0, 0.0, 1.0)


def test_messages_arrive_once_then_only_on_change_and_every_second(tmp_path, receiver, monkeypatch):
    out, _ = make_output(tmp_path, receiver, [{"what": "color_a.rgba", "address": "/a", "format": "r"}])
    try:
        out.send({"a": A, "b": B})
        got = drain(receiver)
        assert [decode(m)[0] for m in got] == ["/a"] and decode(got[0])[2] == bytes((255, 0, 0, 255))
        for _ in range(20):  # the same colour 20 more frames: nothing on the wire
            out.send({"a": A, "b": B})
        assert drain(receiver, 0.6) == []
        out.send({"a": (0.0, 1.0, 0.0), "b": B})  # a change goes out at once
        assert decode(drain(receiver)[0])[2] == bytes((0, 255, 0, 255))
        out._sent_at -= osc.REFRESH_S + 0.1  # a second later, unchanged: again
        out.send({"a": (0.0, 1.0, 0.0), "b": B})
        assert len(drain(receiver)) == 1
    finally:
        out.stop()


def test_the_worker_does_not_repeat_the_frame_by_itself(tmp_path, receiver):
    out, _ = make_output(tmp_path, receiver, [{"what": "color_a.rgba", "address": "/a", "format": "r"}])
    try:
        out.send({"a": A, "b": B})
        assert len(drain(receiver, 1.3)) == 1  # LatestFrameWorker alone would resend every 0.5 s
    finally:
        out.stop()


def test_a_and_b_go_to_their_own_addresses(tmp_path, receiver):
    entries = [
        {"what": "color_a.rgba", "address": "/a", "format": "r"},
        {"what": "color_b.rgba", "address": "/b", "format": "r"},
        {"what": "color_b.b", "address": "/b/blue", "format": "f"},
    ]
    out, _ = make_output(tmp_path, receiver, entries)
    try:
        out.send({"a": A, "b": B})
        got = {decode(m)[0]: decode(m) for m in drain(receiver)}
        assert set(got) == {"/a", "/b", "/b/blue"}
        assert got["/b"][2] == bytes((0, 0, 255, 255))
        assert struct.unpack(">f", got["/b/blue"][2])[0] == 1.0
    finally:
        out.stop()


def test_an_edited_file_is_picked_up_and_a_broken_one_keeps_the_last_good(tmp_path, receiver):
    out, path = make_output(tmp_path, receiver, [{"what": "color_a.rgba", "address": "/a", "format": "r"}])
    try:
        out.send({"a": A, "b": B})
        drain(receiver)
        path.write_text("[{broken", encoding="utf-8")
        out._checked -= 2
        out.send({"a": A, "b": B})
        assert out.file_error and "can't be read" in out.file_error
        assert [r.address for r in out.routes] == ["/a"]  # still sending the old messages
        path.write_text(json.dumps([{"what": "color_a.rgba", "address": "/other", "format": "r"}]), encoding="utf-8")
        out._checked -= 2
        out.send({"a": A, "b": B})
        assert out.file_error is None
        assert [decode(m)[0] for m in drain(receiver)] == ["/other"]
    finally:
        out.stop()


def test_missing_file_and_no_file(tmp_path, receiver):
    settings = OscSettings(enabled=True, port=receiver.getsockname()[1], file="nope")
    out = OscOutput(settings, lambda n: None)
    out.start()
    try:
        out.send({"a": A, "b": B})
        assert "isn't in the osc folder" in (out.file_error or "")
        assert drain(receiver, 0.3) == []
    finally:
        out.stop()
    none = OscOutput(OscSettings(enabled=True, file=""), lambda n: None)
    none.start()
    none.send({"a": A, "b": B})
    none.stop()
    assert none.file_error is None and none.routes == []


def test_a_receiver_that_can_not_be_found_is_an_error_not_a_crash(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps([{"what": "color_a.rgba", "address": "/a", "format": "r"}]), encoding="utf-8")
    out = OscOutput(OscSettings(enabled=True, host="no-such-host.invalid", file="f"), lambda n: path)
    out.start()
    try:
        out.send({"a": A, "b": B})
        time.sleep(0.8)
        assert out.status()["connected"] is False and "can't find" in (out.status()["error"] or "")
    finally:
        out.stop()


# -- the manager and the engine


def test_osc_restarts_alone_and_the_dmx_outputs_keep_running(tmp_path, receiver):
    path = tmp_path / "f.json"
    path.write_text("[]", encoding="utf-8")
    manager = OutputManager(OutputSettings(), lambda n: path)
    manager.start()
    try:
        assert manager.osc is None and manager.status()["osc"] is None
        on = OutputSettings(osc=OscSettings(enabled=True, port=receiver.getsockname()[1], file="f"))
        manager.restart_osc(on)
        assert manager.osc is not None and manager.status()["osc"]["messages"] == 0
        manager.restart_osc(OutputSettings())
        assert manager.osc is None
    finally:
        manager.stop()


def test_engine_base_colours_are_before_brightness(store):
    from pitchcontrol.engine.engine import Engine

    engine = Engine(store, enable_hardware=False)
    engine.macros.set("Hue A", 0.0)
    engine.macros.set("Saturation A", 1.0)
    engine.macros.set("Hue B", 0.25)
    engine.macros.set("Saturation B", 0.0)
    engine.tick(1 / 40)
    colors = engine.base_colors()
    assert set(colors) == {"a", "b"}
    assert all(0.0 <= v <= 1.0 for c in colors.values() for v in c)
    assert max(colors["a"]) == pytest.approx(1.0) and min(colors["a"]) == pytest.approx(0.0)  # saturated
    assert colors["b"] == pytest.approx((1.0, 1.0, 1.0))  # no saturation: white, whatever the hue
    # darkening everything doesn't change them: they are the colours before strobo, idle and dimmers
    for name in ("Strobo Brightness", "Idle Brightness", "Strobo Bright. A", "Idle Bright. A"):
        engine.macros.set(name, 0.0)
    engine.tick(1 / 40)
    assert engine.base_colors() == colors
    # Swap Colors swaps what is sent
    engine.macros.set("Swap Colors", 1.0)
    engine.tick(1 / 40)
    swapped = engine.base_colors()
    assert swapped["a"] == pytest.approx(colors["b"]) and swapped["b"] == pytest.approx(colors["a"])


def test_settings_api_restarts_only_what_changed(store):
    from fastapi.testclient import TestClient

    from pitchcontrol.engine.engine import Engine
    from pitchcontrol.server.app import create_app

    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True  # the API only restarts outputs when there is hardware
    calls = []
    engine.outputs.restart = lambda s: calls.append("all")  # type: ignore[method-assign]
    engine.outputs.restart_osc = lambda s: calls.append("osc")  # type: ignore[method-assign]
    client = TestClient(create_app(engine))
    data = client.get("/api/settings").json()
    data["outputs"]["osc"].update(enabled=True, host="10.0.0.5", port=9000, file="x")
    assert client.put("/api/settings", json=data).status_code == 200
    assert calls == ["osc"]
    data["outputs"]["artnet"]["enabled"] = True
    assert client.put("/api/settings", json=data).status_code == 200
    assert calls == ["osc", "all"]


def test_osc_files_endpoint_lists_the_shipped_examples_and_the_users(store, tmp_path):
    from fastapi.testclient import TestClient

    from pitchcontrol.engine.engine import Engine
    from pitchcontrol.server.app import create_app

    (store.root / "osc").mkdir(parents=True, exist_ok=True)
    (store.root / "osc" / "Mine.json").write_text("[]", encoding="utf-8")
    store.defaults = SHIPPED_CONFIG
    client = TestClient(create_app(Engine(store, enable_hardware=False)))
    body = client.get("/api/osc/files").json()
    assert "Mine" in body["available"] and "Colors as RGBA" in body["available"]
    assert body["folder"].endswith("osc")
