"""Audio input via sounddevice (PortAudio: CoreAudio on macOS, ASIO/WASAPI on Windows)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # not imported at run time: the child that lists the devices (item 32) needs no numpy (about 35 ms of its start)
    import numpy as np

log = logging.getLogger(__name__)

# ASIO support in sounddevice's bundled PortAudio on Windows must be enabled before import
os.environ.setdefault("SD_ENABLE_ASIO", "1")

try:
    import sounddevice as sd
except OSError as exc:  # PortAudio missing
    sd = None
    log.error("sounddevice unavailable: %s", exc)


# PortAudio is not safe to query while it is terminated and initialised again: reinit_portaudio and everything in this
# process that asks for the devices take this lock (item 34: the Audio tab's list can fall back to this process
# every two seconds, while a Save or the watchdog restarts the audio input). Reentrant: a thread that holds it may ask again.
_PORTAUDIO = threading.RLock()


def list_input_devices() -> list[dict]:
    if sd is None:
        return []
    with _PORTAUDIO:
        apis = sd.query_hostapis()
        try:
            default = sd.default.device[0]  # what a stream opens when no device is chosen
        except Exception:  # noqa: BLE001 - the list matters more than which entry is the default
            default = -1
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                api = apis[d["hostapi"]]["name"]
                out.append(
                    {
                        "index": i,
                        "name": d["name"],
                        "hostapi": api,
                        "label": f"{d['name']} ({api})",
                        "channels": d["max_input_channels"],
                        "default_samplerate": d["default_samplerate"],
                        "default": i == default,
                    }
                )
        return out


def match_device(name: str | None, devices: list[dict]) -> dict | None:
    """The first of ``devices`` whose "name (host api)" label contains ``name`` (case-insensitive): the one rule by
    which the saved device is found, in this process and in a list read by another one (indices differ between
    processes, labels don't)."""
    if not name:
        return None
    return next((d for d in devices if name.lower() in d["label"].lower()), None)


LIST_FLAG = "--list-audio-devices"
# The child needs about 0.3 s on the Mac (item 32), but on the owner's Windows laptop 2 s was not enough, four times in a
# log: the frozen exe has to start, and PortAudio then enumerates every WDM-KS and Bluetooth hands-free device, which can
# take several seconds. The callers (the Audio tab's endpoint, the audio watchdog) are not the light engine's thread, so a
# longer wait costs nothing; the limit is only there so that a stuck driver cannot hang them for good.
LIST_TIMEOUT_S = 10.0
LIST_MAX_AGE_S = 1.5  # an answer this young is the answer: no new child (the Audio tab asks every 2 s, the watchdog too)
SLOW_CHILD_S = 3.0  # a listing this slow is worth a line in the log, whatever the one before took


_child_failure: list[str | None] = [None]  # why the last listing by the child failed, until one works again
# Item 32: one child at a time. A caller that finds a listing running waits for it (the lock) and then reads its answer
# from ``_last_listing`` instead of starting another child, which on a slow computer would queue one after the other.
_LIST_LOCK = threading.Lock()
_last_listing: list[tuple[float, list[dict] | None] | None] = [None]  # (time.monotonic() when it ended, devices; None = it failed)
_child_logged_s: list[float | None] = [None]  # the child's time at the last "audio device list from a child process" line


def _log_child_time(seconds: float) -> None:
    """One INFO line with how long the child took: the first time it works in a run, and again when it got much slower
    (twice the last time logged, or past ``SLOW_CHILD_S``), so that a Windows log says what the child really needs."""
    last = _child_logged_s[0]
    if last is None or seconds > 2 * last or (seconds > SLOW_CHILD_S and last <= SLOW_CHILD_S):
        _child_logged_s[0] = seconds
        log.info("audio device list from a child process: %.1f s", seconds)


def list_input_devices_fresh() -> list[dict]:
    """The input devices as they are right now, without touching the stream that is running: a short-lived child process
    has its own PortAudio, which enumerates the devices afresh when it starts, and opens no stream (the running stream
    would be closed by a re-init in this process). The ``index`` of each entry is the child's: match by label
    (``match_device``). Falls back to the list of this process, with a warning, if the child fails or takes longer than
    ``LIST_TIMEOUT_S``. One child runs at a time; a caller that arrives meanwhile, or within ``LIST_MAX_AGE_S`` of the
    end of the last one, gets that one's answer."""
    if sd is None:
        return []
    with _LIST_LOCK:
        last = _last_listing[0]
        if last is not None and time.monotonic() - last[0] < LIST_MAX_AGE_S:
            devices = last[1]
        else:
            devices = _run_list_child()
            _last_listing[0] = (time.monotonic(), devices)
    if devices is None:
        return list_input_devices()
    return [dict(d) for d in devices]


def _run_list_child() -> list[dict] | None:
    """Start the child and read its list; None, with the warning (once per change), if that didn't work."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, LIST_FLAG]  # the app binary itself, handled in packaging/app_entry.py before the app starts
    else:
        cmd = [sys.executable, "-m", "pitchcontrol.io.audio_in", LIST_FLAG]
    started = time.monotonic()
    try:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                timeout=LIST_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"timed out after {LIST_TIMEOUT_S:g} seconds, the limit") from None
        if res.returncode != 0:
            raise RuntimeError(f"exit code {res.returncode}: {res.stderr.decode(errors='replace').strip()[-200:]}")
        devices = json.loads(res.stdout.decode())
    except Exception as exc:  # noqa: BLE001
        if _child_failure[0] != str(exc):  # Connections asks every two seconds: say it when it changes, not every time
            _child_failure[0] = str(exc)
            log.warning("could not list the audio devices in a child process (%s): using this process's list", exc)
        return None
    _child_failure[0] = None
    _log_child_time(time.monotonic() - started)
    return devices


def list_devices_main() -> None:
    """The child's job (``--list-audio-devices``): print the input devices as JSON on stdout and exit. Written with
    ``os.write``: a windowed app has no ``sys.stdout`` on Windows."""
    os.write(1, json.dumps(list_input_devices()).encode())


def reinit_portaudio(saved: str | None = None) -> None:
    """Make PortAudio list the devices as they are now, and log them with whether the ``saved`` device is among them
    (one line, so that a replug that didn't work can be read from the log afterwards).

    PortAudio enumerates its devices once, when it is initialised, so a device plugged in after the start only shows up
    after a terminate and initialise. All streams must be closed first. (``_terminate``/``_initialize`` are
    sounddevice's own, underscored, but it has no public call for this.)
    """
    if sd is None:
        return
    try:
        with _PORTAUDIO:
            sd._terminate()
            sd._initialize()
    except Exception as exc:  # noqa: BLE001
        log.error("PortAudio could not be re-initialised: %s", exc)
        return
    labels = [d["label"] for d in list_input_devices()]
    if not saved:
        verdict = "no device saved (the system default is used)"
    elif match_device(saved, [{"label": label} for label in labels]):
        verdict = f"saved device '{saved}' found"
    else:
        verdict = f"saved device '{saved}' NOT found"
    log.info("audio devices after re-init: %s; %s", ", ".join(f"'{label}'" for label in labels) or "none", verdict)


def find_device(name: str | None) -> int | None:
    """Index of the first input device whose "name (host api)" label contains ``name``."""
    if not name:
        return None
    found = match_device(name, list_input_devices())
    if found:
        return found["index"]
    log.warning("audio device '%s' not found, using the system default", name)
    return None


DEAD_AFTER_S = 0.5  # no callback for this long: the stream is dead (item 29: a pulled interface just stops the callbacks)
FIRST_CALLBACK_S = 2.0  # a slow driver may take longer for the first block than the gap between two


class AudioInput:
    def __init__(self, device: str | None, channels: list[int], sample_rate: int, on_samples: Callable[[np.ndarray], None]):
        self.device_name = device
        self.channels = [c for c in channels if c >= 1] or [1]
        self.sample_rate = sample_rate
        self.on_samples = on_samples
        self.stream = None
        self.error: str | None = None
        self.warning: str | None = None  # the input runs, but not as configured
        self.device_missing = False  # the configured device wasn't found: the system default is used
        self.device: str | None = None  # the device actually opened
        self.device_inputs = 0
        self.used_channels: list[int] = self.channels  # the requested channels the device has
        self.level = 0.0  # peak input level of the last block (for the meter of Connections → Audio)
        self.last_callback: float | None = None  # time.monotonic() of the last block, or of the start before the first
        self.got_block = False  # the callback has run at least once since the start

    def start(self) -> None:
        self.error = None
        self.warning = None
        self.device_missing = False
        self.device, self.device_inputs, self.used_channels = None, 0, self.channels
        if sd is None:
            self.error = "sounddevice / PortAudio not available"
            return
        name = self.device_name or "system default"
        try:
            index = find_device(self.device_name)
            with _PORTAUDIO:
                info = sd.query_devices(index if index is not None else sd.default.device[0])
            actual = info["name"]
            name = actual
            inputs = info["max_input_channels"]
            if inputs < 1:
                raise ValueError("it has no inputs")
            # A device with fewer inputs than requested (a laptop microphone has one) runs on the channels it has.
            # The saved channels stay as they are, so they work again when the interface is back.
            used = [c for c in self.channels if c <= inputs] or [1]
            fallback = not any(c <= inputs for c in self.channels)
            self.stream = sd.InputStream(
                device=index,
                channels=max(used),
                samplerate=self.sample_rate,
                dtype="float32",
                callback=self._callback,
            )
            self.got_block = False
            self.last_callback = time.monotonic()
            self.stream.start()
            self.device, self.device_inputs, self.used_channels = actual, inputs, used
            warnings = []
            if self.device_name and index is None:
                self.device_missing = True
                warnings.append(
                    f"'{self.device_name}' not found: listening to the system default ('{actual}'). "
                    "It switches back by itself when it's plugged in."
                )
            if fallback:
                wanted = ", ".join(map(str, self.channels))
                valid = "1" if inputs == 1 else "1 or 2" if inputs == 2 else f"1 to {inputs}"
                warnings.append(
                    f"'{actual}' has {inputs} input{'s' if inputs != 1 else ''}, "
                    f"channel{'s' if len(self.channels) != 1 else ''} {wanted} "
                    f"{'do' if len(self.channels) != 1 else 'does'}n't exist: listening to channel 1. "
                    f"Set Input channels to {valid}."
                )
            if warnings:
                self.warning = " ".join(warnings)
                log.warning("audio input: %s", self.warning)
            log.info("audio input: '%s', channels %s, %d Hz", actual, used, self.sample_rate)
        except Exception as exc:  # noqa: BLE001
            self.error = (
                f"'{name}' could not be opened ({exc}). "
                "Another program may be using it: close that program and it reconnects by itself, or pick another device."
            )
            log.error("audio input failed: %s", self.error)
            self.stream = None

    def _callback(self, indata, frames, time_info, status) -> None:  # audio thread
        if status:
            log.debug("audio status: %s", status)
        self.last_callback = time.monotonic()  # the age of this is what says the stream is dead (see ``dead``)
        self.got_block = True
        mono = indata[:, [c - 1 for c in self.used_channels]].sum(axis=1)
        self.level = float(abs(mono).max()) if len(mono) else 0.0
        self.on_samples(mono)

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:  # noqa: BLE001
                pass
        self.stream = None

    @property
    def dead(self) -> bool:
        """The stream is open but no longer delivers blocks: the device was pulled, or the driver stopped. Judged from the
        age of the last block, so it needs no PortAudio call from another thread (``stream.active`` would)."""
        if self.stream is None or self.last_callback is None:
            return False
        limit = DEAD_AFTER_S if self.got_block else FIRST_CALLBACK_S
        return time.monotonic() - self.last_callback > limit

    @property
    def delivering(self) -> bool:
        """Blocks are arriving: a stream is open and not dead. What the analysis may rely on."""
        return self.stream is not None and not self.dead

    def last_block_epoch(self) -> float | None:
        """Wall-clock time of the last block (for "lost 21:13:58"), or None before the stream was started."""
        if self.last_callback is None:
            return None
        return time.time() - (time.monotonic() - self.last_callback)

    def status(self) -> dict:
        dead = self.dead
        error = self.error
        if dead:  # a dead stream is not running, whatever the stream object says
            error = (
                f"'{self.device}' disappeared. Check the cable: it reconnects by itself when the device is back."
            )
        return {
            "running": self.stream is not None and not dead,
            "error": error,
            "warning": None if dead else self.warning,
            "device_missing": self.device_missing,
            "device": self.device,
            "device_inputs": self.device_inputs,
            "channels": self.used_channels,
            "level": 0.0 if dead else self.level,
            "dead": dead,
        }


if __name__ == "__main__":  # python -m pitchcontrol.io.audio_in --list-audio-devices (the child, in a source run)
    if LIST_FLAG in sys.argv:
        list_devices_main()
