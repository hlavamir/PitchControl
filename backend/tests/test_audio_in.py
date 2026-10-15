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
    assert st["running"] and st["device"] == "MacBook Pro Microphone"
    assert st["warning"] == (
        "'Komplete Audio 6' not found: using the system default (MacBook Pro Microphone). "
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


def test_rescan_restarts_only_an_input_that_isnt_running_as_configured(store):
    from fastapi.testclient import TestClient

    from pitchcontrol.engine.engine import Engine
    from pitchcontrol.server.app import create_app

    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True  # the app is built without opening devices; the endpoint checks the flag
    restarts = []

    class Input:
        def __init__(self, **status):
            self._status = {"running": True, "warning": None, "error": None, **status}

        def status(self):
            return self._status

    def restart():
        restarts.append(1)
        engine.audio = Input()

    engine.restart_audio = restart
    client = TestClient(create_app(engine))

    engine.audio = Input()
    assert client.post("/api/audio/rescan").status_code == 200
    assert restarts == []  # a working input isn't touched

    engine.audio = Input(warning="'Komplete Audio 6' not found: using the system default")
    assert client.post("/api/audio/rescan").json()["warning"] is None
    assert restarts == [1]

    engine.audio = Input(running=False, error="could not be opened")
    client.post("/api/audio/rescan")
    assert restarts == [1, 1]
