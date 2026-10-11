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
    """Records what the worker does to a serial port."""

    instances: list = []

    def __init__(self, path, baud, **kw):
        self.path, self.baudrate, self.kw = path, baud, kw
        self.events = []
        self._break = False
        _FakePort.instances.append(self)

    @property
    def break_condition(self):
        return self._break

    @break_condition.setter
    def break_condition(self, v):
        self._break = v
        self.events.append(("break", v))

    def write(self, data):
        self.events.append(("write", self.baudrate, bytes(data)))

    def flush(self):
        self.events.append(("flush",))

    def close(self):
        pass


def _open_dmx(monkeypatch, method):
    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    _FakePort.instances = []
    monkeypatch.setattr(workers.serial, "Serial", _FakePort)
    monkeypatch.setattr(workers, "resolve_port", lambda ref: "/dev/fake")
    monkeypatch.setattr(workers.time, "sleep", lambda s: None)
    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1", method)
    w.open()
    return w, _FakePort.instances[0]


def test_open_dmx_makes_break_mark_and_frame(monkeypatch):
    w, port = _open_dmx(monkeypatch, "break")
    assert port.baudrate == 250000 and port.kw["stopbits"] == 2 and port.kw["bytesize"] == 8 and port.kw["parity"] == "N"
    frame = bytes([7] * 512)
    w.write(frame)
    ev = [e for e in port.events if e[0] != "flush"]
    assert ev[0] == ("break", True) and ev[1] == ("break", False)      # the break, then the mark
    assert ev[2] == ("write", 250000, b"\x00" + frame)                  # start code 0 + 512 channels
    assert port.events[0] == ("flush",)                                 # the previous frame is out first


def test_open_dmx_break_by_baud_rate(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    w.write(bytes(512))
    writes = [e for e in port.events if e[0] == "write"]
    # a 0x00 byte at 90000 baud is the break (9 bits x 11.1 us), then the frame at 250000
    assert writes[0] == ("write", 90000, b"\x00")
    assert writes[1][1] == 250000 and writes[1][2] == b"\x00" + bytes(512)
    assert not any(e[0] == "break" for e in port.events)
    assert port.baudrate == 250000


def test_open_dmx_cuts_long_frames_and_pads_nothing(monkeypatch):
    w, port = _open_dmx(monkeypatch, "break")
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
        {"enabled": True, "universe": 1, "type": "open", "break_method": "baud", "device": {"serial_number": "B"}},
    ]})
    m = out.OutputManager(s)
    m.start()
    m.send({0: bytearray([9] * 512), 1: bytearray([5] * 512)}, [])
    pro, op = m.enttec
    assert pro.frames[0][:2] == bytes([0x7E, 6])                  # an Enttec Pro packet
    assert op.frames[0] == bytes([5] * 512)                        # bare channels
    assert op.a[2:] == ("break",) or "baud" in op.a               # the break method reaches the worker
