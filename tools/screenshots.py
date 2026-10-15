"""Retake the nine screenshots of the README and the website, the same way every time.

    backend/.venv/bin/python tools/screenshots.py                 # into screenshots/
    backend/.venv/bin/python tools/screenshots.py --data ~/Documents/PitchControl --out /tmp/shots

Runs the engine and the web UI in this process, without hardware, on a throw-away copy of the data
(nothing of yours is changed), and photographs each page in a headless browser.

The state shown:
- the shipped defaults, plus a copy of ``--data`` if given (for example a showcase rig);
- this computer: one USB DMX interface that isn't plugged in and an Art-Net target, amber ink, UI
  scale 1; two Control Desk overrides and three named scenes, unless the copied data brings its own
  scenes (the fog machines are the rig's);
- the macros at their defaults with Strobo (0.59) and Audio Reactivity (0.3) raised, so the pages
  move (more Audio Reactivity darkens the lights: the peaks map takes over the mask);
- a synthetic 128 BPM techno loop feeding the audio analysis;
- 1512 × 915 (the design size) at device scale 2, so the PNGs are 3024 × 1830; no hovered control.

Settings → About shows the version of this checkout: run it from a clean checkout of the release
commit, so it reads the plain version (the script warns otherwise).

Needs the built frontend (``frontend/dist``) and Playwright (``pip install -e "backend[screenshots]"``).
Playwright uses the installed Chrome or Edge; without one, ``python -m playwright install chromium``.
"""

from __future__ import annotations

import argparse
import logging
import math
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import uvicorn  # noqa: E402

from pitchcontrol.config.loader import write_json  # noqa: E402
from pitchcontrol.io import audio_in  # noqa: E402
from pitchcontrol.server import app as server_app  # noqa: E402
from pitchcontrol.engine.engine import Engine  # noqa: E402
from pitchcontrol.engine.macros import MacroBank  # noqa: E402
from pitchcontrol.paths import open_store, resolve_paths  # noqa: E402
from pitchcontrol.server.app import create_app  # noqa: E402
from pitchcontrol.version import version_label  # noqa: E402

VIEWPORT = {"width": 1512, "height": 915}
RATE = 48000
BPM = 128

# key that opens the page -> file name
PAGES = [
    ("1", "general"),
    ("2", "dimmers"),
    ("3", "fixtures"),
    ("4", "rig"),
    ("5", "inputs"),
    ("6", "outputs"),
    ("7", "fog"),
    ("8", "settings"),
    ("9", "control-desk"),
]


# --------------------------------------------------------------------------- the staged data


def macro_values(**changes: float) -> dict[str, float]:
    """The macro defaults of a scene (General and Dimmers), with some changed."""
    bank = MacroBank()
    values = {n: v for n, v in bank.snapshot().items() if bank.defs[n].page in ("general", "dimmers") and bank.defs[n].kind != "button"}
    return values | changes


# The machine's own audio devices must not end up on the website: the UI is shown with this one.
DEVICES = [
    {
        "index": 0,
        "name": "MacBook Pro Microphone",
        "hostapi": "Core Audio",
        "label": "MacBook Pro Microphone (Core Audio)",
        "channels": 1,
        "default_samplerate": 48000.0,
        "default": True,
    }
]


def stage(data_src: Path | None, data: Path, machine: Path) -> None:
    if data_src is not None:
        shutil.copytree(data_src.expanduser(), data, ignore=shutil.ignore_patterns(".machine", "*.broken-*"))
    data.mkdir(parents=True, exist_ok=True)  # fog machines come with the rig (the shipped one has one)
    scenes = data / "scenes"
    if not list(scenes.glob("scene_*.json")):
        looks = [
            ("Warm-up", macro_values(**{"Audio Reactivity": 0.4, "Strobo": 0.3})),
            ("Peak time", macro_values(**{"Audio Reactivity": 0.9, "Strobo": 0.8, "Mask C": 1.0, "Mask B": 0.0, "Strobo Decay": 0.3})),
            ("Chill-out", macro_values(**{"Mask D": 1.0, "Mask B": 0.0, "Mask Param A": 0.35, "Idle Attack": 0.4})),
        ]
        for i, (name, values) in enumerate(looks):
            write_json(scenes / f"scene_{i + 1}.json", {"name": name, "values": values})
    write_json(
        machine / "machine.json",
        {
            "outputs": {
                "enttec": [
                    {
                        "enabled": True,
                        "universe": 0,
                        "device": {"serial_number": "EN123456", "vid": 0x0403, "pid": 0x6001, "description": "DMX USB PRO"},
                    }
                ],
                "artnet": {"enabled": False, "targets": [{"universe": 1, "ip": "192.168.1.50"}]},
            },
            "ui": {"ink": "amber", "glow": 1.0, "brightness": 1.0, "key_hints": True, "scale": 1.0},
        },
    )
    write_json(machine / "state" / "overrides.json", {"universes": {"0": {"9": 180, "10": 255}}})
    write_json(machine / "state" / "macros.json", {"name": "screenshots", "values": macro_values(**{"Strobo": 0.59, "Audio Reactivity": 0.3})})


# --------------------------------------------------------------------------- the music


