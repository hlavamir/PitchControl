"""AudioInput on devices with fewer inputs than the configured channels (item 25)."""

import threading
import time

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
    """Stands in for ``sounddevice``. Like PortAudio it lists the devices of the moment it was initialised: a device
    added to ``devices`` ("plugged in") is only listed after ``_terminate()`` and ``_initialize()``."""

    class default:
        device = (0, 1)

    def __init__(self, devices, fail=False):
        self.devices = devices
        self.listed = list(devices)
        self.fail = fail
        self.streams: list[FakeStream] = []
        self.calls: list[str] = []
        self.slow = False
        self.in_reinit = False

    def _terminate(self):
        self.calls.append("terminate")
        if self.slow:
            assert not self.in_reinit, "PortAudio terminated while it was being re-initialised"
            self.in_reinit = True
            time.sleep(0.05)

    def _initialize(self):
        self.calls.append("initialize")
        self.listed = list(self.devices)
        self.in_reinit = False

    def query_devices(self, index=None):
        if index is None:
            return [dict(d, hostapi=0) for d in self.listed]
        return dict(self.listed[index], hostapi=0)

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
        "It switches back by itself when it's plugged in."
    )


def test_stream_that_fails_to_open_is_an_error_naming_the_device(monkeypatch):
    inp, _, _ = make(monkeypatch, [MIC], "MacBook", [1], fail=True)
    st = inp.status()
    assert not st["running"]
    assert st["error"].startswith("'MacBook Pro Microphone' could not be opened (")
    assert st["error"].endswith("Another program may be using it: close that program and it reconnects by itself, or pick another device.")
    assert st["warning"] is None


def test_restart_clears_the_warning(monkeypatch):
    inp, fake, _ = make(monkeypatch, [MIC], "Komplete", [1, 2])
    assert inp.status()["warning"]
    fake.devices.append(INTERFACE)
    inp.stop()
    inp.start()
    assert inp.status()["device_missing"]  # not listed: PortAudio was not re-initialised
    inp.stop()
    audio_in.reinit_portaudio()
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

    # the interface is plugged in after the start: PortAudio doesn't list it until a rescan re-initialises it
    fake.devices.append(INTERFACE)
    engine.restart_audio()
    assert engine.audio.status()["device_missing"] and fake.calls == []
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


def test_find_new_devices_reinitialises_even_while_the_input_runs(monkeypatch, store):
    from pitchcontrol.engine.engine import Engine

    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    engine.restart_audio()
    assert engine.audio.status()["running"] and fake.calls == []

    fake.devices.append(INTERFACE)  # plugged in while the microphone is listened to
    assert "Komplete Audio 6" not in [d["label"].split(" (")[0] for d in audio_in.list_input_devices()]
    old = engine.audio
    st = engine.rescan_audio(force=True)
    assert fake.calls == ["terminate", "initialize"] and engine.audio is not old and old.stream is None
    assert st["running"]
    assert "Komplete Audio 6" in [d["label"].split(" (")[0] for d in audio_in.list_input_devices()]
    engine.audio.stop()


def test_audio_restarts_run_one_after_the_other(monkeypatch, store):
    from pitchcontrol.engine.engine import Engine

    fake = FakeSd([MIC, INTERFACE])
    monkeypatch.setattr(audio_in, "sd", fake)
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    engine.restart_audio()
    fake.slow = True  # a re-init takes a while, so that two threads would overlap in it without the lock
    errors = []

    def go(force):
        try:
            engine.rescan_audio(force=force)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(True,)) for _ in range(3)]
    threads.append(threading.Thread(target=engine.restart_audio))  # a settings save
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert fake.calls == ["terminate", "initialize"] * 3
    assert sum(1 for st in fake.streams if st.started) == 1  # one open stream, not two
    assert engine.audio.status()["running"]
    engine.audio.stop()


def test_every_reinit_logs_the_device_list_and_whether_the_saved_device_was_found(monkeypatch, store, caplog):
    import logging

    from pitchcontrol.engine.engine import Engine

    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)
    store.settings.audio.device = "Komplete"
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    engine.restart_audio()  # the interface is unplugged: the stand-in runs
    caplog.set_level(logging.INFO)

    def lines():
        return [r.getMessage() for r in caplog.records if r.getMessage().startswith(("audio devices after re-init", "rescan devices"))]

    engine.rescan_audio()  # "Rescan devices"
    assert lines() == [
        "audio devices after re-init: 'MacBook Pro Microphone (Core Audio)'; saved device 'Komplete' NOT found"
    ]
    caplog.clear()
    fake.devices.append(INTERFACE)  # replugged
    engine.rescan_audio(force=True)  # "Find new devices"
    assert lines() == [
        "audio devices after re-init: 'MacBook Pro Microphone (Core Audio)', 'Komplete Audio 6 (Core Audio)'; "
        "saved device 'Komplete' found"
    ]
    caplog.clear()
    engine.rescan_audio()  # runs on the saved device: left alone, and the log says so
    assert lines() == ["rescan devices: the audio input runs on 'Komplete Audio 6', left alone"]
    caplog.clear()
    engine.restart_audio(reinit=True)  # what a settings save that changes the device does after a re-init
    assert len(lines()) == 1 and lines()[0].endswith("saved device 'Komplete' found")
    engine.audio.stop()


