"""Where PitchControl keeps its files.

- **Defaults** — shipped with the app, read-only: the bundled ``default_config`` (app) or the repo's
  ``config/`` (source).
- **User data** — what the user made or changed (rigs, fixture types, scenes, controllers,
  ``settings.json``), first match wins:

  1. ``--data <folder>``
  2. a folder written in ``~/Documents/PitchControl/data_folder.txt``
  3. a source run: the repo's ``data/`` (gitignored)
  4. ``~/Documents/PitchControl``

- **This computer** — ``machine.json``, ``state/`` and ``logs/``: the OS app-data folder
  (``~/Library/Application Support/PitchControl``, ``%LOCALAPPDATA%\\PitchControl``,
  ``~/.local/share/PitchControl``). With ``--data`` or in a source run it is ``.machine/`` inside the
  data folder, so a test or portable setup is self-contained; ``--machine`` chooses it explicitly.

The app never writes into its own folder: a data folder that is, or contains, the defaults is refused.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config.loader import ConfigStore
from .config.migrate import migrate_old_layout

APP_NAME = "PitchControl"
log = logging.getLogger(__name__)


def documents_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


def app_data_dir() -> Path:
    """The per-computer folder the OS provides for an app's own files (not synced, not in Documents)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / APP_NAME
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / APP_NAME


@dataclass
class DataPaths:
    defaults: Path | None  # read-only, shipped
    user: Path  # the user's data
    machine: Path  # this computer: machine.json, state/, logs/
    reason: str  # how the user folder was chosen (for the log)
    notices: list[str] = field(default_factory=list)

    @property
    def logs(self) -> Path:
        return self.machine / "logs"


def _contains(outer: Path, inner: Path) -> bool:
    try:
        inner.resolve().relative_to(outer.resolve())
        return True
    except (OSError, ValueError):
        return False


def resolve_paths(
    defaults: Path | None,
    data: Path | None = None,
    machine: Path | None = None,
    source_repo: Path | None = None,
) -> DataPaths:
    """``source_repo``: the repo root when running from source (its ``data/`` is the default)."""
    notices: list[str] = []
    pointer = documents_dir() / "data_folder.txt"
    if data is not None:
        user, own_machine, reason = data.expanduser(), True, "--data"
    elif pointer.is_file() and (target := pointer.read_text(encoding="utf-8").strip()):
        user, own_machine, reason = Path(target).expanduser(), False, f"from {pointer}"
    elif source_repo is not None:
        user, own_machine, reason = source_repo / "data", True, "source run"
    else:
        user, own_machine, reason = documents_dir(), False, "Documents"
    if defaults is not None and (_contains(user, defaults) or _contains(defaults, user)):
        notices.append(
            f"The data folder {user} would be the app's own default configuration, which is never changed; "
            f"{documents_dir()} is used instead."
        )
        log.error("data folder %s contains the defaults %s (or lies inside them): refused", user, defaults)
        user, own_machine, reason = documents_dir(), False, "Documents (fallback)"
    if machine is None:
        machine = user / ".machine" if own_machine else app_data_dir()
    return DataPaths(defaults=defaults, user=user, machine=machine, reason=reason, notices=notices)


def writable(folder: Path) -> bool:
    """Whether files can be created in ``folder`` (created if missing)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / f".write-test-{uuid.uuid4().hex}"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def open_store(paths: DataPaths) -> ConfigStore:
    """Prepare the folders (migrating a 1.3 data folder), then load the configuration."""
    store = ConfigStore(paths.user, defaults=paths.defaults, machine=paths.machine)
    for text in paths.notices:
        store.notice(text)
    if not writable(paths.machine):
        store.notice(f"{paths.machine} can't be written: the macro autosave and the logs are not kept.")
    if writable(paths.user):
        for text in migrate_old_layout(paths.user, paths.machine, paths.defaults):
            store.notice(text)
    else:
        store.notice(f"The data folder {paths.user} can't be written: changes to rigs, scenes and settings can't be saved.")
    store.load_all()
    return store