def techno_bar(rate: int = RATE, bpm: int = BPM) -> np.ndarray:
    """One bar of four-on-the-floor: kick, off-beat bass, clap on 2 and 4, hi-hats on the eighths."""
    beat = int(rate * 60 / bpm)
    bar = np.zeros(beat * 4, dtype=np.float32)
    rng = np.random.default_rng(7)

    def add(at: int, sound: np.ndarray) -> None:
        end = min(len(bar), at + len(sound))
        bar[at:end] += sound[: end - at]

    t = np.arange(int(rate * 0.35)) / rate
    kick = np.sin(2 * np.pi * (45 * t + (120 - 45) * (1 - np.exp(-t * 30)) / 30)) * np.exp(-t * 9)
    tb = np.arange(int(rate * 0.18)) / rate
    bass = np.sign(np.sin(2 * np.pi * 55 * tb)) * 0.25 * np.exp(-tb * 12)
    tc = np.arange(int(rate * 0.12)) / rate
    clap = rng.normal(0, 1, len(tc)) * 0.35 * np.exp(-tc * 30)
    th = np.arange(int(rate * 0.04)) / rate
    hat = np.diff(rng.normal(0, 1, len(th) + 1)) * 0.12 * np.exp(-th * 90)
    for b in range(4):
        add(b * beat, kick)
        add(b * beat + beat // 2, bass)
        add(b * beat + beat // 2, hat)
        add(b * beat, hat * 0.5)
        if b % 2:
            add(b * beat, clap)
    # peaks at 0.05 (about -26 dBFS, a line feed after the input gain): louder saturates the band meter
    return (bar / np.max(np.abs(bar)) * 0.05).astype(np.float32)


def feed(engine: Engine, stop: threading.Event, block: int = 480) -> None:
    """Push the loop into the analysis in real time, as an audio input would."""
    bar = techno_bar()
    pos, start, sent = 0, time.perf_counter(), 0
    while not stop.is_set():
        chunk = np.take(bar, range(pos, pos + block), mode="wrap")
        pos = (pos + block) % len(bar)
        with engine.lock:
            engine.analyzer.push(chunk)
        sent += block
        delay = start + sent / RATE - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


# --------------------------------------------------------------------------- the browser


def launch(playwright, channel: str | None):
    tries = [channel] if channel else ["chrome", "msedge", None]
    error = None
    for ch in tries:
        try:
            return playwright.chromium.launch(channel=ch) if ch else playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - try the next browser
            error = exc
    sys.exit(f"no browser could be started ({error}).\nInstall one with: python -m playwright install chromium")


NEUTRAL = """() => {
  document.activeElement && document.activeElement.blur && document.activeElement.blur();
  document.documentElement.dispatchEvent(new PointerEvent('pointerleave'));
}"""


# The throw-away folders have ugly temp names; show what a user would see instead.
SHOWN_DATA = "~/Documents/PitchControl"
SHOWN_MACHINE = "~/Library/Application Support/PitchControl"

DISGUISE = """([real, shown]) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    real.forEach((from, i) => {
      if (n.nodeValue.includes(from)) n.nodeValue = n.nodeValue.replace(from, shown[i]);
    });
  }
}"""


def shoot(url: str, out: Path, settle: float, channel: str | None, folders: tuple[list[str], list[str]]) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = launch(p, channel)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.goto(f"{url}/#General")
        page.wait_for_selector("text=PitchControl!")
        page.evaluate("document.fonts.ready")
        for key, name in PAGES:
            page.keyboard.press(key)
            page.wait_for_timeout(500)
            if name == "outputs":
                page.get_by_text("show channel values").first.click()  # the DMX numbers, as in the docs
            page.evaluate(NEUTRAL)
            page.wait_for_timeout(settle * 1000)
            page.evaluate(DISGUISE, list(folders))
            page.screenshot(path=str(out / f"{name}.png"))
            print("  ", out / f"{name}.png")
        browser.close()


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=None, help="a data folder to show (copied, never changed), e.g. a showcase rig")
    parser.add_argument("--out", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--port", type=int, default=8460)
    parser.add_argument("--settle", type=float, default=6.0, help="seconds each page runs before the photo")
    parser.add_argument("--browser", default=None, help="chrome, msedge or chromium (default: the first that starts)")
    args = parser.parse_args()

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        sys.exit("frontend/dist is missing: run `npm run build` in frontend/ first")
    label = version_label()
    if label.endswith(")"):  # "1.4.0+3 (abc1234)", "1.4.0-dev (…)", "…, modified)"
        print(f"warning: this checkout reports '{label}', not a plain release version; Settings > About will show it")

    logging.basicConfig(level=logging.WARNING)
    with tempfile.TemporaryDirectory(prefix="pitchcontrol-shots-") as tmp:
        data, machine = Path(tmp) / "data", Path(tmp) / "machine"
        stage(args.data, data, machine)
        for module in (audio_in, server_app):
            for name in ("list_input_devices", "list_input_devices_fresh"):
                if hasattr(module, name):
                    setattr(module, name, lambda: [dict(d) for d in DEVICES])
        store = open_store(resolve_paths(ROOT / "config", data=data, machine=machine))
        store.notices.clear()  # nothing to report about a staged folder
        engine = Engine(store, enable_hardware=False)
        engine.start()
        stop = threading.Event()
        feeder = threading.Thread(target=feed, args=(engine, stop), name="audio", daemon=True)
        feeder.start()
        app = create_app(engine, static_dir=ROOT / "frontend" / "dist")
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
        threading.Thread(target=server.run, name="server", daemon=True).start()
        url = f"http://127.0.0.1:{args.port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/api/state", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            sys.exit(f"the server did not start on {url}")
        print(f"PitchControl {label} at {url}, screenshots into {args.out}")
        try:
            shoot(url, args.out, args.settle, args.browser, ([str(data), str(machine)], [SHOWN_DATA, SHOWN_MACHINE]))
        finally:
            stop.set()
            server.should_exit = True
            engine.stop()
            time.sleep(0.5)


if __name__ == "__main__":
    main()