# ---------------------------------------------------------------- the device list read by a child process (item 32)
def test_the_child_process_lists_the_devices_of_this_computer_without_this_processes_portaudio(monkeypatch):
    import pytest

    if audio_in.sd is None:
        pytest.skip("PortAudio is not available here")
    real = audio_in.list_input_devices()
    fresh = audio_in.list_input_devices_fresh()  # runs `python -m pitchcontrol.io.audio_in --list-audio-devices`
    assert [d["label"] for d in fresh] == [d["label"] for d in real]
    assert all({"index", "name", "hostapi", "label", "channels", "default_samplerate"} <= d.keys() for d in fresh)


def test_fresh_list_leaves_the_running_streams_portaudio_alone(monkeypatch):
    fake = FakeSd([MIC, INTERFACE])
    monkeypatch.setattr(audio_in, "sd", fake)
    inp = audio_in.AudioInput("Komplete", [1, 2], 48000, lambda s: None)
    inp.start()
    fake.devices.append(STEREO)  # plugged in after the start

    class Done:
        returncode = 0
        stdout = b'[{"index": 3, "name": "Stereo Interface", "hostapi": "Core Audio", "label": "Stereo Interface (Core Audio)", "channels": 2, "default_samplerate": 48000.0}]'
        stderr = b""

    monkeypatch.setattr(audio_in.subprocess, "run", lambda *a, **k: Done())  # the child, which has its own PortAudio
    fresh = audio_in.list_input_devices_fresh()
    assert [d["label"] for d in fresh] == ["Stereo Interface (Core Audio)"]
    assert fake.calls == [] and inp.stream.started and inp.status()["running"]  # not terminated, not closed
    inp.stop()


def test_fresh_list_falls_back_to_this_processs_list_when_the_child_hangs(monkeypatch, caplog):
    import subprocess
    import sys

    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)
    monkeypatch.setattr(audio_in, "LIST_TIMEOUT_S", 0.3)
    real_run = subprocess.run
    monkeypatch.setattr(
        audio_in.subprocess, "run", lambda cmd, **k: real_run([sys.executable, "-c", "import time; time.sleep(10)"], **k)
    )
    t0 = time.monotonic()
    fresh = audio_in.list_input_devices_fresh()
    assert time.monotonic() - t0 < 3
    assert [d["label"] for d in fresh] == ["MacBook Pro Microphone (Core Audio)"]
    assert "could not list the audio devices in a child process" in caplog.text


def test_fresh_list_falls_back_when_the_child_fails(monkeypatch):
    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)

    class Failed:
        returncode = 1
        stdout = b""
        stderr = b"Traceback ... OSError: PortAudio library not found"

    monkeypatch.setattr(audio_in.subprocess, "run", lambda *a, **k: Failed())
    assert [d["label"] for d in audio_in.list_input_devices_fresh()] == ["MacBook Pro Microphone (Core Audio)"]


def test_match_device_is_one_rule_for_both_lists():
    devices = [{"label": "Komplete Audio 6 (Core Audio)"}, {"label": "MacBook Pro Microphone (Core Audio)"}]
    assert audio_in.match_device("komplete", devices) is devices[0]
    assert audio_in.match_device("Komplete Audio 6 (Core Audio)", devices) is devices[0]
    assert audio_in.match_device("Scarlett", devices) is None
    assert audio_in.match_device(None, devices) is None and audio_in.match_device("", devices) is None


# ---------------------------------------------------------------- the input reconnects by itself (item 30)
def watched_engine(monkeypatch, store, devices, saved, channels=(1, 2)):
    """An engine with the fake PortAudio and a fake child (``list_input_devices_fresh`` lists ``fake.devices`` as they
    are right now, as a new process would). Returns (engine, fake). ``engine.audio_check()`` is one look of the watchdog."""
    from pitchcontrol.engine.engine import Engine

    fake = FakeSd(devices)
    monkeypatch.setattr(audio_in, "sd", fake)

    def fresh():
        return [
            {"index": i, "name": d["name"], "label": f"{d['name']} (Core Audio)", "channels": d["max_input_channels"]}
            for i, d in enumerate(fake.devices)
        ]

    monkeypatch.setattr(audio_in, "list_input_devices_fresh", fresh)
    store.settings.audio.device = saved
    store.settings.audio.channels = list(channels)
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True
    engine.restart_audio()
    return engine, fake


def make_dead(engine):
    """The callbacks stopped (a pulled cable) long enough ago."""
    engine.audio.got_block = True
    engine.audio.last_callback = time.monotonic() - 5


