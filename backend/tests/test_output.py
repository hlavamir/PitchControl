import numpy as np
import pytest

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
    monkeypatch.setattr(workers.time, "perf_counter", lambda: clock["t"])
    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1", method)
    w.open()
    w.sleeps, w.clock = sleeps, clock
    return w, _FakePort.instances[0]


def test_open_dmx_port_setup(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    assert port.baudrate == 250000 and port.kw["stopbits"] == 2 and port.kw["bytesize"] == 8 and port.kw["parity"] == "N"
    # RTS and DTR low: the RS-485 driver of the dongle follows them (the fixture saw nothing with them high)
    assert port.rts is False and port.dtr is False
    assert ("break", False) in port.events   # a break left on by an earlier run is cleared


def test_open_dmx_break_by_baud_rate_drains_between_steps(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    port.events.clear()
    w.write(bytes([7] * 512))
    # the sequence that made a fixture react on macOS: drain, break byte at 90000 baud, drain, back to
    # 250000 baud, start code + 512 channels
    assert port.events == [
        ("flush",),
        ("baud", 90000),
        ("write", 90000, b"\x00"),
        ("flush",),
        ("baud", 250000),
        ("write", 250000, b"\x00" + bytes([7] * 512)),
    ]
    assert not any(e[0] == "break" for e in port.events)


def test_open_dmx_break_line_method(monkeypatch):
    w, port = _open_dmx(monkeypatch, "break")
    port.events.clear()
    frame = bytes([7] * 512)
    w.write(frame)
    ev = [e for e in port.events if e[0] != "flush"]
    assert ev[0] == ("break", True) and ev[1] == ("break", False)      # the break, then the mark
    assert ev[2] == ("write", 250000, b"\x00" + frame)
    assert w.sleeps[-2:] == [w.BREAK_S, w.MARK_S]


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


# -- the interface type is found out from the USB device


def test_guess_dmx_type_from_the_usb_strings():
    from pitchcontrol.io.devices import guess_dmx_type

    assert guess_dmx_type("FT245R USB FIFO") == "pro"           # the Enttec DMX USB Pro
    assert guess_dmx_type("DMX USB PRO", "ENTTEC") == "pro"
    assert guess_dmx_type("ultraDMX Micro", "DMXking.com") == "pro"
    assert guess_dmx_type("FT232R USB UART") == "open"          # the Enttec Open DMX USB / bare dongles
    assert guess_dmx_type(None, "FTDI", "USB-RS485") == "open"
    assert guess_dmx_type("Midihub MH-3Z6HN83") is None
    assert guess_dmx_type(None, None) is None
    assert guess_dmx_type("ENTTEC Open DMX USB") == "open"      # "open dmx" counts before the Pro word "enttec"
    assert guess_dmx_type("Open DMX USB", "ENTTEC") == "open"
    assert guess_dmx_type("ENTTEC") == "pro"
    assert guess_dmx_type("USB Serial Port (COM3)", "FTDI") is None  # Windows: no product string, the probe decides


class FakeProbePort:
    """A stand-in for serial.Serial that answers the probe with `reply` (or fails to open)."""

    opened: list = []

    def __init__(self, reply=b"", error=None):
        self.reply, self.error, self.written, self.closed = reply, error, b"", False

    def factory(self, port, baud, **kw):
        if self.error:
            raise self.error
        FakeProbePort.opened.append((port, baud))
        return self

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written += data

    def read(self, n):
        out, self.reply = self.reply[:n], self.reply[n:]
        return out

    def close(self):
        self.closed = True


def _windows_device(monkeypatch, fake):
    """A connected interface whose strings don't tell the type, and the fake in place of the port."""
    import serial
    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import devices

    FakeProbePort.opened = []
    devices.clear_probe_cache()
    dev = {"port": "COM3", "serial_number": "A1", "description": "USB Serial Port (COM3)", "dmx_type": None}
    monkeypatch.setattr(devices, "list_serial_devices", lambda: [dev])
    monkeypatch.setattr(devices, "resolve_port", lambda ref: "COM3")
    monkeypatch.setattr(devices.serial, "Serial", fake.factory)
    return devices, DeviceRef(serial_number="A1", port="COM3"), serial


def test_probe_pro_answers(monkeypatch):
    fake = FakeProbePort(bytes([0x7E, 0x0A, 0x04, 0x00, 1, 2, 3, 4, 0xE7]))
    devices, ref, _ = _windows_device(monkeypatch, fake)
    assert devices.detect_dmx_type(ref) == "pro"
    assert fake.written == bytes([0x7E, 0x0A, 0x00, 0x00, 0xE7])
    assert FakeProbePort.opened == [("COM3", 57600)] and fake.closed


def test_probe_silence_is_open(monkeypatch):
    fake = FakeProbePort(b"")
    devices, ref, _ = _windows_device(monkeypatch, fake)
    assert devices.detect_dmx_type(ref) == "open"
    assert fake.closed


def test_probe_garbage_is_open(monkeypatch):
    fake = FakeProbePort(bytes([0x00, 0xFF, 0x12, 0x34, 0x56]))
    devices, ref, _ = _windows_device(monkeypatch, fake)
    assert devices.detect_dmx_type(ref) == "open"


def test_probe_open_fails_falls_back(monkeypatch, caplog):
    import serial

    devices, ref, _ = _windows_device(monkeypatch, FakeProbePort())
    monkeypatch.setattr(devices.serial, "Serial", FakeProbePort(error=serial.SerialException("busy")).factory)
    with caplog.at_level("WARNING"):
        assert devices.detect_dmx_type(ref) == "pro"            # nothing stored: the Enttec Pro protocol
        ref.description = "FT232R USB UART"
        assert devices.detect_dmx_type(ref) == "open"           # the stored description
    assert "probe failed: busy" in caplog.text
    assert not devices._probed                                  # a failure is not remembered


def test_probe_result_is_cached_per_run(monkeypatch):
    fake = FakeProbePort(b"")
    devices, ref, _ = _windows_device(monkeypatch, fake)
    assert devices.detect_dmx_type(ref) == "open"
    assert devices.detect_dmx_type(ref) == "open"
    assert len(FakeProbePort.opened) == 1                       # the second call didn't touch the port
    devices.clear_probe_cache()
    devices.detect_dmx_type(ref)
    assert len(FakeProbePort.opened) == 2


def test_strings_decide_without_probing(monkeypatch):
    fake = FakeProbePort(b"")
    devices, ref, _ = _windows_device(monkeypatch, fake)
    devices.list_serial_devices()[0]["dmx_type"] = "open"
    assert devices.detect_dmx_type(ref) == "open"
    assert FakeProbePort.opened == []


def test_auto_type_uses_the_detected_device(monkeypatch):
    from pitchcontrol.config.models import DeviceRef, OutputSettings
    from pitchcontrol.io import devices, outputs as out

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

    # a stored description is enough when the device is not plugged in
    assert devices.detect_dmx_type(DeviceRef(description="FT232R USB UART")) == "open"
    assert devices.detect_dmx_type(DeviceRef(description="FT245R USB FIFO")) == "pro"
    assert devices.detect_dmx_type(DeviceRef()) == "pro"        # nothing tells: the Enttec Pro protocol

    monkeypatch.setattr(out, "SerialWorker", Rec)
    monkeypatch.setattr(out, "OpenDmxWorker", Rec)
    s = OutputSettings.model_validate({"enttec": [
        {"enabled": True, "universe": 0, "device": {"serial_number": "A", "description": "FT245R USB FIFO"}},   # auto -> pro
        {"enabled": True, "universe": 1, "device": {"serial_number": "B", "description": "FT232R USB UART"}},   # auto -> open
        {"enabled": True, "universe": 2, "type": "pro", "device": {"serial_number": "C", "description": "FT232R USB UART"}},  # forced
    ]})
    m = out.OutputManager(s)
    m.start()
    m.send({0: bytearray([9] * 512), 1: bytearray([5] * 512), 2: bytearray([6] * 512)}, [])
    pro, op, forced = m.enttec
    assert pro.frames[0][:2] == bytes([0x7E, 6])
    assert op.frames[0] == bytes([5] * 512)
    assert forced.frames[0][:2] == bytes([0x7E, 6])
    assert [x["kind"] for x in m.status()["enttec"]] == ["pro", "open", "pro"]


# -- the opt-in timing log of the Open DMX writer ("Log frame timing")


def _timing_lines(caplog, kind):
    return [r.getMessage() for r in caplog.records if r.name.endswith("io.workers") and kind in r.getMessage()]


def test_frame_timing_log_summary_every_10_seconds(caplog):
    import logging

    from pitchcontrol.io.workers import FrameTimingLog

    caplog.set_level(logging.INFO)
    t = FrameTimingLog("opendmx1", lambda: 0.025)
    starts = [100.0 + 0.025 * i + (0.020 if i >= 200 else 0.0) for i in range(402)]   # 40 fps, one gap of 45 ms
    for i, start in enumerate(starts):
        t.frame(start, start + (0.012 if i == 100 else 0.005))                          # one write of 12 ms
    summary = _timing_lines(caplog, "timing,")
    assert len(summary) == 1
    assert "opendmx1: timing, last 10.0 s" in summary[0]
    assert "longest write 12.0 ms" in summary[0]
    assert "largest gap 45.0 ms" in summary[0]
    assert "late frames 0" in summary[0] and "dropped 0" in summary[0]   # 45 ms is under 2 x 25 ms: not late
    assert "fps (target 40.0)" in summary[0]
    assert _timing_lines(caplog, "late frame:") == []


def test_frame_timing_log_outlier_line_and_dropped_frames(caplog):
    import logging

    from pitchcontrol.io.workers import FrameTimingLog

    caplog.set_level(logging.INFO)
    t = FrameTimingLog("opendmx1", lambda: 0.025)
    t.frame(10.0, 10.004)
    t.frame(10.025, 10.029)            # on time
    t.dropped += 2                      # the engine submitted over two frames the writer never took
    t.frame(10.100, 10.130)            # gap 75 ms, write 30 ms
    late = _timing_lines(caplog, "late frame:")
    assert len(late) == 1
    assert "gap 75.0 ms (target 25.0 ms)" in late[0]
    assert "write 30.0 ms" in late[0] and "start +0.100 s, end +0.130 s" in late[0]
    assert "2 dropped since the last frame" in late[0]
    # the next on-time frame says nothing, and the dropped count is reported once
    t.frame(10.125, 10.129)
    assert len(_timing_lines(caplog, "late frame:")) == 1
    t.reset()                           # an outage: the first gap after it is not measured
    t.frame(10.5, 10.504)
    assert len(_timing_lines(caplog, "late frame:")) == 1


def test_frame_timing_log_follows_the_target_frame_rate(caplog):
    import logging

    from pitchcontrol.io.workers import FrameTimingLog

    caplog.set_level(logging.INFO)
    period = {"s": 0.1}                 # 10 fps: a gap of 150 ms is fine
    t = FrameTimingLog("opendmx1", lambda: period["s"])
    t.frame(1.0, 1.001)
    t.frame(1.15, 1.151)
    assert _timing_lines(caplog, "late frame:") == []
    period["s"] = 0.025                 # the frame rate went up to 40: the same gap is late now
    t.frame(1.30, 1.301)
    assert len(_timing_lines(caplog, "late frame:")) == 1


def test_open_dmx_writer_logs_timing_through_the_thread(monkeypatch, caplog):
    import logging
    import time as real_time

    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    caplog.set_level(logging.INFO)
    _FakePort.instances = []
    monkeypatch.setattr(workers.serial, "Serial", _FakePort)
    monkeypatch.setattr(workers, "resolve_port", lambda ref: "/dev/fake")
    monkeypatch.setattr(workers, "TIMING_SUMMARY_S", 0.15)
    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1")
    w.min_interval = 0.0                                           # the clamp has its own tests (item 35)
    w.timing = workers.FrameTimingLog("opendmx1", lambda: 0.001)   # target 1 ms: frames 20 ms apart are late
    w.start()
    try:
        for i in range(12):
            w.submit(bytes([i] * 512))
            real_time.sleep(0.02)
    finally:
        w.stop()
    assert w.frames_sent >= 10
    assert _timing_lines(caplog, "late frame:")
    assert _timing_lines(caplog, "timing,")


def test_open_dmx_writer_counts_the_frames_it_never_took(monkeypatch):
    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1")   # the thread isn't started: nothing takes a frame
    w.timing = workers.FrameTimingLog("opendmx1", lambda: 0.025)
    for i in range(4):
        w.submit(bytes([i] * 512))
    assert w.timing.dropped == 3                          # each submit after the first replaced a frame


def test_open_dmx_writer_does_nothing_extra_with_timing_off(monkeypatch, caplog):
    import logging

    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    caplog.set_level(logging.INFO)
    w = workers.OpenDmxWorker(DeviceRef(), "opendmx1")
    assert w.timing is None
    w.submit(b"\x01" * 512)
    w.submit(b"\x02" * 512)
    assert w._pending is False                            # no bookkeeping when off
    assert _timing_lines(caplog, "timing") == []


def test_log_timing_setting_reaches_only_the_open_dmx_worker(monkeypatch):
    from pitchcontrol.config.models import EnttecSettings, OutputSettings
    from pitchcontrol.io import outputs as out

    assert EnttecSettings().log_timing is False   # off by default

    class Rec:
        def __init__(self, *a, **k):
            self.a, self.timing = a, None

        def start(self):
            pass

        def stop(self):
            pass

        def submit(self, f):
            pass

    monkeypatch.setattr(out, "SerialWorker", Rec)
    monkeypatch.setattr(out, "OpenDmxWorker", Rec)
    s = OutputSettings.model_validate({"enttec": [
        {"enabled": True, "universe": 0, "type": "open", "log_timing": True, "device": {"serial_number": "A"}},
        {"enabled": True, "universe": 1, "type": "open", "device": {"serial_number": "B"}},
    ]})
    m = out.OutputManager(s, frame_period=lambda: 0.05)
    m.start()
    on, off = m.enttec
    assert on.timing is not None and on.timing.target_period() == 0.05
    assert off.timing is None


def test_open_dmx_timing_target_is_clamped_to_30_fps(monkeypatch, caplog):
    """An Open sends at most 30 fps: the timing log's target and 'late' follow (item 35)."""
    import logging

    from pitchcontrol.config.models import OutputSettings
    from pitchcontrol.io import outputs as out

    class Rec:
        def __init__(self, *a, **k):
            self.timing = None

        def start(self):
            pass

    monkeypatch.setattr(out, "SerialWorker", Rec)
    monkeypatch.setattr(out, "OpenDmxWorker", Rec)
    s = OutputSettings.model_validate({"enttec": [
        {"enabled": True, "type": "open", "log_timing": True, "device": {"serial_number": "A"}},
    ]})
    caplog.set_level(logging.INFO)
    period = {"s": 1 / 40}
    m = out.OutputManager(s, frame_period=lambda: period["s"])
    m.start()
    t = m.enttec[0].timing
    assert abs(t.target_period() - 1 / 30) < 1e-9          # the engine's 40 fps is above what an Open sends
    assert any("opendmx1: sends at most 30 fps (engine 40)" in r.getMessage() for r in caplog.records)
    for i in range(401):
        t.frame(100.0 + i / 30, 100.0 + i / 30 + 0.031)
    summary = _timing_lines_any(caplog, "timing,")
    assert len(summary) == 1 and "fps (target 30.0, clamped from 40.0)" in summary[0]
    assert "late frames 0" in summary[0]                    # 33 ms gaps are on target now
    period["s"] = 1 / 20                                    # the engine is slower than the clamp: no clamp
    assert t.target_period() == 1 / 20


def _timing_lines_any(caplog, kind):
    return [r.getMessage() for r in caplog.records if kind in r.getMessage()]


def test_open_dmx_status_tells_its_frame_cap(monkeypatch):
    from pitchcontrol.config.models import DeviceRef
    from pitchcontrol.io import workers

    assert workers.OpenDmxWorker(DeviceRef(), "opendmx1").status()["max_fps"] == 30
    assert "max_fps" not in workers.SerialWorker(DeviceRef(), 57600, "enttec1").status()


def test_worker_keeps_a_minimum_gap_between_writes_and_writes_the_newest_frame():
    import time as real_time

    from pitchcontrol.io import workers

    class Fake(workers.LatestFrameWorker):
        name = "fake"
        min_interval = 0.05

        def __init__(self):
            super().__init__()
            self.writes: list[tuple[float, object]] = []

        def write(self, frame):
            self.writes.append((real_time.monotonic(), frame))

    w = Fake()
    w.start()
    try:
        w.submit(0)
        real_time.sleep(0.02)                    # frame 0 is written; the next may start only 50 ms after it
        for i in range(1, 6):                    # a burst while the worker waits out the gap
            w.submit(i)
            real_time.sleep(0.005)
        real_time.sleep(0.12)
        w.submit(6)
        real_time.sleep(0.02)
    finally:
        w.stop()
    frames = [f for _, f in w.writes]
    assert frames == [0, 5, 6]                   # the burst became its newest frame, once
    starts = [t for t, _ in w.writes]
    assert all(b - a >= 0.05 - 0.002 for a, b in zip(starts, starts[1:]))


def test_worker_without_min_interval_writes_every_frame_at_once():
    import time as real_time

    from pitchcontrol.io import workers

    class Fake(workers.LatestFrameWorker):
        name = "fake"

        def __init__(self):
            super().__init__()
            self.frames = []

        def write(self, frame):
            self.frames.append(frame)

    assert workers.LatestFrameWorker.min_interval == 0.0
    assert workers.SerialWorker.min_interval == 0.0 and workers.OpenDmxWorker.min_interval == 1 / 30 - 0.0015
    w = Fake()
    w.start()
    try:
        for i in range(3):
            w.submit(i)
            real_time.sleep(0.02)
    finally:
        w.stop()
    assert w.frames == [0, 1, 2]


def test_open_dmx_min_interval_is_a_little_under_a_30_fps_frame():
    from pitchcontrol.io import workers

    assert workers.OpenDmxWorker.min_interval == pytest.approx(1 / 30 - 0.0015)
    assert 0.0317 < workers.OpenDmxWorker.min_interval < 0.0319


@pytest.mark.parametrize("method", ["baud", "break"])
def test_open_dmx_wire_guard_waits_until_the_last_frames_bytes_have_left(monkeypatch, method):
    from pitchcontrol.io import workers

    w, port = _open_dmx(monkeypatch, method)
    on_wire = 513 * workers.DMX_BYTE_S + workers.WIRE_MARGIN_S   # start code + 512 slots, plus the margin
    w.sleeps.clear()
    w.write(bytes([7] * 512))
    assert workers.DMX_BYTE_S == pytest.approx(44e-6) and on_wire == pytest.approx(0.0246, abs=1e-4)
    assert w._wire_free_at == pytest.approx(w.clock["t"] + on_wire)   # noted right before the bytes go to the port
    free_at = w._wire_free_at
    assert w.sleeps == ([w.BREAK_S, w.MARK_S] if method == "break" else [workers.WIRE_MARGIN_S])   # nothing to wait for on the first frame
    port.events.clear()
    w.sleeps.clear()
    w.clock["t"] = free_at - 0.010            # the next frame comes 10 ms before the wire is free
    w.write(bytes([8] * 512))
    assert w.sleeps[0] == pytest.approx(0.010)   # slept before the flush and the break
    assert port.events[0] == ("flush",)
    assert w.clock["t"] >= free_at
    w.sleeps.clear()
    w.clock["t"] = w._wire_free_at + 0.001   # a frame after the wire is free: no guard sleep
    w.write(bytes([9] * 512))
    assert w.sleeps == ([w.BREAK_S, w.MARK_S] if method == "break" else [workers.WIRE_MARGIN_S])


def test_open_dmx_wire_guard_resets_on_open(monkeypatch):
    w, port = _open_dmx(monkeypatch, "baud")
    w.write(bytes(512))
    assert w._wire_free_at > 0
    w.open()
    assert w._wire_free_at == 0.0


def test_worker_wait_for_the_min_interval_is_a_precise_sleep(monkeypatch):
    from pitchcontrol.io import workers

    sleeps: list[float] = []
    clock = {"t": 100.0}

    def fake_sleep(s):
        if s != 1.0:
            sleeps.append(s)
        clock["t"] += s
        w._stop.set()                          # stop during the wait: it must be seen right after the sleep

    class Fake(workers.LatestFrameWorker):
        name = "fake"
        min_interval = 0.03

        def write(self, frame):
            pass

    monkeypatch.setattr(workers.time, "perf_counter", lambda: clock["t"])
    monkeypatch.setattr(workers.time, "sleep", fake_sleep)
    w = Fake()
    w._last_start = clock["t"] - 0.01         # the last write started 10 ms ago
    w._frame = 1
    w._event.set()
    w._run()
    assert sleeps == [pytest.approx(0.02)]
    assert w.frames_sent == 0


def test_timer_resolution_is_a_no_op_off_windows(monkeypatch):
    from pitchcontrol import timer_resolution as tr

    calls = []
    monkeypatch.setattr(tr.sys, "platform", "darwin")
    monkeypatch.setattr(tr, "_winmm", lambda: calls.append("winmm"))
    tr.raise_resolution()
    tr.restore_resolution()
    assert calls == []


class _FakeWinmm:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def timeBeginPeriod(self, ms):
        self.calls.append(("begin", ms))
        if self.fail:
            raise OSError("no winmm")

    def timeEndPeriod(self, ms):
        self.calls.append(("end", ms))


def test_timer_resolution_on_windows_begins_and_ends_once(monkeypatch, caplog):
    import logging

    from pitchcontrol import timer_resolution as tr

    winmm = _FakeWinmm()
    monkeypatch.setattr(tr.sys, "platform", "win32")
    monkeypatch.setattr(tr, "_winmm", lambda: winmm)
    monkeypatch.setattr(tr, "_raised", False)
    with caplog.at_level(logging.INFO, logger="pitchcontrol.timer_resolution"):
        tr.raise_resolution()
        tr.raise_resolution()
        tr.restore_resolution()
        tr.restore_resolution()
    assert winmm.calls == [("begin", 1), ("end", 1)]
    assert [r.getMessage() for r in caplog.records] == ["Windows timer resolution set to 1 ms (precise frame timing)"]


def test_timer_resolution_failure_only_logs(monkeypatch, caplog):
    import logging

    from pitchcontrol import timer_resolution as tr

    winmm = _FakeWinmm(fail=True)
    monkeypatch.setattr(tr.sys, "platform", "win32")
    monkeypatch.setattr(tr, "_winmm", lambda: winmm)
    monkeypatch.setattr(tr, "_raised", False)
    with caplog.at_level(logging.WARNING, logger="pitchcontrol.timer_resolution"):
        tr.raise_resolution()
        tr.restore_resolution()                # nothing was raised: no end call
    assert winmm.calls == [("begin", 1)]
    assert "could not set the Windows timer resolution" in caplog.text
