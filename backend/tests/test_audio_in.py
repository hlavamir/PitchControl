"""AudioInput on devices with fewer inputs than the configured channels (item 25)."""

import json
import threading
import time

import numpy as np
import pytest

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


@pytest.fixture(autouse=True)
def _forget_child_failures():
    def forget():
        audio_in._child_failure[0] = None  # the fallback warning is logged once per change: every test starts afresh
        audio_in._last_listing[0] = None  # and the child's last answer (item 32) is not reused by the next test
        audio_in._child_logged_s[0] = None

    forget()
    yield
    forget()


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


def test_a_restart_reinitialises_portaudio_only_when_the_saved_device_isnt_listed(monkeypatch, store):
    """The Inputs page lists the devices as they are now (item 34), so a device plugged in after the start can be picked
    and saved before this process's PortAudio knows it: the restart that a save causes looks again, only then."""
    from pitchcontrol.engine.engine import Engine

    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)
    engine = Engine(store, enable_hardware=False)
    engine.enable_hardware = True  # the engine is built without opening devices; the restart checks the flag
    store.settings.audio.device = "Komplete Audio 6"
    engine.restart_audio()
    assert engine.audio.status()["device_missing"] and fake.calls == ["terminate", "initialize"]  # not listed: look again

    fake.calls.clear()
    fake.devices.append(INTERFACE)  # plugged in after the start
    first = engine.audio
    engine.restart_audio()  # the save that picks it
    st = engine.audio.status()
    assert fake.calls == ["terminate", "initialize"] and engine.audio is not first and not first.stream
    assert st["running"] and st["device"] == "Komplete Audio 6" and not st["device_missing"]

    # a device PortAudio lists is opened without a re-init, a channel fallback included
    fake.calls.clear()
    engine.restart_audio()
    assert fake.calls == [] and engine.audio.status()["running"]
    store.settings.audio.channels = [9]
    engine.restart_audio()
    assert engine.audio.status()["warning"] and not engine.audio.status()["device_missing"] and fake.calls == []

    # no device saved: the system default, no re-init; an explicit re-init (the watchdog) always looks again
    store.settings.audio.device = None
    engine.restart_audio()
    assert fake.calls == []
    engine.restart_audio(reinit=True)
    assert fake.calls == ["terminate", "initialize"]
    engine.audio.stop()


def test_the_audio_device_list_names_the_default_and_comes_from_the_fresh_listing(monkeypatch, store):
    from fastapi.testclient import TestClient

    import pitchcontrol.server.app as app_module
    from pitchcontrol.engine.engine import Engine

    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC, INTERFACE]))  # FakeSd.default.device is (0, 1): the input is MIC
    assert [d["default"] for d in audio_in.list_input_devices()] == [True, False]

    fresh = [dict(index=0, name="Komplete Audio 6", hostapi="Core Audio", label="Komplete Audio 6 (Core Audio)", channels=2, default_samplerate=48000.0, default=True)]
    monkeypatch.setattr(app_module, "list_input_devices_fresh", lambda: fresh)
    client = TestClient(app_module.create_app(Engine(store, enable_hardware=False)))
    assert client.get("/api/devices/audio").json() == fresh
    assert client.post("/api/devices/audio/rescan").status_code in (404, 405)  # the buttons and their endpoints are gone
    assert client.post("/api/devices/midi/rescan").status_code in (404, 405)


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
            engine.restart_audio(reinit=force)
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
    caplog.set_level(logging.INFO)

    def lines():
        return [r.getMessage() for r in caplog.records if r.getMessage().startswith("audio devices after re-init")]

    engine.restart_audio()  # the interface is unplugged: the stand-in runs, and the saved device isn't listed
    assert lines() == [
        "audio devices after re-init: 'MacBook Pro Microphone (Core Audio)'; saved device 'Komplete' NOT found"
    ]
    caplog.clear()
    fake.devices.append(INTERFACE)  # replugged
    engine.restart_audio()  # the save that picks it: not listed in this process yet, so it looks again
    assert lines() == [
        "audio devices after re-init: 'MacBook Pro Microphone (Core Audio)', 'Komplete Audio 6 (Core Audio)'; "
        "saved device 'Komplete' found"
    ]
    caplog.clear()
    engine.restart_audio()  # listed now: no re-init, nothing logged
    assert lines() == []
    engine.restart_audio(reinit=True)  # what the watchdog does after a re-plug
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


