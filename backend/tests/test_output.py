import numpy as np

from pitchcontrol.config.models import FixtureInstance
from pitchcontrol.engine.fixtures import Fixture
from pitchcontrol.engine.macros import MacroBank
from pitchcontrol.io.protocols import artdmx_packet, enttec_pro_packet, pitchpls_v2_packet


def test_v3_frame_matches_firmware_layout(store):
    """master, mode, 4 strip dimmers, then 24 x RGB (v3_esp32_dmx.ino, DMX_HEADER_CHANNELS = NUM_STRIPS + 2)."""
    fx = Fixture(FixtureInstance(name="v3", type="pitchpls_v3", address=100), store.fixture_types["pitchpls_v3"])
    fx.rgb = np.tile([1.0, 0.5, 0.0], (24, 1))
    data = fx.dmx_bytes(MacroBank())
    assert len(data) == 6 + 24 * 3
    assert data[:6] == [255, 0, 255, 255, 255, 255]
    assert data[6:9] == [255, 128, 0]


def test_channel_override_by_name(store):
    inst = FixtureInstance(name="v3", type="pitchpls_v3", channel_values={"mode": 2})
    fx = Fixture(inst, store.fixture_types["pitchpls_v3"])
    assert fx.dmx_bytes(MacroBank())[1] == 2


def test_rgbw_extracts_white(store):
    fx = Fixture(FixtureInstance(name="p", type="cameo_qspot15_rgbw"), store.fixture_types["cameo_qspot15_rgbw"])
    fx.rgb = np.array([[1.0, 0.6, 0.2]])
    assert fx.dmx_bytes(MacroBank()) == [204, 102, 0, 51]


def test_enttec_packet():
    pkt = enttec_pro_packet(bytes(range(256)) * 2)
    assert pkt[:2] == bytes([0x7E, 6])
    assert pkt[2] | (pkt[3] << 8) == 513  # start code + 512 channels
    assert pkt[4] == 0 and pkt[5:7] == bytes([0, 1])
    assert pkt[-1] == 0xE7 and len(pkt) == 4 + 513 + 1


def test_artdmx_packet():
    pkt = artdmx_packet(0x123, bytes(512), sequence=7)
    assert pkt[:8] == b"Art-Net\x00"
    assert pkt[8:10] == bytes([0x00, 0x50])  # OpDmx, little endian
    assert pkt[12] == 7
    assert pkt[14] == 0x23 and pkt[15] == 0x01
    assert pkt[16:18] == bytes([2, 0]) and len(pkt) == 18 + 512


def test_pitchpls_v2_packet():
    pkt = pitchpls_v2_packet([[255] * 57, [10] * 57], strips_count=4, pixels_per_strip=19, mode=1)
    assert len(pkt) == 4 * 19 * 3 + 2
    assert max(pkt[:-1]) == 254  # 255 is reserved for the terminator
    assert pkt[57] == 10 and pkt[114] == 0  # missing strips are black
    assert pkt[-2:] == bytes([1, 255])


# -- several Enttec interfaces


def test_single_enttec_settings_migrate_to_a_list():
    from pitchcontrol.config.models import OutputSettings

    o = OutputSettings.model_validate({"enttec": {"enabled": True, "universe": 3, "device": {"serial_number": "A"}}})
    assert len(o.enttec) == 1 and o.enttec[0].universe == 3 and o.enttec[0].device.serial_number == "A"
    assert OutputSettings().enttec == []
    assert OutputSettings.model_validate(o.model_dump()).enttec == o.enttec  # saved form loads again


def test_at_most_four_enttec_interfaces():
    import pytest
    from pydantic import ValidationError

    from pitchcontrol.config.models import OutputSettings

    OutputSettings.model_validate({"enttec": [{}] * 4})
    with pytest.raises(ValidationError):
        OutputSettings.model_validate({"enttec": [{}] * 5})


class _FakeWorker:
    def __init__(self):
        self.frames = []

    def submit(self, frame):
        self.frames.append(frame)

    def status(self):
        return {"connected": True, "error": None, "frames": len(self.frames)}


def test_each_enttec_interface_sends_its_own_universe():
    from pitchcontrol.config.models import OutputSettings
    from pitchcontrol.io.outputs import OutputManager

    m = OutputManager(OutputSettings.model_validate({"enttec": [{"enabled": True, "universe": 0}, {"enabled": False, "universe": 1}, {"enabled": True, "universe": 2}]}))
    m.enttec = [_FakeWorker(), None, _FakeWorker()]
    m.send({0: bytearray([10] * 512), 1: bytearray([11] * 512), 2: bytearray([12] * 512)}, [])
    assert m.enttec[0].frames[0][5] == 10 and m.enttec[2].frames[0][5] == 12
    status = m.status()["enttec"]
    assert [x is not None for x in status] == [True, False, True]


def test_two_interfaces_cannot_share_a_device():
    from pitchcontrol.config.models import OutputSettings
    from pitchcontrol.io.outputs import OutputManager

    dev = {"serial_number": "ENP1"}
    m = OutputManager(OutputSettings.model_validate({"enttec": [{"enabled": True, "device": dev}, {"enabled": True, "device": dev, "universe": 1}]}))
    m.start()
    try:
        assert m.enttec[0] is not None and m.enttec[1] is None
        assert "interface 1" in m.status()["enttec"][1]["error"]
    finally:
        m.stop()


