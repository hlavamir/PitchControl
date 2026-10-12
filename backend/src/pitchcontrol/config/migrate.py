"""One-time move of a data folder from the 1.3 layout to the 1.4 one.

Up to 1.3 the data folder held ``config/`` (settings, rigs, fixture types, controllers, scenes and
``state/``) and ``logs/``, and every default was copied into it on first start. From 1.4 the user
folder holds only what the user made or changed, flat, and this computer's files live elsewhere:

- ``config/state/`` and ``logs/`` move to this computer's folder;
- ``config/settings.json`` moves up; the loader then splits off the per-computer part into
  ``machine.json`` and keeps only what differs from the defaults (see ``ConfigStore.load_settings``);
- every other file moves up, unless it is an untouched copy of a file the app has shipped (any
  version, see ``shipped_history``): those are dropped, so the user gets the current default. A shipped
  fixture type that a kept rig still uses is kept, though, when no default of that name exists any
  more (types were renamed between versions).
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .loader import content_hash
from .shipped_history import SHIPPED

log = logging.getLogger(__name__)

JUNK = {".DS_Store", "Thumbs.db", "desktop.ini"}


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_shipped(rel: str, data, defaults: Path | None) -> bool:
    if data is None:
        return False
    h = content_hash(data)
    if h in SHIPPED.get(rel, ()):
        return True
    current = defaults / rel if defaults is not None else None
    return bool(current and current.is_file() and (cur := _read(current)) is not None and content_hash(cur) == h)


def _move(src: Path, dst: Path) -> Path:
    """Move ``src`` to ``dst``; an existing different file at ``dst`` is kept and ``src`` gets a new name."""
    if dst.exists():
        if _read(dst) is not None and _read(src) is not None and content_hash(_read(dst)) == content_hash(_read(src)):
            src.unlink()
            return dst
        n = 2
        while (alt := dst.with_name(f"{dst.stem} (from 1.3{'' if n == 2 else f' {n}'}){dst.suffix}")).exists():
            n += 1
        dst = alt
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst


def _prune(folder: Path) -> None:
    """Remove empty folders (and OS junk files) bottom-up, ``folder`` included."""
    if not folder.is_dir():
        return
    for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_file() and path.name in JUNK:
            path.unlink(missing_ok=True)
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for junk in JUNK:
        (folder / junk).unlink(missing_ok=True)
    if not any(folder.iterdir()):
        folder.rmdir()


def migrate_old_layout(user: Path, machine: Path, defaults: Path | None) -> list[str]:
    """Move a 1.3 data folder into the 1.4 layout. Returns notices for the user (empty: nothing to do)."""
    old, old_logs = user / "config", user / "logs"
    if not old.is_dir() and not old_logs.is_dir():
        return []
    log.info("data folder %s has the 1.3 layout: migrating", user)
    moved = dropped = 0
    files = sorted(p for p in old.rglob("*") if p.is_file() and p.name not in JUNK) if old.is_dir() else []

    # this computer's files
    for path in files:
        rel = path.relative_to(old)
        if rel.parts[0] == "state":
            _move(path, machine / rel)
    if old_logs.is_dir():
        for path in sorted(p for p in old_logs.rglob("*") if p.is_file() and p.name not in JUNK):
            _move(path, machine / "logs" / path.relative_to(old_logs))

    # the user's files: first decide which are untouched defaults
    rest = [(p, p.relative_to(old).as_posix()) for p in files if p.exists() and p.relative_to(old).parts[0] != "state"]
    keep = {rel: not _is_shipped(rel, _read(p), defaults) for p, rel in rest if rel != "settings.json"}
    used_types: set[str] = set()
    for p, rel in rest:
        if rel.startswith("rigs/") and keep.get(rel):
            data = _read(p)
            for fx in (data or {}).get("fixtures", []) if isinstance(data, dict) else []:
                if isinstance(fx, dict) and isinstance(fx.get("type"), str):
                    used_types.add(fx["type"].lower())
    default_types = {p.stem.lower() for p in (defaults / "fixtures" / "types").glob("*.json")} if defaults else set()
    for p, rel in rest:
        if rel.startswith("fixtures/types/") and not keep[rel]:
            name = Path(rel).stem.lower()
            keep[rel] = name in used_types and name not in default_types  # a rig needs it, no default replaces it

    for p, rel in rest:
        if rel == "settings.json" or keep[rel]:
            _move(p, user / rel)
            moved += 1
        else:
            p.unlink()
            dropped += 1
            log.info("migration: %s is an unchanged default, dropped", rel)

    _prune(old)
    _prune(old_logs)
    left = old.exists() or old_logs.exists()
    log.info("migration done: %d files moved, %d unchanged defaults dropped%s", moved, dropped, ", some files left behind" if left else "")
    text = (
        f"Your PitchControl folder was updated for this version: {moved} of your files were kept, "
        f"{dropped} unchanged copies of the defaults were removed (the app's current defaults apply), and the macro "
        f"autosave and the logs now live in {machine}."
    )
    if left:
        text += f" Some files could not be sorted and were left in {old if old.exists() else old_logs}."
    return [text]