def test_a_stream_without_callbacks_is_dead_and_not_running(monkeypatch):
    inp, _, _ = make(monkeypatch, [MIC, INTERFACE], "Komplete", [1, 2])
    inp._callback(np.zeros((4, 2), dtype="float32"), 4, None, None)
    assert inp.status()["running"] and not inp.status()["dead"]
    inp.last_callback = time.monotonic() - (audio_in.DEAD_AFTER_S + 0.1)
    st = inp.status()
    assert st["dead"] and not st["running"] and st["level"] == 0.0 and st["warning"] is None
    assert st["error"] == "'Komplete Audio 6' disappeared. Check the cable: it reconnects by itself when the device is back."
    inp._callback(np.zeros((4, 2), dtype="float32"), 4, None, None)  # blocks come again
    assert inp.status()["running"]


def test_a_slow_first_block_is_not_dead(monkeypatch):
    inp, _, _ = make(monkeypatch, [INTERFACE], "Komplete", [1])
    inp.last_callback = time.monotonic() - (audio_in.DEAD_AFTER_S + 0.1)  # no block yet, 0.6 s after the start
    assert inp.status()["running"]
    inp.last_callback = time.monotonic() - (audio_in.FIRST_CALLBACK_S + 0.1)
    assert inp.status()["dead"]


def test_a_device_missing_at_the_start_is_switched_to_when_it_appears(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC], "Komplete")
    assert engine.audio.status()["device"] == "MacBook Pro Microphone" and engine.audio.device_missing

    engine.audio_check()  # not plugged in: nothing is touched
    assert fake.calls == [] and engine.audio.device == "MacBook Pro Microphone"

    fake.devices.append(INTERFACE)
    engine.audio_check()
    st = engine.audio_status()
    assert st["running"] and st["device"] == "Komplete Audio 6" and not st["device_missing"] and st["warning"] is None
    assert fake.calls == ["terminate", "initialize"]
    assert st["reconnect"]["lost"] is None and st["reconnect"]["back"] is not None  # "missing at start · back …"
    engine.audio.stop()


def test_a_dead_stream_shows_stopped_and_runs_again_when_the_device_is_back(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    assert engine.audio.device == "Komplete Audio 6"
    make_dead(engine)
    fake.devices.remove(INTERFACE)  # pulled out

    engine.audio_check()  # not listed: nothing is touched, and no other device is switched to
    st = engine.audio_status()
    assert not st["running"] and "disappeared" in st["error"] and st["reconnect"]["lost"] is not None
    assert st["reconnect"]["back"] is None and fake.calls == []

    engine.audio_check()  # and again: still nothing, no reconnect to the microphone
    assert fake.calls == [] and not engine.audio_status()["running"]

    fake.devices.append(INTERFACE)  # plugged in
    engine.audio_check()
    st = engine.audio_status()
    assert st["running"] and st["device"] == "Komplete Audio 6" and st["error"] is None
    assert st["reconnect"]["lost"] < st["reconnect"]["back"]  # "lost 21:13:58 · back 21:14:05"
    assert st["reconnect"]["lost_device"] == st["reconnect"]["back_device"] == "Komplete Audio 6"
    engine.audio.stop()


def test_a_dead_stream_never_reconnects_to_another_device(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    make_dead(engine)
    fake.devices.remove(INTERFACE)
    for _ in range(3):
        engine.audio_check()
    assert [s.kwargs.get("device") for s in fake.streams] == [1]  # only the first open, on the interface
    assert engine.audio.device == "Komplete Audio 6" and not engine.audio_status()["running"]
    engine.audio.stop()


def test_without_a_saved_device_a_dead_stream_restarts_on_the_system_default(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], None)
    make_dead(engine)
    engine.audio_check()
    st = engine.audio_status()
    assert st["running"] and st["reconnect"]["back"] is not None and fake.calls == ["terminate", "initialize"]
    assert st["reconnect"]["lost_device"] == "MacBook Pro Microphone"  # the fake lists the microphone first: same device
    engine.audio.stop()


def test_a_listed_device_that_wont_open_is_retried_after_a_pause(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    make_dead(engine)
    fake.fail = True  # the device is there but busy
    engine.audio_check()
    assert not engine.audio_status()["running"] and fake.calls == ["terminate", "initialize"]
    engine.audio_check()  # within the pause: not tried again
    assert fake.calls == ["terminate", "initialize"]
    engine._audio_retry_at = 0.0
    fake.fail = False  # the other program let go
    engine.audio_check()
    assert engine.audio_status()["running"]
    engine.audio.stop()


def test_saving_another_device_forgets_the_drop(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    make_dead(engine)
    fake.devices.remove(INTERFACE)
    engine.audio_check()
    assert engine.audio_status()["reconnect"]["lost"] is not None
    store.settings.audio.device = "MacBook"  # the user picks the microphone and saves
    engine.restart_audio(reinit=True)
    engine.audio_check()
    st = engine.audio_status()
    assert st["running"] and st["reconnect"] is None
    engine.audio.stop()


def test_the_drop_is_logged_once_not_at_every_look(monkeypatch, store, caplog):
    import logging

    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    make_dead(engine)
    fake.devices.remove(INTERFACE)
    with caplog.at_level(logging.INFO):
        for _ in range(4):
            engine.audio_check()
    assert sum("stopped delivering audio" in r.message for r in caplog.records) == 1
    engine.audio.stop()
