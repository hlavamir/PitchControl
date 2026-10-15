#!/usr/bin/env python3
"""Find out what PortAudio does to an open input stream when the interface is unplugged (item 29, not shipped).

Close PitchControl first (an interface can be opened by two programs, but then you measure both), then:

    backend/.venv/bin/python tools/audio_stream_probe.py [--device "Komplete Audio 6"] [--channels 1,2]
                                                          [--out probe.log]

It opens the input the way the app does (``AudioInput``: the saved device from this computer's ``machine.json`` unless
``--device`` is given) and prints, every second and at every change, ten times a second what the stream shows:
callbacks so far, the age of the last callback, the status flags PortAudio passed to it, ``stream.active`` and
``stream.stopped``, the peak of the last second and whether the last blocks were digital silence (every sample exactly 0).
Press Enter to run what the app's "Find new devices" does (close, re-initialise PortAudio, list the devices, open the
saved one again). Ctrl-C ends it. The whole output goes to ``--out`` as well, so it can be sent.

The test: start it, wait 5 s, pull the interface's USB cable, wait 5 s, plug it in again, wait 5 s, press Enter, wait
5 s, Ctrl-C.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import numpy as np  # noqa: E402

from pitchcontrol.io import audio_in  # noqa: E402

MACHINE = Path.home() / "Library" / "Application Support" / "PitchControl" / "machine.json"


class ProbeInput(audio_in.AudioInput):
    """AudioInput that also records what the callback sees (the callback runs on PortAudio's thread)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callbacks = 0
        self.last_at: float | None = None
        self.flags: dict[str, int] = {}
        self.window_peak = 0.0
        self.silent_blocks = 0  # in a row, blocks of exact zeros
        self.lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status) -> None:
        with self.lock:
            self.callbacks += 1
            self.last_at = time.monotonic()
            if status:
                self.flags[str(status)] = self.flags.get(str(status), 0) + 1
            peak = float(np.abs(indata).max()) if len(indata) else 0.0
            self.window_peak = max(self.window_peak, peak)
            self.silent_blocks = self.silent_blocks + 1 if peak == 0.0 else 0
        super()._callback(indata, frames, time_info, status)

    def snapshot(self) -> dict:
        s = self.stream
        out = {"stream": s is not None}
        for name in ("active", "stopped"):
            try:
                out[name] = getattr(s, name) if s is not None else None
            except Exception as exc:  # noqa: BLE001
                out[name] = f"raises {type(exc).__name__}: {exc}"
        with self.lock:
            out["callbacks"] = self.callbacks
            out["age_ms"] = None if self.last_at is None else round((time.monotonic() - self.last_at) * 1000)
            out["flags"] = dict(self.flags)
            out["peak"] = round(self.window_peak, 5)
            out["silent_blocks"] = self.silent_blocks
            self.window_peak = 0.0
        return out


def saved_device() -> str | None:
    try:
        return json.loads(MACHINE.read_text(encoding="utf-8"))["audio"]["device"]
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default=None, help="device name (default: the saved one in machine.json)")
    parser.add_argument("--channels", default="1,2")
    parser.add_argument("--out", type=Path, default=None, help="also write the output here")
    args = parser.parse_args()
    device = args.device or saved_device()
    channels = [int(c) for c in args.channels.split(",")]
    t0 = time.monotonic()
    out = args.out.open("w", encoding="utf-8") if args.out else None

    def say(text: str) -> None:
        line = f"{time.monotonic() - t0:7.2f}s  {text}"
        print(line, flush=True)
        if out:
            out.write(line + "\n")
            out.flush()

    say(f"device {device!r}, channels {channels}")
    say("devices: " + ", ".join(d["label"] for d in audio_in.list_input_devices()))
    inp = ProbeInput(device, channels, 48000, lambda s: None)
    inp.start()
    say(f"opened: {inp.status()}")

    enter = threading.Event()

    def watch_enter() -> None:
        while sys.stdin.readline():  # '' = no terminal / closed: stop watching
            enter.set()

    threading.Thread(target=watch_enter, daemon=True).start()
    last_state, last_print = None, 0.0
    try:
        while True:
            time.sleep(0.1)
            if enter.is_set():
                enter.clear()
                say("ENTER: close, re-initialise PortAudio, open again")
                inp.stop()
                audio_in.reinit_portaudio(device)
                say("devices: " + ", ".join(d["label"] for d in audio_in.list_input_devices()))
                inp = ProbeInput(device, channels, 48000, lambda s: None)
                inp.start()
                say(f"reopened: {inp.status()}")
            snap = inp.snapshot()
            # A change worth a line: the stream's own state, new flags, the callbacks stopping or restarting, or the
            # signal becoming digital silence (or not).
            state = (snap["stream"], snap["active"], snap["stopped"], tuple(snap["flags"].items()),
                     snap["age_ms"] is not None and snap["age_ms"] > 300, snap["silent_blocks"] > 3, snap["peak"] > 0)
            now = time.monotonic()
            if state != last_state or now - last_print >= 1.0:
                say(f"callbacks {snap['callbacks']:6d}  age {snap['age_ms']} ms  active {snap['active']}  "
                    f"stopped {snap['stopped']}  peak {snap['peak']}  silent_blocks {snap['silent_blocks']}  "
                    f"flags {snap['flags'] or '-'}")
                last_state, last_print = state, now
    except KeyboardInterrupt:
        say("end")
    finally:
        inp.stop()


if __name__ == "__main__":
    main()
