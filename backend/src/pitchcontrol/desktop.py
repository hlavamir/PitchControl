"""Standalone desktop app: engine + server in the background, UI in a native window.

Folders (see ``paths.py``): the shipped defaults are read-only inside the app, the user's data is
``~/Documents/PitchControl`` (or ``--data`` / ``data_folder.txt``), and this computer's files
(``machine.json``, the macro autosave, the logs) are in the OS app-data folder.

Closing the window stops the engine.
"""

from __future__ import annotations

import argparse
import atexit
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from .engine.engine import Engine
from .logsetup import setup_logging
from .paths import APP_NAME, open_store, resolve_paths
from .server.app import create_app
from .version import version_label

DEFAULT_PORT = 8420
log = logging.getLogger("pitchcontrol.desktop")


def resource_dir() -> Path:
    """Folder with the bundled ``default_config`` and ``frontend_dist`` (PyInstaller or source tree)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]  # the repo root


def bundled_config(res: Path) -> Path:
    return res / "default_config" if (res / "default_config").exists() else res / "config"


def bundled_frontend(res: Path) -> Path:
    return res / "frontend_dist" if (res / "frontend_dist").exists() else res / "frontend" / "dist"


def free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(url: str, timeout: float = 20.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            urllib.request.urlopen(f"{url}/api/state", timeout=1).read()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    # a windowed app (no console) has no stdout/stderr; uvicorn's logging needs them
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    parser = argparse.ArgumentParser(description="PitchControl desktop app")
    parser.add_argument("--data", type=Path, default=None, help="folder with your rigs, scenes and settings (default: Documents/PitchControl)")
    parser.add_argument("--machine", type=Path, default=None, help="folder for this computer's settings, autosave and logs")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to allow a phone on the LAN")
    parser.add_argument("--no-hardware", action="store_true", help="run without audio, MIDI and outputs")
    parser.add_argument("--no-window", action="store_true", help="no window: serve the UI and open the browser")
    parser.add_argument("--smoke-test", action="store_true", help="start, check the API, quit (for builds)")
    args, _ = parser.parse_known_args()  # macOS may add -psn_… arguments

    res = resource_dir()
    paths = resolve_paths(
        bundled_config(res),
        data=args.data,
        machine=args.machine,
        source_repo=None if getattr(sys, "frozen", False) else res,
    )
    setup_logging(paths.logs)
    log.info("%s %s starting", APP_NAME, version_label())
    log.info("defaults %s, data folder %s (%s), this computer %s", paths.defaults, paths.user, paths.reason, paths.machine)

    store = open_store(paths)
    engine = Engine(store, enable_hardware=not args.no_hardware)
    engine.start()

    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    desktop_hooks: dict = {"url": url, "data_dir": str(paths.user), "logs_dir": str(paths.logs)}
    app = create_app(engine, static_dir=bundled_frontend(res), desktop=desktop_hooks)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, name="server", daemon=True)
    server_thread.start()

    stopped = threading.Event()

    def shutdown() -> None:
        if stopped.is_set():
            return
        stopped.set()
        server.should_exit = True
        server_thread.join(timeout=5)
        engine.stop()
        log.info("%s stopped", APP_NAME)

    atexit.register(shutdown)

    if not wait_until_up(url):
        log.error("server did not start on %s", url)
        shutdown()
        sys.exit(1)
    log.info("UI at %s", url)

    if args.smoke_test:
        ok = b"fixtures" in urllib.request.urlopen(f"{url}/api/state", timeout=2).read()
        ok = ok and b"<div id=\"root\">" in urllib.request.urlopen(url, timeout=2).read()
        print("SMOKE TEST", "OK" if ok else "FAILED", url)
        shutdown()
        sys.exit(0 if ok else 1)

    if args.no_window:
        webbrowser.open(url)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        shutdown()
        return

    import webview  # imported late: only the window needs it

    # open maximized: fits any screen (the UI is laid out for a 14" MacBook and up)
    window = webview.create_window(
        APP_NAME, url, width=1440, height=900, min_size=(1000, 700), background_color="#0e0f12", maximized=True
    )
    # on macOS, Quit (Cmd+Q) fires "closing" and then ends the process without returning
    # from webview.start(); pywebview waits for "closing" handlers, so stop the engine there
    window.events.closing += shutdown
    window.events.closed += shutdown

    from .fullscreen import Fullscreen

    fullscreen = Fullscreen(window)
    desktop_hooks["fullscreen"] = fullscreen

    def on_shown() -> None:
        fullscreen.setup()
        if store.settings.ui.start_fullscreen:
            fullscreen.set(True)

    window.events.shown += on_shown
    webview.start()  # blocks until the window is closed
    shutdown()


if __name__ == "__main__":
    main()