# -- Enttec Open DMX USB (a bare FTDI chip: the break and the timing are ours)


class _FakePort:
    """Records what the worker does to a serial port, in order."""

    instances: list = []

    def __init__(self, path, baud, **kw):
        self.path, self.kw = path, kw
        self.events = [("open", baud)]
        self._baud = baud
        self._break = False
        self.rts = self.dtr = True   # a port starts with the lines up
        _FakePort.instances.append(self)

    @property
    def baudrate(self):
        return self._baud

    @baudrate.setter
    def baudrate(self, v):
        self._baud = v
        self.events.append(("baud", v))

    @property
    def break_condition(self):
        return self._break

    @break_condition.setter
    def break_condition(self, v):
        self._break = v
        self.events.append(("break", v))

    def write(self, data):
        self.events.append(("write", self._baud, bytes(data)))

    def reset_output_buffer(self):
        self.events.append(("reset",))

    def flush(self):
        self.events.append(("flush",))

    def close(self):
        pass


def _open_dmx(monkeypatch, method):
    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    _FakePort.instances = []
    clock = {"t": 0.0}
    sleeps = []
    monkeypatch.setattr(workers.serial, "Serial", _FakePort)
    monkeypatch.setattr(workers, "resolve_port", lambda ref: "/dev/fake")
    monkeypatch.setattr(workers.time, "sleep", lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)))
    monkeypatch.setattr(workers.time, "monotonic", lambda: clock["t"])
    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1", method)
    w.open()
    w.sleeps, w.clock = sleeps, clock
    return w, _FakePort.instances[0]


def test_open_dmx_port_setup(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    assert port.baudrate == 250000 and port.kw["stopbits"] == 2 and port.kw["bytesize"] == 8 and port.kw["parity"] == "N"
    assert port.rts is True and port.dtr is True     # left as the system opened it
    assert ("reset",) not in port.events


def test_open_dmx_break_by_baud_rate_waits_for_every_step(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    port.events.clear()
    w.write(bytes([7] * 512))
    # the baud rate change, the break byte and the change back are separate USB transfers: each
    # one is followed by a wait, so none overtakes the other
    assert port.events == [
        ("baud", 90000),
        ("write", 90000, b"\x00"),                       # 9 bits at 90000 baud = a 100 us break
        ("baud", 250000),
        ("write", 250000, b"\x00" + bytes([7] * 512)),   # start code 0 + 512 channels
    ]
    settle = w.SETTLE_S
    assert w.sleeps[-3:] == [settle, settle, settle]
    assert not any(e[0] == "break" for e in port.events)


def test_open_dmx_waits_for_the_previous_frame_by_its_length(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    w.write(bytes(512))
    before = w.clock["t"]
    w.sleeps.clear()
    w.write(bytes(512))   # straight away: the first frame (513 slots x 44 us) is still on its way out
    assert w.sleeps[0] >= 513 * 44e-6 - 1e-6
    assert w.clock["t"] - before >= 513 * 44e-6


def test_open_dmx_break_line_method(monkeypatch):
    w, port = _open_dmx(monkeypatch, "break")
    port.events.clear()
    frame = bytes([7] * 512)
    w.write(frame)
    ev = port.events
    assert ev[0] == ("break", True) and ev[1] == ("break", False)      # the break, then the mark
    assert ev[2] == ("write", 250000, b"\x00" + frame)
    assert w.sleeps[-2:] == [w.BREAK_S, w.MARK_S] or w.sleeps[:2] == [w.BREAK_S, w.MARK_S]


def test_open_dmx_cuts_long_frames_and_pads_nothing(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    w.write(bytes(range(256)) * 3)   # more than 512 bytes: cut at 512 channels
    last = [e for e in port.events if e[0] == "write"][-1]
    assert len(last[2]) == 513


def test_usb_interface_type_selects_the_worker_and_the_data(monkeypatch):
    from pitchcontrol.config.models import OutputSettings
    from pitchcontrol.io import outputs as out

    class Rec:
        def __init__(self, *a, **k):
            self.a, self.frames = a, []

        def start(self):
            pass

        def stop(self):
            pass

        def submit(self, f):
            self.frames.append(f)

        def status(self):
            return {"connected": True, "error": None, "frames": 0}

    monkeypatch.setattr(out, "SerialWorker", Rec)
    monkeypatch.setattr(out, "OpenDmxWorker", Rec)
    s = OutputSettings.model_validate({"enttec": [
        {"enabled": True, "universe": 0, "device": {"serial_number": "A"}},                       # no type: the Pro
        {"enabled": True, "universe": 1, "type": "open", "break_method": "break", "device": {"serial_number": "B"}},
    ]})
    m = out.OutputManager(s)
    m.start()
    m.send({0: bytearray([9] * 512), 1: bytearray([5] * 512)}, [])
    pro, op = m.enttec
    assert pro.frames[0][:2] == bytes([0x7E, 6])                  # an Enttec Pro packet
    assert op.frames[0] == bytes([5] * 512)                        # bare channels
    assert "break" in op.a                                          # the break method reaches the worker
