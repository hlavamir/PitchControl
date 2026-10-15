"""AudioInput on devices with fewer inputs than the configured channels (item 25)."""

import numpy as np

from pitchcontrol.io import audio_in


class FakeStream:
    def __init__(self, fail=False, **kwargs):
        self.kwargs = kwargs
        self.fail = fail
        self.started = False

    def start(self):
        if self.fail:
            raise RuntimeError("Error opening InputStream: Invalid number of channels")
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        pass


class FakeSd:
    """Stands in for ``sounddevice``: two devices, a built-in microphone with 1 input and an interface with 6."""

    class default:
        device = (0, 1)

    def __init__(self, devices, fail=False):
        self.devices = devices
        self.fail = fail
        self.streams: list[FakeStream] = []
        self.calls: list[str] = []

    def _terminate(self):
        self.calls.append("terminate")

    def _initialize(self):
        self.calls.append("initialize")

    def query_devices(self, index=None):
        if index is None:
            return [dict(d, hostapi=0) for d in self.devices]
        return dict(self.devices[index], hostapi=0)

    def query_hostapis(self):
        return [{"name": "Core Audio"}]

    def InputStream(self, **kwargs):  # noqa: N802
        stream = FakeStream(fail=self.fail, **kwargs)
        self.streams.append(stream)
        return stream


MIC = {"name": "MacBook Pro Microphone", "max_input_channels": 1, "default_samplerate": 48000.0}
INTERFACE = {"name": "Komplete Audio 6", "max_input_channels": 6, "default_samplerate": 48000.0}
STEREO = {"name": "Stereo Interface", "max_input_channels": 2, "default_samplerate": 48000.0}


def make(monkeypatch, devices, device, channels, fail=False):
    fake = FakeSd(devices, fail=fail)
    monkeypatch.setattr(audio_in, "sd", fake)
    got: list[np.ndarray] = []
    inp = audio_in.AudioInput(device, channels, 48000, got.append)
    inp.start()
    return inp, fake, got


def test_one_input_device_with_default_channels_runs_on_channel_one_without_a_warning(monkeypatch):
    inp, fake, got = make(monkeypatch, [MIC, INTERFACE], "MacBook Pro", [1, 2])
    st = inp.status()
    assert st["running"] and st["error"] is None and st["warning"] is None
    assert st["channels"] == [1] and st["device_inputs"] == 1 and st["device"] == "MacBook Pro Microphone"
    assert fake.streams[0].kwargs["channels"] == 1
    assert inp.channels == [1, 2]  # the saved setting is untouched
    inp._callback(np.array([[0.25], [0.5]], dtype="float32"), 2, None, None)
    assert inp.status()["level"] == 0.5
    assert got[0].tolist() == [0.25, 0.5]


def test_no_requested_channel_exists_falls_back_to_channel_one_with_a_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [STEREO], "Stereo", [3])
    st = inp.status()
    assert st["running"] and st["channels"] == [1]
    assert fake.streams[0].kwargs["channels"] == 1
    assert st["warning"] == (
        "'Stereo Interface' has 2 inputs, channel 3 doesn't exist: listening to channel 1. Set Input channels to 1 or 2."
    )


def test_enough_inputs_open_the_requested_channels_without_a_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [MIC, INTERFACE], "Komplete", [1, 2])
    st = inp.status()
    assert st["running"] and st["warning"] is None and st["error"] is None
    assert st["channels"] == [1, 2] and st["device_inputs"] == 6
    assert fake.streams[0].kwargs["channels"] == 2


def test_missing_device_uses_the_system_default_with_a_warning(monkeypatch):
    inp, _, _ = make(monkeypatch, [MIC], "Komplete Audio 6", [1, 2])
    st = inp.status()
    assert st["running"] and st["device"] == "MacBook Pro Microphone" and st["device_missing"]
    assert st["warning"] == (
        "'Komplete Audio 6' not found: listening to the system default ('MacBook Pro Microphone'). "
        "Plug it in and press Rescan devices."
    )


def test_stream_that_fails_to_open_is_an_error_naming_the_device(monkeypatch):
    inp, _, _ = make(monkeypatch, [MIC], "MacBook", [1], fail=True)
    st = inp.status()
    assert not st["running"]
    assert st["error"].startswith("'MacBook Pro Microphone' could not be opened (")
    assert st["error"].endswith("press Rescan devices if you just plugged it in.")
    assert st["warning"] is None


def test_restart_clears_the_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [MIC], "Komplete", [1, 2])
    assert inp.status()["warning"]
    fake.devices.append(INTERFACE)
    inp.stop()
    inp.start()
    st = inp.status()
    assert st["warning"] is None and st["device"] == "Komplete Audio 6" and st["channels"] == [1, 2]


def test_rescan_reinitialises_portaudio_only_for_an_input_that_isnt_on_the_saved_device(monkeypatch, store):
    from pitchcontrol.engine.engine import Engine

    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True  # the engine is built without opening devices; the rescan checks the flag
    store.settings.audio.device = "Komplete Audio 6"
    engine.restart_audio()
    assert engine.audio.status()["device_missing"] and fake.calls == []

    # the interface is plugged in after the start: a rescan re-initialises PortAudio and the input moves to it
    fake.devices.append(INTERFACE)
    first = engine.audio
    st = engine.rescan_audio()
    assert fake.calls == ["terminate", "initialize"]
    assert engine.audio is not first and not first.stream
    assert st["running"] and st["device"] == "Komplete Audio 6" and not st["device_missing"]

    # a working input on the saved device is left alone
    fake.calls.clear()
    streams = len(fake.streams)
    working = engine.audio
    assert engine.rescan_audio()["running"]
    assert fake.calls == [] and engine.audio is working and len(fake.streams) == streams

    # a channel fallback is on the saved device: left alone as well
    store.settings.audio.channels = [9]
    engine.restart_audio()
    assert engine.audio.status()["warning"] and not engine.audio.status()["device_missing"]
    fake.calls.clear()
    engine.rescan_audio()
    assert fake.calls == []

    # an input that isn't running (the stream fails to open) is reopened
    fake.fail = True
    engine.restart_audio()
    assert not engine.audio.status()["running"]
    fake.fail = False
    engine.rescan_audio()
    assert fake.calls == ["terminate", "initialize"] and engine.audio.status()["running"]
    engine.audio.stop()


def test_rescan_endpoint(store):
    from fastapi.testclient import TestClient

    from pitchcontrol.engine.engine import Engine
    from pitchcontrol.server.app import create_app

    engine = Engine(store, enable_hardware=False)  # no hardware: nothing to rescan
    client = TestClient(create_app(engine))
    r = client.post("/api/devices/audio/rescan")
    assert r.status_code == 200 and r.json() is None