class _Child:
    """A fake ``subprocess.run`` for the child: counts its runs, takes ``seconds`` and answers with ``devices``."""

    def __init__(self, devices=(), seconds=0.0, fail=None):
        self.runs = 0
        self.seconds = seconds
        self.devices = list(devices)
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        import subprocess

        self.runs += 1
        time.sleep(self.seconds)
        if self.fail == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        class Done:
            returncode = 0
            stdout = json.dumps(self.devices).encode()
            stderr = b""

        return Done()


STEREO_LISTED = {"index": 3, "name": "Stereo Interface", "hostapi": "WASAPI", "label": "Stereo Interface (WASAPI)",
                 "channels": 2, "default_samplerate": 48000.0}


def test_the_child_has_ten_seconds_on_a_slow_windows_computer():
    assert audio_in.LIST_TIMEOUT_S == 10.0  # 2 s timed out four times on the owner's laptop (item 32)


def test_two_callers_at_once_share_one_child(monkeypatch):
    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC]))
    child = _Child([STEREO_LISTED], seconds=0.3)
    monkeypatch.setattr(audio_in.subprocess, "run", child)
    results = []
    threads = [threading.Thread(target=lambda: results.append(audio_in.list_input_devices_fresh())) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert child.runs == 1
    assert results == [[STEREO_LISTED]] * 3


def test_an_answer_younger_than_1_5_seconds_is_reused_and_an_older_one_is_not(monkeypatch):
    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC]))
    child = _Child([STEREO_LISTED])
    monkeypatch.setattr(audio_in.subprocess, "run", child)
    clock = [100.0]
    monkeypatch.setattr(audio_in.time, "monotonic", lambda: clock[0])
    audio_in.list_input_devices_fresh()
    clock[0] += 1.4
    audio_in.list_input_devices_fresh()
    assert child.runs == 1
    clock[0] += 0.2  # 1.6 s after the answer
    audio_in.list_input_devices_fresh()
    assert child.runs == 2


def test_a_caller_cannot_change_the_cached_list(monkeypatch):
    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC]))
    monkeypatch.setattr(audio_in.subprocess, "run", _Child([STEREO_LISTED]))
    audio_in.list_input_devices_fresh()[0]["label"] = "changed"
    assert audio_in.list_input_devices_fresh()[0]["label"] == "Stereo Interface (WASAPI)"


