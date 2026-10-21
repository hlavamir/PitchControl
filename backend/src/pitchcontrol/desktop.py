"""Standalone desktop app: engine + server in the background, UI in a native window.

Folders (see ``paths.py``): the shipped defaults are read-only inside the app, the user's data is
``~/Documents/PitchControl`` (or ``--data`` / ``data_folder.txt``), and this computer's files
(``machine.json``, the macro autosave, the logs) are in the OS app-data folder.

Closing the window stops the engine; it asks first when an output is live or a page has unsaved edits
(``quitguard.py``).
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

from .config.models import DEFAULT_PORT
from .engine.engine import Engine
from .logsetup import setup_logging
from .menu import MenuActions, native_menu, patch_cocoa
from .paths import APP_NAME, open_store, resolve_paths
from .quitguard import confirm_quit, quit_reasons, with_live_edits
from .server.app import create_app
from .version import version_label

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
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
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)  # replaced by Settings → Network
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

    if args.host not in LOCAL_HOSTS:
        log.warning("--host %s is ignored: other devices are allowed in Settings → Network (the switch, a fixed port, an optional PIN)", args.host)
    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    menu = MenuActions(str(paths.user), str(paths.logs))  # the menu bar's actions (menu.py); the window comes later
    desktop_hooks: dict = {"url": url, "data_dir": str(paths.user), "logs_dir": str(paths.logs), "menu": menu}
    app = create_app(engine, static_dir=bundled_frontend(res), desktop=desktop_hooks)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, name="server", daemon=True)
    server_thread.start()

    stopped = threading.Event()

    def shutdown() -> None:
        if stopped.is_set():
            return
        stopped.set()
        app.state.network.stop()
        server.should_exit = True
        server_thread.join(timeout=5)
        engine.stop()
        log.info("%s stopped", APP_NAME)

    atexit.register(shutdown)
    app.state.network.start()  # other devices on the network, when the switch is on (stopped with the app)

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

    # open maximized: fits any screen (the UI is laid out for a 14" MacBook and up). On Windows the UI draws the menu
    # bar in its header (menu.py), only in this window: ?window=app (a browser, here or on the network, has no menu)
    mac = sys.platform == "darwin"
    window = webview.create_window(
        APP_NAME, url if mac else f"{url}/?window=app", width=1440, height=900, min_size=(1000, 700), background_color="#0e0f12", maximized=True
    )
    menu.window = window
    menu.zoomed = True  # opened maximized

    def on_maximized() -> None:
        menu.zoomed = True

    def on_restored() -> None:
        menu.zoomed = False

    window.events.maximized += on_maximized
    window.events.restored += on_restored
    def on_closing() -> bool | None:
        # Cmd+Q on macOS and the window's close button both end up here; returning False keeps the window and the engine
        try:
            reasons = quit_reasons(with_live_edits(engine.ui_unsaved.pages(), app.state.unsaved_live()), engine.outputs.status())
        except Exception:  # noqa: BLE001
            log.exception("checking whether to ask before quitting failed: asking")
            reasons = ["PitchControl couldn't check whether the lights are live or a page has unsaved edits."]
        if reasons and not confirm_quit(reasons):
            log.info("quit cancelled (%s)", "; ".join(reasons))
            return False
        # on macOS, Quit (Cmd+Q) ends the process after "closing" without returning from webview.start(),
        # so the engine is stopped here
        shutdown()
        return None

    window.events.closing += on_closing
    window.events.closed += shutdown

    from .fullscreen import Fullscreen

    fullscreen = Fullscreen(window)
    desktop_hooks["fullscreen"] = fullscreen

    def on_shown() -> None:
        fullscreen.setup()
        if store.settings.ui.start_fullscreen:
            fullscreen.set(True)

    window.events.shown += on_shown
    if mac:
        patch_cocoa(menu)  # the native menu bar in the usual order, with its keys
        webview.start(menu=native_menu(menu))  # blocks until the window is closed
    else:
        webview.start()  # blocks until the window is closed
    shutdown()


if __name__ == "__main__":
    main()
