"""Entry point: ``pitchcontrol`` or ``python -m pitchcontrol``.

Runs from the source tree: the repo's ``config/`` is the read-only defaults, the user data goes to the
gitignored ``data/`` (``--data`` chooses another folder), see ``paths.py``.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from .config.models import DEFAULT_PORT
from .engine.engine import Engine
from .logsetup import setup_logging
from .paths import open_store, resolve_paths
from .server.app import create_app
from .version import version_label

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # the repo root


def main() -> None:
    parser = argparse.ArgumentParser(description="PitchControl light engine + web UI")
    parser.add_argument("--data", "--config", dest="data", type=Path, default=None, help="folder with your rigs, scenes and settings (default: the repo's data/)")
    parser.add_argument("--machine", type=Path, default=None, help="folder for this computer's settings, autosave and logs (default: .machine/ in the data folder)")
    parser.add_argument("--logs", type=Path, default=None, help="log folder (default: logs/ in the machine folder)")
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)  # replaced by Settings → Network
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-hardware", action="store_true", help="run without audio, MIDI and outputs")
    args = parser.parse_args()

    paths = resolve_paths(PROJECT_ROOT / "config", data=args.data, machine=args.machine, source_repo=PROJECT_ROOT)
    setup_logging(args.logs or paths.logs)
    log = logging.getLogger("pitchcontrol")
    log.info("PitchControl %s starting", version_label())
    log.info("defaults %s, data folder %s (%s), this computer %s", paths.defaults, paths.user, paths.reason, paths.machine)

    store = open_store(paths)
    engine = Engine(store, enable_hardware=not args.no_hardware)
    engine.start()

    app = create_app(engine, static_dir=PROJECT_ROOT / "frontend" / "dist", folders={"data_dir": str(paths.user), "logs_dir": str(args.logs or paths.logs)})
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("--host %s is ignored: other devices are allowed in Settings → Network (the switch, a fixed port, an optional PIN)", args.host)
    app.state.network.start()  # other devices on the network, when the switch is on
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        app.state.network.stop()
        engine.stop()
        log.info("PitchControl stopped")


if __name__ == "__main__":
    main()
