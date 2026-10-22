"""Live input (item 57): ArtDMX parsing, the latest-values store, the own-packet filter, the Enttec Pro's receive
messages, the manager, and the settings endpoint."""

import json
import socket
import time

import pytest
from fastapi.testclient import TestClient

from pitchcontrol.config.models import (
    ArtNetInputSettings,
    DeviceRef,
    DmxInputSettings,
    EnttecSettings,
    LiveInputSettings,
    OutputSettings,
)
from pitchcontrol.engine.engine import Engine
from pitchcontrol.io import live_input
from pitchcontrol.io.live_input import (
    ArtNetReceiver,
    DmxProReceiver,
    InputStore,
    LiveInput,
    ProDecoder,
    ProParser,
    artnet_key,
    parse_artdmx,
    pro_message,
)
from pitchcontrol.io.outputs import ArtNetWorker
from pitchcontrol.io.protocols import artdmx_packet
from pitchcontrol.server.app import create_app


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(condition, seconds: float = 3.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


# -- ArtDMX parsing


def test_artdmx_port_address_length_and_sequence():
    art = parse_artdmx(artdmx_packet(0x123, bytes(range(100)), sequence=7))
    assert art is not None
    assert art.port_address == 0x123  # net 1, sub-net 2, universe 3
    assert art.sequence == 7
    assert art.data == bytes(range(100))  # 100 is even: nothing padded


def test_artdmx_odd_length_is_padded_by_the_sender_and_kept_as_sent():
    art = parse_artdmx(artdmx_packet(0, bytes([1, 2, 3])))  # the sender pads to an even length
    assert art is not None and art.data == bytes([1, 2, 3, 0])


def test_artdmx_the_full_15_bit_port_address():
    assert parse_artdmx(artdmx_packet(0x7FFF, bytes(512))).port_address == 0x7FFF


def test_other_packets_are_not_artdmx():
    poll = b"Art-Net\x00" + bytes([0x00, 0x20, 0, 14, 0, 0])  # ArtPoll
    assert parse_artdmx(poll) is None
    assert parse_artdmx(b"") is None
    assert parse_artdmx(b"Art-Net\x00" + bytes(11)) is None  # OpCode 0
    good = artdmx_packet(1, bytes(10))
    assert parse_artdmx(good[:17]) is None  # cut inside the header
    assert parse_artdmx(good[:9] + b"\x40" + good[10:]) is None  # OpCode 0x4000
    assert parse_artdmx(good[:16] + bytes([2, 1]) + good[18:]) is None  # a length of 513
    assert parse_artdmx(good[:16] + bytes([0, 0]) + good[18:]) is None  # a length of 0
    assert parse_artdmx(b"Art-Nex\x00" + good[8:]) is None  # not Art-Net


def test_artdmx_cut_short_gives_what_is_there():
    pkt = artdmx_packet(5, bytes(range(20)))
    assert parse_artdmx(pkt[: 18 + 7]).data == bytes(range(7))


# -- the store


def test_store_keeps_the_latest_values_and_the_channels_a_packet_leaves_out():
    clock = [100.0]
    store = InputStore(lambda: clock[0])
    assert store.get("artnet:0") is None
    store.put("artnet:0", bytes([10] * 512), "10.0.0.5")
    store.put("artnet:0", bytes([99, 98, 97]), "10.0.0.6")  # a short packet: the rest stays
    values = store.get("artnet:0")
    assert values[:3] == bytes([99, 98, 97]) and values[3] == 10 and len(values) == 512
    clock[0] += 0.5
    (entry,) = store.snapshot("artnet:")
    assert entry["sender"] == "10.0.0.6" and entry["packets"] == 2 and entry["age"] == 0.5


def test_store_packets_per_second_and_age():
    clock = [0.0]
    store = InputStore(lambda: clock[0])
    store.put("artnet:1", b"\x01")
    for _ in range(40):
        clock[0] += 0.025
        store.put("artnet:1", b"\x01")
    (entry,) = store.snapshot()
    assert 35 <= entry["pps"] <= 45  # 41 packets over one second
    clock[0] += 30
    (entry,) = store.snapshot()
    assert entry["pps"] == 0.0 and entry["age"] > 29
    assert store.get("artnet:1") is not None  # nothing is forgotten when a sender goes quiet


# -- the own-packet filter


def test_own_packets_are_dropped_and_others_taken():
    store = InputStore()
    rx = ArtNetReceiver(store, ArtNetInputSettings(), own_ports=lambda: {50000})
    packet = artdmx_packet(3, bytes([7] * 8))
    rx.handle(packet, ("127.0.0.1", 50000))  # this computer, the output's port: our own
    assert store.get("artnet:3") is None and rx.own == 1
    rx.handle(packet, ("192.0.2.9", 50000))  # another computer that happens to use the same port number
    assert store.get("artnet:3") is not None and rx.packets == 1
    rx.handle(packet, ("127.0.0.1", 50001))  # this computer, another program
    assert rx.packets == 2 and rx.own == 1


def test_a_packet_that_is_not_artdmx_is_counted_apart():
    rx = ArtNetReceiver(InputStore(), ArtNetInputSettings())
    rx.handle(b"hello", ("10.0.0.2", 6454))
    assert rx.other == 1 and rx.packets == 0


def test_loopback_own_output_is_ignored_and_an_external_packet_is_taken(monkeypatch):
    """The app's own Art-Net output to another universe on 127.0.0.1 doesn't feed back; a packet from elsewhere does."""
    port = free_udp_port()
    store = InputStore()
    out = ArtNetWorker(dest_port=port)
    out.start()
    rx = ArtNetReceiver(store, ArtNetInputSettings(enabled=True, port=port, adapter="127.0.0.1"), own_ports=lambda: {out.sock.getsockname()[1]} if out.sock else set())
    rx.start()
    try:
        assert wait_for(lambda: rx.listening), rx.error
        out.submit([("127.0.0.1", artdmx_packet(5, bytes([200] * 512)))])
        assert wait_for(lambda: rx.own >= 1)  # it arrived, and was recognised as ours
        assert store.get(artnet_key(5)) is None

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:  # "another program", its own source port
            other.sendto(artdmx_packet(9, bytes([33] * 512)), ("127.0.0.1", port))
        assert wait_for(lambda: store.get(artnet_key(9)) is not None)
        assert store.get(artnet_key(9))[0] == 33
        assert store.get(artnet_key(5)) is None
    finally:
        rx.stop()
        out.stop()


def test_a_taken_port_is_reported_and_tried_again():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as blocker:  # no SO_REUSEADDR: nobody else may bind
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        blocker.bind(("127.0.0.1", 0))
        port = blocker.getsockname()[1]
        rx = ArtNetReceiver(InputStore(), ArtNetInputSettings(enabled=True, port=port, adapter="127.0.0.1"))
        rx.start()
        try:
            assert wait_for(lambda: rx.error is not None)
            assert not rx.listening and str(port) in rx.error
        finally:
            rx.stop()


# -- the Enttec Pro


def received(channels: bytes, status: int = 0, start_code: int = 0) -> bytes:
    return pro_message(live_input.PRO_LABEL_RECEIVED, bytes([status, start_code]) + channels)


def test_pro_parser_splits_messages_over_chunks_and_resyncs_on_garbage():
    parser = ProParser()
    stream = b"\x00\x13garbage" + received(bytes([1, 2, 3])) + received(bytes([4, 5]))
    messages = []
    for i in range(0, len(stream), 3):  # three bytes at a time
        messages += parser.feed(stream[i : i + 3])
    assert [(label, data) for label, data in messages] == [
        (5, bytes([0, 0, 1, 2, 3])),
        (5, bytes([0, 0, 4, 5])),
    ]
    # a message with a wrong end byte is skipped, the next one still arrives
    bad = bytearray(received(bytes([9])))
    bad[-1] = 0x00
    assert [m[1] for m in parser.feed(bytes(bad) + received(bytes([8])))] == [bytes([0, 0, 8])]


def test_pro_received_dmx_packet():
    dec = ProDecoder()
    values = dec.decode(5, bytes([0, 0]) + bytes(range(1, 101)))
    assert values is not None and len(values) == 512
    assert values[0] == 1 and values[99] == 100 and values[100] == 0


def test_pro_damaged_packets_and_other_start_codes_are_not_taken():
    dec = ProDecoder()
    assert dec.decode(5, bytes([1, 0, 9, 9])) is None  # queue overflowed
    assert dec.decode(5, bytes([2, 0, 9, 9])) is None  # receive overrun
    assert dec.decode(5, bytes([0, 0xCC, 9, 9])) is None  # an RDM start code
    assert dec.decode(5, b"") is None
    assert dec.errors == 4
    assert dec.decode(3, b"anything") is None  # another label


def test_pro_change_of_state_packets_follow_enttecs_algorithm():
    dec = ProDecoder()
    # start byte 0 (array positions 0..39, position 0 is the start code): positions 1, 2 and 9 changed
    bits = bytearray(5)
    for pos in (1, 2, 9):
        bits[pos // 8] |= 1 << (pos % 8)
    values = dec.decode(9, bytes([0]) + bytes(bits) + bytes([50, 60, 70]))
    assert values[0] == 50 and values[1] == 60 and values[8] == 70  # channels are positions 1..512
    # a second packet starting at byte 8 (positions 64..103) leaves the first ones alone
    bits = bytearray(5)
    bits[0] = 0b101  # positions 64 and 66 = channels 64 and 66
    values = dec.decode(9, bytes([8]) + bytes(bits) + bytes([11, 22]))
    assert values[63] == 11 and values[65] == 22 and values[0] == 50


class FakePort:
    def __init__(self, to_read: bytes = b""):
        self.written = b""
        self.to_read = to_read
        self.closed = False

    def write(self, data):
        self.written += data

    def reset_input_buffer(self):
        pass

    def read(self, n):
        data, self.to_read = self.to_read[:n], self.to_read[n:]
        return data

    def close(self):
        self.closed = True


def test_pro_receiver_asks_for_every_packet_and_stores_what_arrives(monkeypatch):
    port = FakePort()
    monkeypatch.setattr(live_input, "resolve_port", lambda ref: "COM9")
    monkeypatch.setattr(live_input.serial, "Serial", lambda *a, **k: port)
    store = InputStore()
    rx = DmxProReceiver(store, DeviceRef(port="COM9"))
    rx._open()
    assert port.written == bytes([0x7E, 8, 1, 0, 0, 0xE7])  # "Receive DMX on Change": 0 = send always
    rx.feed(received(bytes([5, 6, 7])) + received(bytes([5, 6, 8]))[:6])  # the second one is cut: it waits for the rest
    assert store.get("dmx")[:3] == bytes([5, 6, 7])
    rx.feed(received(bytes([200] * 512)))
    assert store.get("dmx") == bytes([200] * 512)
    assert rx.status()["connected"] and rx.status()["packets"] == 2


def test_pro_receiver_without_a_device_reports_it_and_keeps_trying(monkeypatch):
    monkeypatch.setattr(live_input, "resolve_port", lambda ref: None)
    monkeypatch.setattr(live_input, "RETRY_S", 0.05)
    rx = DmxProReceiver(InputStore(), DeviceRef())
    rx.start()
    try:
        assert wait_for(lambda: rx.error is not None)
        assert "not found" in rx.error and not rx.connected
    finally:
        rx.stop()


# -- the manager


def test_a_pro_that_receives_is_refused_on_a_device_an_output_uses(monkeypatch):
    started = []
    monkeypatch.setattr(DmxProReceiver, "start", lambda self: started.append(self))
    live = LiveInput()
    pro = DeviceRef(serial_number="EN123456")
    outputs = OutputSettings(enttec=[EnttecSettings(enabled=True, device=pro)])
    live.apply(LiveInputSettings(dmx=DmxInputSettings(enabled=True, device=pro)), outputs)
    assert not started and live.dmx is None
    status = live.status()["dmx"]
    assert status["enabled"] and not status["connected"] and "output interface 1" in status["error"]

    # with the output off the same device may receive
    live.apply(LiveInputSettings(dmx=DmxInputSettings(enabled=True, device=pro)), OutputSettings(enttec=[EnttecSettings(enabled=False, device=pro)]))
    assert len(started) == 1 and live.dmx is not None
    # a different device is no clash
    live.apply(LiveInputSettings(dmx=DmxInputSettings(enabled=True, device=DeviceRef(serial_number="OTHER"))), outputs)
    assert len(started) == 2


def test_manager_runs_only_what_is_on_and_keeps_the_values_when_switched_off():
    live = LiveInput()
    port = free_udp_port()
    on = LiveInputSettings(artnet=ArtNetInputSettings(enabled=True, port=port, adapter="127.0.0.1"))
    live.apply(on, OutputSettings())
    try:
        assert wait_for(lambda: live.artnet is not None and live.artnet.listening)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(artdmx_packet(2, bytes([77] * 512)), ("127.0.0.1", port))
        assert wait_for(lambda: live.latest(artnet_key(2)) is not None)
        status = live.status()["artnet"]
        assert status["listening"] and status["universes"][0]["universe"] == 2 and status["universes"][0]["sender"] == "127.0.0.1"
        live.apply(LiveInputSettings(), OutputSettings())  # switched off
        assert live.artnet is None and live.status()["artnet"] == {"enabled": False}
        assert live.latest(artnet_key(2))[0] == 77  # the last values stay (an overridden channel stays overridden)
    finally:
        live.stop()


# -- the settings endpoint


@pytest.fixture
def client(store):
    return TestClient(create_app(Engine(store, enable_hardware=False)), client=("127.0.0.1", 50000))


def test_live_input_is_off_by_default_and_listens_on_the_standard_port(store):
    cfg = store.settings.live_input
    assert not cfg.artnet.enabled and not cfg.dmx.enabled
    assert cfg.artnet.port == 6454 and cfg.artnet.adapter == ""


def test_the_endpoint_lists_adapters_and_saves_per_computer(store, client):
    got = client.get("/api/live-input").json()
    assert got["settings"]["artnet"]["port"] == 6454
    assert {"name": "Loopback", "ip": "127.0.0.1"} in got["adapters"]
    assert got["status"] == {"artnet": {"enabled": False}, "dmx": {"enabled": False}}

    body = {"artnet": {"enabled": True, "port": 6455, "adapter": "127.0.0.1"}, "dmx": {"enabled": False}}
    assert client.put("/api/live-input", json=body).status_code == 200
    assert store.settings.live_input.artnet == ArtNetInputSettings(enabled=True, port=6455, adapter="127.0.0.1")
    machine = json.loads(store.machine_path.read_text(encoding="utf-8"))  # this computer's file, not settings.json
    assert machine["live_input"]["artnet"]["port"] == 6455
    assert "live_input" not in json.loads(store.settings_path.read_text(encoding="utf-8")) if store.settings_path.exists() else True


def test_bad_values_are_refused(client):
    assert client.put("/api/live-input", json={"artnet": {"port": 0}}).status_code == 422
    assert client.put("/api/live-input", json={"artnet": {"adapter": "not an address"}}).status_code == 422
    assert client.put("/api/live-input", json={"artnet": {"adapter": "10.0.0.256"}}).status_code == 422


def test_other_devices_cannot_change_it_and_the_settings_page_neither_shows_nor_changes_it(store):
    app = create_app(Engine(store, enable_hardware=False))
    phone = TestClient(app, client=("192.168.1.50", 50000))
    store.settings = store.settings.model_copy(update={"network": store.settings.network.model_copy(update={"enabled": True})})
    assert phone.get("/api/live-input").status_code == 403
    assert phone.put("/api/live-input", json={}).status_code == 403

    local = TestClient(app, client=("127.0.0.1", 50000))
    local.put("/api/live-input", json={"artnet": {"enabled": True, "port": 6460}})
    page = local.get("/api/settings").json()
    assert "live_input" not in page
    assert local.put("/api/settings", json=page).status_code == 200  # the Inputs page saves what it read
    assert store.settings.live_input.artnet.port == 6460 and store.settings.live_input.artnet.enabled
