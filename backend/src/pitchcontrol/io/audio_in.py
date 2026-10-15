"""Audio input via sounddevice (PortAudio: CoreAudio on macOS, ASIO/WASAPI on Windows)."""

from __future__ import annotations

import logging
import os
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

# ASIO support in sounddevice's bundled PortAudio on Windows must be enabled before import
os.environ.setdefault("SD_ENABLE_ASIO", "1")

try:
    import sounddevice as sd
except OSError as exc:  # PortAudio missing
    sd = None
    log.error("sounddevice unavailable: %s", exc)


def list_input_devices() -> list[dict]:
    if sd is None:
        return []
    apis = sd.query_hostapis()
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
                }
            )
    return out


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
        sd._terminate()
        sd._initialize()
    except Exception as exc:  # noqa: BLE001
        log.error("PortAudio could not be re-initialised: %s", exc)
        return
    labels = [d["label"] for d in list_input_devices()]
    if not saved:
        verdict = "no device saved (the system default is used)"
    elif any(saved.lower() in label.lower() for label in labels):
        verdict = f"saved device '{saved}' found"
    else:
        verdict = f"saved device '{saved}' NOT found"
    log.info("audio devices after re-init: %s; %s", ", ".join(f"'{label}'" for label in labels) or "none", verdict)


def find_device(name: str | None) -> int | None:
    """Index of the first input device whose "name (host api)" label contains ``name``."""
    if not name:
        return None
    for d in list_input_devices():
        if name.lower() in d["label"].lower():
            return d["index"]
    log.warning("audio device '%s' not found, using the system default", name)
    return None


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
        self.level = 0.0  # peak input level of the last block (for the Inputs page meter)

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
            self.stream.start()
            self.device, self.device_inputs, self.used_channels = actual, inputs, used
            warnings = []
            if self.device_name and index is None:
                self.device_missing = True
                warnings.append(
                    f"'{self.device_name}' not found: listening to the system default ('{actual}'). "
                    "Plug it in and press Rescan devices."
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
                "Pick another device, or press Rescan devices if you just plugged it in."
            )
            log.error("audio input failed: %s", self.error)
            self.stream = None

    def _callback(self, indata, frames, time_info, status) -> None:  # audio thread
        if status:
            log.debug("audio status: %s", status)
        mono = indata[:, [c - 1 for c in self.used_channels]].sum(axis=1)
        self.level = float(np.abs(mono).max()) if len(mono) else 0.0
        self.on_samples(mono)

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:  # noqa: BLE001
                pass
        self.stream = None

    def status(self) -> dict:
        return {
            "running": self.stream is not None,
            "error": self.error,
            "warning": self.warning,
            "device_missing": self.device_missing,
            "device": self.device,
            "device_inputs": self.device_inputs,
            "channels": self.used_channels,
            "level": self.level,
        }
