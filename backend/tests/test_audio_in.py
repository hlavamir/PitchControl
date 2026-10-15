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


def test_one_input_device_runs_on_channel_one_with_a_warning(monkeypatch):
    inp, fake, got = make(monkeypatch, [MIC, INTERFACE], "MacBook Pro", [1, 2])
    st = inp.status()
    assert st["running"] and st["error"] is None
    assert st["channels"] == [1] and st["device_inputs"] == 1
    assert fake.streams[0].kwargs["channels"] == 1
    assert st["warning"] == "'MacBook Pro Microphone': device has 1 input, using channel 1 (channel 2 ignored)"
    assert inp.channels == [1, 2]  # the saved setting is untouched
    inp._callback(np.array([[0.25], [0.5]], dtype="float32"), 2, None, None)
    assert inp.status()["level"] == 0.5
    assert got[0].tolist() == [0.25, 0.5]


def test_missing_channel_falls_back_to_channel_one(monkeypatch):
    inp, fake, _ = make(monkeypatch, [STEREO], "Stereo", [3])
    st = inp.status()
    assert st["running"] and st["channels"] == [1]
    assert fake.streams[0].kwargs["channels"] == 1
    assert "channel 3 ignored" in st["warning"]


def test_enough_inputs_open_the_requested_channels_without_a_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [MIC, INTERFACE], "Komplete", [1, 2])
    st = inp.status()
    assert st["running"] and st["warning"] is None and st["error"] is None
    assert st["channels"] == [1, 2] and st["device_inputs"] == 6
    assert fake.streams[0].kwargs["channels"] == 2


def test_stream_that_fails_to_open_is_an_error_naming_the_device(monkeypatch):
    inp, _, _ = make(monkeypatch, [MIC], "MacBook", [1], fail=True)
    st = inp.status()
    assert not st["running"]
    assert st["error"].startswith("'MacBook Pro Microphone': ")
    assert st["warning"] is None


def test_restart_clears_the_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [MIC, INTERFACE], "MacBook", [1, 2])
    assert inp.status()["warning"]
    fake.devices[0] = dict(MIC, max_input_channels=2)
    inp.stop()
    inp.start()
    assert inp.status()["warning"] is None and inp.status()["channels"] == [1, 2]