def test_a_timeout_falls_back_once_for_everyone_who_waited_and_says_the_limit(monkeypatch, caplog):
    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC]))
    child = _Child(seconds=0.2, fail="timeout")
    monkeypatch.setattr(audio_in.subprocess, "run", child)
    results = []
    with caplog.at_level("WARNING"):
        threads = [threading.Thread(target=lambda: results.append(audio_in.list_input_devices_fresh())) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
    assert child.runs == 1  # the waiting callers don't start a child of their own after the failure
    assert [[d["label"] for d in r] for r in results] == [["MacBook Pro Microphone (Core Audio)"]] * 3
    assert caplog.text.count("could not list the audio devices in a child process") == 1
    assert "timed out after 10 seconds, the limit" in caplog.text and "using this process's list" in caplog.text


def test_the_child_s_time_is_logged_the_first_time_and_when_it_gets_much_slower(monkeypatch, caplog):
    monkeypatch.setattr(audio_in, "sd", FakeSd([MIC]))
    child = _Child([STEREO_LISTED])
    clock = [0.0]

    def run(cmd, **kwargs):
        res = child(cmd, **kwargs)
        clock[0] += took[0]
        return res

    monkeypatch.setattr(audio_in.subprocess, "run", run)
    monkeypatch.setattr(audio_in.time, "monotonic", lambda: clock[0])
    took = [1.0]

    def listing():
        clock[0] += 10  # past LIST_MAX_AGE_S: every call runs the child
        audio_in.list_input_devices_fresh()

    with caplog.at_level("INFO", logger=audio_in.log.name):
        listing()
        assert "audio device list from a child process: 1.0 s" in caplog.text
        took[0] = 1.8  # not twice as slow
        listing()
        assert caplog.text.count("audio device list from a child process") == 1
        took[0] = 2.5  # more than twice the 1.0 s
        listing()
        assert caplog.text.count("audio device list from a child process") == 2 and "2.5 s" in caplog.text
        took[0] = 3.2  # past 3 s
        listing()
        assert caplog.text.count("audio device list from a child process") == 3 and "3.2 s" in caplog.text
        took[0] = 3.4  # slow, but not news
        listing()
        assert caplog.text.count("audio device list from a child process") == 3


def test_the_child_does_not_import_numpy():
    import subprocess
    import sys

    code = "import sys, pitchcontrol.io.audio_in; print('numpy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "False", out.stderr


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
    fake.calls.clear()  # the start looked again for the missing device (item 34); what the watchdog does is counted

    engine.audio_check()  # not plugged in: nothing is touched
    assert fake.calls == [] and engine.audio.device == "MacBook Pro Microphone"

    assert engine._audio_next_list > time.monotonic()  # it looks again in two seconds, not at once
    engine._audio_next_list = 0.0  # ... which is now
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
    engine._audio_next_list = 0.0  # the next look, two seconds later
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


def test_a_restart_that_runs_while_the_watchdog_looks_is_not_taken_for_a_drop(monkeypatch, store, caplog):
    import logging

    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    stopped, release = threading.Event(), threading.Event()

    def save_restart():  # what Save or Find new devices does: the old input is stopped, the new one opened a moment later
        with engine._audio_restart:
            engine.audio.stop()
            stopped.set()
            release.wait(2)
            engine.restart_audio()

    restarter = threading.Thread(target=save_restart)
    restarter.start()
    assert stopped.wait(2)
    with caplog.at_level(logging.INFO):
        looker = threading.Thread(target=engine.audio_check)
        looker.start()
        time.sleep(0.1)  # it waits for the restart instead of reading the stopped input
        assert looker.is_alive()
        release.set()
        restarter.join()
        looker.join()
    assert engine._audio_problem is None and engine.audio_status()["reconnect"] is None
    assert not [r for r in caplog.records if "audio input" in r.message and r.levelno >= logging.WARNING]
    assert engine.audio_status()["running"]
    engine.audio.stop()


def test_a_stall_that_recovered_while_the_list_was_read_costs_no_reinit(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    make_dead(engine)
    real_fresh = audio_in.list_input_devices_fresh

    def fresh_and_recover():  # the callbacks come again while the child lists the devices
        engine.audio._callback(np.zeros((4, 2), dtype="float32"), 4, None, None)
        return real_fresh()

    monkeypatch.setattr(audio_in, "list_input_devices_fresh", fresh_and_recover)
    engine.audio_check()
    assert fake.calls == [] and engine.audio_status()["running"]
    engine.audio.stop()


def test_a_device_that_stays_away_is_looked_for_less_often_after_a_minute(monkeypatch, store):
    engine, fake = watched_engine(monkeypatch, store, [MIC], "Komplete")  # missing at the start: the stand-in runs
    # A whole number, so that adding 2.0 and 10.0 is exact: from the real clock's value (seconds since boot, with
    # fractions) the sums round differently near a power of two (4194200.987 + 10.0 against five times + 2.0 differ by
    # 5e-10), and "every 10 s" came out as 9.9999999995 on a runner with such a clock.
    clock = [float(round(time.monotonic()))]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    engine.audio.last_callback = clock[0]  # the stand-in is alive on the fake clock
    lists: list[float] = []
    real = audio_in.list_input_devices_fresh

    def counted():
        lists.append(clock[0])
        return real()

    monkeypatch.setattr(audio_in, "list_input_devices_fresh", counted)
    t0 = clock[0]
    for _ in range(90):  # 180 s of looks, one every two seconds
        engine.audio._callback(np.zeros((4, 1), dtype="float32"), 4, None, None)  # the stand-in keeps running
        engine.audio_check()
        clock[0] += 2.0
    early = [t for t in lists if t - t0 < 60]
    late = [t for t in lists if t - t0 >= 60]
    assert len(early) >= 29  # about every 2 s
    assert 10 <= len(late) <= 13  # about every 10 s over the next 120 s
    assert all(b - a >= 10 for a, b in zip(late, late[1:]))
    fake.devices.append(INTERFACE)  # plugged in after all: found at the next look, however slow
    clock[0] += 10.0
    engine.audio_check()
    assert engine.audio_status()["device"] == "Komplete Audio 6"
    engine.audio.stop()


def test_the_lights_hold_their_look_while_the_input_is_dead(monkeypatch, store):
    """Item 30 (Miro): the look stays as it was, but a frozen signal gives no new strobo or peak triggers. (Holding the
    last frame of the signal would: the normalisation decays towards it and every band peaks over and over.)"""
    engine, fake = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    engine.outputs.send = lambda *a, **k: None
    rng = np.random.default_rng(1)
    for _ in range(120):  # a few seconds of music delivered by the running input, varying
        engine.analyzer.push((rng.uniform(-1, 1, 1200) * rng.uniform(0.2, 1.0)).astype("float32"))
        engine.tick(0.025)
    assert engine.features.values.max() > 0.5
    before = engine.features.values.copy()

    make_dead(engine)  # the cable is pulled: no more blocks
    fake.devices.remove(INTERFACE)
    triggers = 0
    for _ in range(400):  # ten seconds of frames at 40 fps
        engine.tick(0.025)
        assert engine.features.trigger_fraction == 0.0 and not engine.features.peak.any()
        triggers += bool(engine.phase.on_peak)
    assert np.array_equal(engine.features.values, before)  # the look is held, not released
    assert triggers == 0  # no new strobo trigger out of the frozen signal

    engine.macros.set("Manual Strobo", 1.0)  # the manual controls still work
    for _ in range(80):
        engine.tick(0.025)
        triggers += bool(engine.phase.on_peak)
    assert triggers >= 1
    engine.macros.set("Manual Strobo", 0.0)
    engine.audio.stop()


def test_the_analysis_starts_clean_when_the_input_is_back(monkeypatch, store):
    engine, _ = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    engine.outputs.send = lambda *a, **k: None
    rng = np.random.default_rng(2)
    for _ in range(80):
        engine.analyzer.push(rng.uniform(-1, 1, 1200).astype("float32"))
        engine.tick(0.025)
    make_dead(engine)
    for _ in range(20):
        engine.tick(0.025)
    assert engine.analyzer.envelope.max() == 0.0 and engine.analyzer.frame_max.max() == 0.0  # nothing stale is kept
    held = engine.features.values.copy()

    engine.audio.last_callback = time.monotonic()  # the device is back: blocks arrive again
    engine.audio.got_block = True
    engine.analyzer.push(rng.uniform(-1, 1, 4800).astype("float32"))
    engine.tick(0.025)
    assert not np.array_equal(engine.features.values, held)  # the values move again with the music
    engine.audio.stop()


def test_a_running_input_is_not_given_silence(monkeypatch, store):
    engine, _ = watched_engine(monkeypatch, store, [MIC, INTERFACE], "Komplete")
    engine.outputs.send = lambda *a, **k: None
    engine.audio.got_block = True
    engine.audio._callback(np.zeros((4, 2), dtype="float32"), 4, None, None)
    pushed = []
    monkeypatch.setattr(engine.analyzer, "push", lambda samples: pushed.append(len(samples)))
    engine.tick(0.025)
    assert pushed == []  # the audio thread feeds it, the engine adds nothing
    engine.audio.stop()


def test_the_fallback_warning_is_logged_once_per_change_not_every_two_seconds(monkeypatch, caplog):
    fake = FakeSd([MIC])
    monkeypatch.setattr(audio_in, "sd", fake)

    class Failed:
        returncode = 1
        stdout = b""
        stderr = b"OSError: PortAudio library not found"

    class Fine:
        returncode = 0
        stdout = b"[]"
        stderr = b""

    result = {"run": Failed}
    monkeypatch.setattr(audio_in.subprocess, "run", lambda *a, **k: result["run"]())
    with caplog.at_level("WARNING"):
        audio_in.list_input_devices_fresh()
        audio_in._last_listing[0] = None
        audio_in.list_input_devices_fresh()
        assert caplog.text.count("could not list the audio devices in a child process") == 1
        audio_in._last_listing[0] = None  # (the failure just seen is no older than LIST_MAX_AGE_S, which skips the child)
        result["run"] = Fine  # the child works again ...
        assert audio_in.list_input_devices_fresh() == []
        audio_in._last_listing[0] = None
        result["run"] = Failed  # ... and fails again: that is news again
        audio_in.list_input_devices_fresh()
    assert caplog.text.count("could not list the audio devices in a child process") == 2


def test_listing_the_devices_waits_while_portaudio_is_being_reinitialised(monkeypatch):
    """The Inputs page's fallback list (this process's PortAudio) must not query while a Save or the watchdog has
    PortAudio terminated: that overlap is what the lock is for."""
    gate = threading.Event()
    inside = threading.Event()

    class Blocking(FakeSd):
        def _terminate(self):
            super()._terminate()
            inside.set()
            gate.wait(5)  # terminated, not yet initialised again

    fake = Blocking([MIC, INTERFACE])
    monkeypatch.setattr(audio_in, "sd", fake)
    done: list[str] = []
    reinit = threading.Thread(target=lambda: (audio_in.reinit_portaudio("Komplete"), done.append("reinit")))
    reinit.start()
    assert inside.wait(2)
    listing = threading.Thread(target=lambda: (audio_in.list_input_devices(), done.append("list")))
    listing.start()
    time.sleep(0.3)
    assert done == []  # the listing is waiting for the re-init to finish
    gate.set()
    reinit.join(3)
    listing.join(3)
    assert sorted(done) == ["list", "reinit"] and done[0] == "reinit"
