"""Loading and saving of the configuration, in two layers plus this computer's files.

- **Defaults** (read-only, shipped with the app: the repo's ``config/``)
- **User data** (``~/Documents/PitchControl``): only what the user made or changed; every write goes
  here. A user file wins over a default of the same name (ignoring case); lists are the union.
- **This computer** (the OS app-data folder): ``machine.json`` and ``state/``.

Layout of the defaults and the user folder::

    settings.json             the show's settings (the user's file holds only what differs)
    fixtures/types/*.json     one file per fixture model
    rigs/<name>.json          fixture instances for one event / venue
    controllers/<name>.json   MIDI controller mappings
    scenes/scene_<n>.json     saved macro snapshots (an empty slot = the macro defaults)

and of this computer's folder::

    machine.json              per-computer settings (audio input, MIDI port, outputs, UI, the network switch)
    last_version              the app version of the last start (for upgrade notices)
    state/macros.json         auto-saved macro values (crash recovery)
    state/overrides.json      Control Desk overrides

Missing keys are filled with defaults. Unknown keys (usually typos) are reported to the log and never
stop the engine. A broken file in the user folder is renamed (``*.json.broken-<time>``, never
overwritten) and the default of the same name takes its place. Every saved file records the
``app_version`` that wrote it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from .. import __version__
from .layers import diff, has_machine_keys, merge, split_machine
from .models import Controller, FixtureType, FogMachine, Rig, Scene, Settings

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)
Origin = Literal["default", "user", "modified"]

VERSION_KEY = "app_version"
# 1.5.0 replaced the shipped LCXL3 layout (see ConfigStore.upgrade_notice)
NEW_LCXL3_VERSION = (1, 5, 0)
TYPES, RIGS, CONTROLLERS, SCENES, OSC = "fixtures/types", "rigs", "controllers", "scenes", "osc"
DEFAULT_RIG = "Default"

# rig names are file names: keep them portable (macOS / Windows) and free of path separators
RIG_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}")


# --------------------------------------------------------------------------- files


def write_json(path: Path, data: dict) -> None:
    """Write atomically (temporary file, then rename), with the app version as the first key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = {VERSION_KEY: __version__, **{k: v for k, v in data.items() if k != VERSION_KEY}}
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def canonical(data: Any) -> str:
    """The content of a JSON file independent of whitespace, key order and the app version."""
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != VERSION_KEY}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(data: Any) -> str:
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()[:16]


def quarantine(path: Path) -> Path | None:
    """Rename a broken file out of the way (kept for the user to repair, never overwritten)."""
    target = path.with_name(f"{path.name}.broken-{datetime.now():%y%m%d-%H%M%S}")
    try:
        path.replace(target)
    except OSError as exc:
        log.error("%s: cannot rename the broken file: %s", path, exc)
        return None
    return target


def report_unknown_keys(model: BaseModel, source: str, path: str = "") -> list[str]:
    """Log (and return) every key that the model did not recognise, recursively."""
    found: list[str] = []
    for key in (model.model_extra or {}):
        if key.startswith("_") or (not path and key == VERSION_KEY):  # "_note" etc. are annotations
            continue
        found.append(f"{path}{key}")
    for name in type(model).model_fields:
        value = getattr(model, name)
        children = value if isinstance(value, list) else [value]
        for i, child in enumerate(children):
            if isinstance(child, BaseModel):
                sub = f"{path}{name}[{i}]." if isinstance(value, list) else f"{path}{name}."
                found += report_unknown_keys(child, source, sub)
    if not path:
        for key in found:
            log.warning("%s: unknown key '%s' ignored (typo?)", source, key)
    return found


def load_model(
    path: Path,
    model: type[M],
    *,
    broken: Callable[[Path, str], None] | None = None,
    **defaults,
) -> M | None:
    """Read and validate one file. A missing file gives the defaults; a broken one ``None``, and with
    ``broken`` (user files) it is renamed out of the way and reported there."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("%s: not found, using defaults", path)
        return model(**defaults)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.error("%s: invalid JSON (%s)", path, exc)
        if broken:
            broken(path, "invalid JSON")
        return None
    except OSError as exc:
        log.error("%s: cannot be read (%s)", path, exc)
        return None
    if isinstance(data, dict):
        data.pop(VERSION_KEY, None)  # the version that wrote the file (for future format upgrades)
        for key, value in defaults.items():
            data.setdefault(key, value)
    try:
        obj = model.model_validate(data)
    except ValidationError as exc:
        log.error("%s: invalid content:\n%s", path, exc)
        if broken:
            broken(path, "invalid content")
        return None
    report_unknown_keys(obj, str(path))
    return obj


def save_model(path: Path, obj: BaseModel) -> None:
    write_json(path, obj.model_dump(mode="json", exclude_none=True))


def _normalised(path: Path, model: type[BaseModel]) -> dict | None:
    """A file's content as the model sees it (defaults filled in), without its name, version and edit time."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.pop(VERSION_KEY, None)
            data.pop("name", None)
            data.pop("modified", None)
        out = model.model_validate(data).model_dump(mode="json", exclude_none=True)
    except (OSError, ValueError, ValidationError):
        return None
    out.pop("name", None)
    out.pop("modified", None)  # a save that changes nothing else is not a modification
    return out


def _version_tuple(text: str | None) -> tuple[int, int, int] | None:
    """``1.5.0`` (or ``v1.5.0``, ``1.5.0-dev``) as a tuple; None if it isn't a version."""
    m = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", text or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _had_page_knob(path: Path | None) -> bool:
    """Does a controller file still have the page knob of 1.4 (the ``page_knob`` key or a mapping with that mode)?"""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else None
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    mappings = list(data.get("mappings") or [])
    if isinstance(data.get("pages"), dict):
        for items in data["pages"].values():
            mappings += items or []
    return "page_knob" in data or any(isinstance(m, dict) and m.get("mode") == "page_knob" for m in mappings)


# --------------------------------------------------------------------------- the store


@dataclass
class ConfigStore:
    root: Path  # the user's data folder: every write goes here
    defaults: Path | None = None  # shipped with the app, read-only
    machine: Path | None = None  # this computer: machine.json and state/ (None: the data folder itself)
    settings: Settings = field(default_factory=Settings)
    fixture_types: dict[str, FixtureType] = field(default_factory=dict)
    rig: Rig = field(default_factory=Rig)
    controller: Controller | None = None
    # problems the user should see in the UI (broken files, missing items, an unwritable folder)
    notices: list[str] = field(default_factory=list)
    legacy_mask_curve: float | None = field(default=None, repr=False)  # an old rig file's mask curve, until the engine has taken it (item 76)
    _legacy_fog: list | None = field(default=None, repr=False)  # see move_fog_into_rigs

    def notice(self, text: str) -> None:
        if text not in self.notices:
            self.notices.append(text)

    def broken_file(self, path: Path, why: str) -> None:
        moved = quarantine(path)
        kept = f" and was set aside as {moved.name}" if moved else ""
        self.notice(
            f"{path.name} in {path.parent} could not be read ({why}){kept}. "
            "Where the app has its own version of it, that one is used now."
        )

    # -- paths
    @property
    def machine_root(self) -> Path:
        return self.machine or self.root

    @property
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    @property
    def machine_path(self) -> Path:
        return self.machine_root / "machine.json"

    @property
    def types_dir(self) -> Path:
        return self.root / TYPES

    @property
    def rigs_dir(self) -> Path:
        return self.root / RIGS

    @property
    def controllers_dir(self) -> Path:
        return self.root / CONTROLLERS

    @property
    def osc_dir(self) -> Path:
        return self.root / OSC

    @property
    def scenes_dir(self) -> Path:
        return self.root / SCENES

    @property
    def state_dir(self) -> Path:
        return self.machine_root / "state"

    # -- layers
    def _layer(self, rel: str) -> dict[str, tuple[str, Path | None, Path | None]]:
        """lower-case name -> (name, default file, user file); the user's spelling wins."""
        out: dict[str, tuple[str, Path | None, Path | None]] = {}
        for base, is_user in ((self.defaults, False), (self.root, True)):
            if base is None:
                continue
            for p in sorted((base / rel).glob("*.json")):
                key = p.stem.lower()
                name, d, u = out.get(key, (p.stem, None, None))
                if (u if is_user else d) is not None:
                    log.error("%s: another file has the same name ignoring case, skipped", p)
                    continue
                out[key] = (p.stem, d, p) if is_user else (name, p, u)
        return out

    def names(self, rel: str) -> list[str]:
        return sorted((name for name, _, _ in self._layer(rel).values()), key=str.lower)

    def default_file(self, rel: str, name: str) -> Path | None:
        return self._layer(rel).get(name.lower(), (name, None, None))[1]

    def user_file(self, rel: str, name: str) -> Path | None:
        return self._layer(rel).get(name.lower(), (name, None, None))[2]

    def find(self, rel: str, name: str) -> Path | None:
        """The file that counts for ``name``: the user's, else the shipped one."""
        _, d, u = self._layer(rel).get(name.lower(), (name, None, None))
        return u or d

    def write_path(self, rel: str, name: str) -> Path:
        """Where saving ``name`` writes: the user's existing file (any case), else a new one."""
        return self.user_file(rel, name) or self.root / rel / f"{name}.json"

    def origin(self, rel: str, name: str, model: type[BaseModel]) -> Origin:
        """``default``: shipped and not changed (a user copy with the same content counts as unchanged);
        ``user``: the user's own; ``modified``: a shipped item the user changed."""
        _, d, u = self._layer(rel).get(name.lower(), (name, None, None))
        if u is None:
            return "default"
        if d is None:
            return "user"
        same = _normalised(u, model)
        return "default" if same is not None and same == _normalised(d, model) else "modified"

    def origins(self, rel: str, model: type[BaseModel]) -> dict[str, Origin]:
        return {name: self.origin(rel, name, model) for name in self.names(rel)}

    def _load_layered(self, rel: str, item: str, model: type[M], **defaults) -> M | None:
        """The user's file (a broken one is set aside), else the shipped one, else None."""
        _, d, u = self._layer(rel).get(item.lower(), (item, None, None))
        if u is not None:
            obj = load_model(u, model, broken=self.broken_file, **defaults)
            if obj is not None:
                return obj
        if d is not None:
            return load_model(d, model, **defaults)
        return None

    # -- loading
    def load_all(self) -> None:
        fresh = self._is_fresh_install()  # before anything is written
        self.load_settings()
        self.load_fixture_types()
        self.move_fog_into_rigs()
        self.load_rig(self.settings.active_rig)
        self.load_controller(self.settings.active_controller)
        self.upgrade_notice(fresh)
        try:  # the place for the user's own OSC files, next to rigs and controllers
            self.osc_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    @property
    def last_version_path(self) -> Path:
        return self.machine_root / "last_version"

    def _is_fresh_install(self) -> bool:
        """Nothing of the user's yet: an empty data folder (hidden entries, such as a portable ``.machine``,
        don't count) and no ``machine.json`` or ``state/`` of an earlier run."""
        try:
            if any(not p.name.startswith(".") for p in self.root.iterdir()):
                return False
        except OSError:  # no folder yet
            pass
        return not (self.machine_path.exists() or self.state_dir.exists())

    def upgrade_notice(self, fresh: bool) -> None:
        """Once, when the app has been updated to 1.5.0 or later: users of the shipped Launch Control XL 3
        mapping (no copy of their own, so nothing else tells them) get the new layout explained. The version
        of the last start is kept per computer in ``last_version``."""
        current = _version_tuple(__version__)
        if current is None:
            return
        try:
            text = self.last_version_path.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        recorded = _version_tuple(text)
        name = self.settings.active_controller or ""
        shipped_lcxl3 = (
            name.lower() == "lcxl3" and self.user_file(CONTROLLERS, name) is None and self.default_file(CONTROLLERS, name) is not None
        )
        if (recorded is None or recorded < NEW_LCXL3_VERSION) and current >= NEW_LCXL3_VERSION and not fresh and shipped_lcxl3:
            self.notice(
                "The shipped Launch Control XL 3 mapping has a new layout. The knob that switched the control pages is gone "
                "(use the Page General / Page Dimmers macros or switch on screen); the top knob row is unused and the middle "
                "knob row is Dimmer 01-08. The buttons now act: the bottom button row saves scenes 1-7 (with shift it loads "
                "them) and the Fog button fogs. See the MIDI mapping in Connections → MIDI."
            )
        if text != __version__:
            try:
                self.last_version_path.parent.mkdir(parents=True, exist_ok=True)
                self.last_version_path.write_text(__version__ + "\n", encoding="utf-8")
            except OSError as exc:
                log.warning("cannot record the app version: %s", exc)

    def move_fog_into_rigs(self) -> None:
        """Up to 1.4 the fog machines were in settings.json; now each rig has its own. Once: every rig
        of the user's without fog machines gets the old ones, and so does the active rig if it is a
        shipped one (as the user's copy, so their show doesn't change); then settings.json is
        rewritten without them."""
        legacy = self._legacy_fog
        self._legacy_fog = None
        if legacy is None:
            return
        machines: list[dict] = []
        for m in legacy if isinstance(legacy, list) else []:
            try:
                machines.append(FogMachine.model_validate(m).model_dump(mode="json", exclude_none=True))
            except ValidationError as exc:
                log.error("settings.json: a fog machine can't be read, dropped:\n%s", exc)
        moved: list[str] = []
        try:
            for name, d, u in self._layer(RIGS).values():
                path, shipped = u, False
                if u is None and name.lower() == self.settings.active_rig.lower() and machines:
                    path, shipped = self.root / RIGS / f"{name}.json", True
                if path is None:
                    continue
                data = json.loads((u or d).read_text(encoding="utf-8"))  # type: ignore[union-attr]
                if not isinstance(data, dict) or ("fog_machines" in data and not shipped):
                    continue
                if shipped and data.get("fog_machines") == machines:
                    continue  # the shipped rig already has the same machines
                data.pop(VERSION_KEY, None)
                data["fog_machines"] = machines
                write_json(path, data)
                moved.append(name)
            self.save_settings()  # fog isn't a setting any more: this drops it from the file
        except (OSError, ValueError) as exc:
            log.error("moving the fog machines into the rigs failed: %s", exc)
            return
        log.info("fog machines moved from settings.json into the rigs: %s", ", ".join(moved) or "none needed")
        if machines and moved:
            self.notice(f"Fog machines are now part of each rig: yours were moved from settings.json into {', '.join(moved)}.")

    # -- settings: model defaults <- shipped settings.json <- user settings.json <- machine.json
    def _read_json(self, path: Path, user: bool) -> dict:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as exc:
            log.error("%s: cannot be read (%s)", path, exc)
            if user:
                self.broken_file(path, "invalid JSON")
            return {}
        data.pop(VERSION_KEY, None)
        return data

    def settings_base(self) -> dict:
        """The settings before the user changed anything: the model's defaults and the shipped file."""
        base = Settings().model_dump(mode="json")
        if self.defaults is not None:
            shipped = merge(base, self._read_json(self.defaults / "settings.json", user=False))
            try:  # as the model sees it, so keys it fills in don't count as changes
                base = Settings.model_validate(shipped).model_dump(mode="json")
            except ValidationError as exc:
                log.error("shipped settings.json: invalid content, ignored:\n%s", exc)
        return base

    def load_settings(self) -> None:
        merged = self.settings_base()
        user = self._read_json(self.settings_path, user=True)
        machine = self._read_json(self.machine_path, user=True)
        fog = user.get("fog")
        # fog machines of 1.4 and earlier, for move_fog_into_rigs (None: nothing to move)
        self._legacy_fog = fog.get("machines", []) if isinstance(fog, dict) else None
        for data, path in ((user, self.settings_path), (machine, self.machine_path)):
            candidate = merge(merged, data)
            try:
                Settings.model_validate(candidate)
            except ValidationError as exc:
                log.error("%s: invalid content:\n%s", path, exc)
                self.broken_file(path, "invalid content")
                continue
            merged = candidate
        self.settings = Settings.model_validate(merged)
        report_unknown_keys(self.settings, "settings")
        # self-healing: per-computer values in the user's settings.json (written before 1.4, or by hand)
        # move to machine.json, which makes the user's file sparse at the same time
        if has_machine_keys(user):
            try:
                self.save_settings()
                log.info("per-computer settings moved from %s to %s", self.settings_path, self.machine_path)
            except OSError as exc:
                log.warning("cannot rewrite the settings: %s", exc)

    def save_settings(self) -> None:
        """Only what differs from the shipped settings: the show to the data folder, the rest to machine.json."""
        show, machine = split_machine(self.settings.model_dump(mode="json"))
        base_show, base_machine = split_machine(self.settings_base())
        write_json(self.settings_path, diff(base_show, show))
        write_json(self.machine_path, diff(base_machine, machine))

    # -- fixture types
    def load_fixture_types(self) -> None:
        self.fixture_types = {}
        for name, d, u in sorted(self._layer(TYPES).values(), key=lambda x: x[0].lower()):
            ftype = load_model(u, FixtureType, broken=self.broken_file, name=name) if u else None
            if ftype is None and d is not None:  # no user file, or a broken one (moved away)
                ftype, name = load_model(d, FixtureType, name=d.stem), d.stem
            if ftype is not None:
                ftype.name = name  # the file name is the type name
                self.fixture_types[name] = ftype
        log.info("loaded %d fixture types: %s", len(self.fixture_types), ", ".join(self.fixture_types))

    def names_map(self, rel: str) -> dict[str, str]:
        """lower-case name -> name as listed (a broken user file moved away gives the shipped spelling)."""
        return {k: v[0] for k, v in self._layer(rel).items()}

    def type_origins(self) -> dict[str, Origin]:
        return self.origins(TYPES, FixtureType)

    def type_path(self, name: str) -> Path:
        return self.write_path(TYPES, name)

    def save_fixture_type(self, ftype: FixtureType) -> None:
        # the file name is the type name, so it isn't repeated inside the file
        write_json(self.type_path(ftype.name), ftype.model_dump(mode="json", exclude_none=True, exclude={"name"}))

    def load_fixture_type(self, name: str) -> FixtureType | None:
        ftype = self._load_layered(TYPES, name, FixtureType, name=name)
        if ftype is not None:
            ftype.name = name
        return ftype

    def type_name_problem(self, name: str) -> str | None:
        """Why ``name`` can't be used for a new fixture type, or None."""
        if not RIG_NAME.fullmatch(name):
            return "use letters, digits, space, - _ . (max 64, starting with a letter or digit)"
        taken = next((n for n in [*self.fixture_types, *self.names(TYPES)] if n.lower() == name.lower()), None)
        if taken is not None:
            return f"the fixture type '{taken}' already exists"
        return None

    def type_usage(self) -> dict[str, list[str]]:
        """Fixture type -> the rigs using it: every rig file, the active rig as it is live."""
        usage: dict[str, set[str]] = {}
        names = self.rig_names()
        for name in names:
            rig = self.rig if name.lower() == self.rig.name.lower() else self.load_rig_file(name)
            for fx in rig.fixtures if rig else []:
                usage.setdefault(fx.type, set()).add(name)
        if self.rig.name.lower() not in {n.lower() for n in names}:  # active rig without a file yet
            for fx in self.rig.fixtures:
                usage.setdefault(fx.type, set()).add(self.rig.name)
        return {t: sorted(r) for t, r in usage.items()}

    def rename_fixture_type(self, old: str, new: str) -> list[str]:
        """Rename a type and update every rig that uses it (rigs are saved to the user folder, the live
        rig keeps its unsaved changes unsaved). A shipped type stays: renaming it makes a user copy.
        Returns the rigs that were changed."""
        saved = self.load_fixture_type(old) or self.fixture_types[old].model_copy(deep=True)
        saved.name = new
        user_old = self.user_file(TYPES, old)
        # delete before writing: on case-insensitive file systems (macOS, Windows) a rename that only
        # changes letter case would otherwise delete the file it just wrote
        if user_old is not None:
            user_old.unlink()
        self.save_fixture_type(saved)
        live = self.fixture_types.pop(old)
        live.name = new
        self.fixture_types[new] = live
        if new.lower() != old.lower() and self.default_file(TYPES, old) is not None:
            shipped = self.load_fixture_type(old)
            if shipped is not None:
                self.fixture_types[old] = shipped
        changed: list[str] = []
        for name in self.rig_names():
            rig = self.load_rig_file(name)
            if rig is not None and any(fx.type == old for fx in rig.fixtures):
                for fx in rig.fixtures:
                    if fx.type == old:
                        fx.type = new
                rig.name = name
                save_model(self.rig_path(name), rig)
                changed.append(name)
        for fx in self.rig.fixtures:
            if fx.type == old:
                fx.type = new
                if self.rig.name not in changed:
                    changed.append(self.rig.name)
        log.info("renamed fixture type '%s' to '%s' (rigs updated: %s)", old, new, ", ".join(changed) or "none")
        return changed

    def delete_fixture_type(self, name: str) -> None:
        """Delete the user's type file (a shipped type can't be deleted, see ``reset_fixture_type``)."""
        path = self.user_file(TYPES, name)
        if path is not None:
            path.unlink(missing_ok=True)
        self.fixture_types.pop(name, None)
        log.info("deleted fixture type '%s'", name)

    def reset_fixture_type(self, name: str) -> FixtureType | None:
        """Back to the shipped version: delete the user's copy. None if the type isn't shipped."""
        if self.default_file(TYPES, name) is None:
            return None
        path = self.user_file(TYPES, name)
        if path is not None:
            path.unlink(missing_ok=True)
        ftype = self.load_fixture_type(name)
        if ftype is not None:
            self.fixture_types[name] = ftype
        log.info("fixture type '%s' reset to the shipped version", name)
        return ftype

    # -- rigs
    def rig_names(self) -> list[str]:
        return self.names(RIGS)

    def rig_origins(self) -> dict[str, Origin]:
        return self.origins(RIGS, Rig)

    def rig_path(self, name: str) -> Path:
        return self.write_path(RIGS, name)

    def load_rig_file(self, name: str) -> Rig | None:
        rig = self._load_layered(RIGS, name, Rig, name=name)
        if rig is not None:
            rig.name = self.names_map(RIGS).get(name.lower(), name)
        return rig

    def load_rig(self, name: str) -> None:
        rig = self.load_rig_file(name) if name else None
        if rig is None:
            # self-healing: a missing (or unreadable) active rig falls back to the Default rig, else
            # to the first one, else an empty rig
            fallback = next((n for n in [DEFAULT_RIG, *self.rig_names()] if self.find(RIGS, n)), None)
            rig = self.load_rig_file(fallback) if fallback else None
            rig = rig or Rig(name=fallback or name or DEFAULT_RIG)
            if name and name.lower() != rig.name.lower():
                self.notice(f"The rig “{name}” was not found; “{rig.name}” is loaded instead.")
                self.settings.active_rig = rig.name
                try:
                    self.save_settings()
                except OSError as exc:
                    log.warning("cannot save the settings: %s", exc)
        self.rig = rig
        # an old rig file's mask curve becomes the macro Mask Curve, once (the engine takes it; item 76)
        self.legacy_mask_curve = rig.legacy_mask_curve or None
        self.fill_legacy_react_to_strobo(self.rig)
        problems = self.validate_rig()
        for p in problems:
            if "unknown type" in p or "unknown mode" in p:
                self.notice(f"Rig “{self.rig.name}”: {p}.")
        log.info("loaded rig '%s' with %d fixtures", self.rig.name, len(self.rig.fixtures))

    def fill_legacy_react_to_strobo(self, rig: Rig) -> None:
        """Rigs from before 2026-10-08 left react_to_strobo to the fixture type: take it from there
        (old type files still carry it), so the show looks the same; the next save writes it."""
        for fx in rig.fixtures:
            if "react_to_strobo" not in fx.model_fields_set:
                ftype = self.fixture_types.get(fx.type)
                fx.react_to_strobo = bool(ftype and ftype.legacy_react_to_strobo)

    def validate_rig(self) -> list[str]:
        """Log problems in the rig: unknown types and overlapping DMX ranges."""
        problems: list[str] = []
        used: dict[tuple[int, int], str] = {}
        for fx in self.rig.fixtures:
            ftype = self.fixture_types.get(fx.type)
            if ftype is None:
                problems.append(f"fixture '{fx.name}': unknown type '{fx.type}' (it will be skipped)")
                continue
            if not fx.enabled or ftype.transport != "dmx":
                continue
            if fx.mode and not ftype.has_mode(fx.mode):
                problems.append(
                    f"fixture '{fx.name}': unknown mode '{fx.mode}' of type '{fx.type}' "
                    f"(the default mode '{ftype.mode_of(None).name}' is used)"
                )
            count = ftype.channel_count(fx.mode)
            end = fx.address + count - 1
            if end > 512:
                problems.append(f"fixture '{fx.name}': channels {fx.address}-{end} exceed 512")
            for ch in range(fx.address, min(end, 512) + 1):
                other = used.get((fx.universe, ch))
                if other and other != fx.name:
                    problems.append(
                        f"fixture '{fx.name}' overlaps '{other}' in universe {fx.universe} at channel {ch}"
                    )
                    break
                used[(fx.universe, ch)] = fx.name
        for fog in self.rig.fog_machines:
            other = used.get((fog.universe, fog.channel))
            if other:
                problems.append(f"fog machine '{fog.name}' uses channel {fog.channel} of universe {fog.universe}, which '{other}' uses too")
        for p in problems:
            log.warning("rig '%s': %s", self.rig.name, p)
        return problems

    def save_rig(self) -> None:
        save_model(self.rig_path(self.rig.name), self.rig)

    def dimmer_unassigned(self, macro: str) -> bool:
        """A dimmer macro no fixture of the active rig uses (enabled or not): disabled in the UI,
        ignored by MIDI."""
        return macro.startswith("Dimmer ") and not any(f.dimmer_macro == macro for f in self.rig.fixtures)

    def rig_name_problem(self, name: str) -> str | None:
        """Why ``name`` can't be used for a new rig file, or None."""
        if not RIG_NAME.fullmatch(name):
            return "use letters, digits, space, - _ . (max 64, starting with a letter or digit)"
        taken = next((n for n in self.rig_names() if n.lower() == name.lower()), None)
        if taken is not None:  # case-insensitive: macOS and Windows file names are
            return f"the rig '{taken}' already exists"
        return None

    def rename_rig(self, new: str) -> None:
        """Rename the active rig. Unsaved live changes stay unsaved. A shipped rig stays listed:
        renaming it makes a user copy under the new name."""
        old = self.rig.name
        # the file keeps its saved content; a missing or broken file takes the live rig
        saved = self.load_rig_file(old) or self.rig.model_copy(deep=True)
        saved.name = new
        user_old = self.user_file(RIGS, old)
        if user_old is not None:
            user_old.unlink()  # before writing: a case-only rename on macOS / Windows
        save_model(self.root / RIGS / f"{new}.json", saved)
        self.rig.name = new
        self.settings.active_rig = new
        self.save_settings()
        log.info("renamed rig '%s' to '%s'", old, new)

    def delete_rig(self, name: str) -> None:
        """Delete the user's rig file (a shipped rig can't be deleted, see ``reset_rig``)."""
        path = self.user_file(RIGS, name)
        if path is not None:
            path.unlink()
        log.info("deleted rig '%s'", name)

    def reset_rig(self) -> bool:
        """Back to the shipped version of the active rig: delete the user's copy and reload it."""
        name = self.rig.name
        if self.default_file(RIGS, name) is None:
            return False
        path = self.user_file(RIGS, name)
        if path is not None:
            path.unlink(missing_ok=True)
        self.load_rig(name)
        log.info("rig '%s' reset to the shipped version", name)
        return True

    # -- OSC files: arrays of "what to send where" (io/osc.py); the app ships examples, the user adds their own
    def osc_names(self) -> list[str]:
        return self.names(OSC)

    def find_osc(self, name: str) -> Path | None:
        return self.find(OSC, name)

    # -- controllers
    def controller_names(self) -> list[str]:
        return self.names(CONTROLLERS)

    def load_controller(self, name: str | None) -> None:
        self.controller = None
        if name:
            self.controller = self._load_layered(CONTROLLERS, name, Controller, name=name)
            if self.controller is None:
                self.notice(f"The MIDI controller mapping “{name}” was not found; no controller is used.")
            elif _had_page_knob(self.find(CONTROLLERS, name)):
                self.notice(
                    f"The MIDI controller mapping “{name}” has a page knob, which no longer exists: it is ignored. "
                    "Switch the control page with the Page General / Page Dimmers macros (map a button or knob to "
                    "them) or on screen. Saving the mapping writes it without the page knob."
                )

    def load_controller_file(self, name: str) -> Controller | None:
        return self._load_layered(CONTROLLERS, name, Controller, name=name)

    def controller_origins(self) -> dict[str, Origin]:
        return self.origins(CONTROLLERS, Controller)

    def controller_labels(self) -> dict[str, str]:
        """File name → the name shown in lists: the ``name`` inside the file, or the file name if there is none."""
        out: dict[str, str] = {}
        for name in self.controller_names():
            path = self.find(CONTROLLERS, name)
            label = ""
            try:
                data = json.loads(path.read_text(encoding="utf-8")) if path else {}
                label = str(data.get("name") or "").strip() if isinstance(data, dict) else ""
            except (OSError, ValueError):
                pass
            out[name] = label or name
        return out

    def controller_name_problem(self, name: str) -> str | None:
        """Why ``name`` can't be used for a new controller file, or None."""
        if not RIG_NAME.fullmatch(name):
            return "use letters, digits, space, - _ . (max 64, starting with a letter or digit)"
        taken = next((n for n in self.controller_names() if n.lower() == name.lower()), None)
        if taken is not None:
            return f"the controller '{taken}' already exists"
        return None

    def save_controller(self, name: str, ctrl: Controller) -> Controller:
        """Write a controller to the user's folder (a shipped one gets a user copy that takes its place),
        stamped with the time of the edit; the file also records the app version (``write_json``)."""
        ctrl.modified = datetime.now().astimezone().isoformat(timespec="seconds")
        # defaults are left out, so a mapping reads {"number": 29, "macro": "Hue A", "page": "general"}
        write_json(self.write_path(CONTROLLERS, name), ctrl.model_dump(mode="json", exclude_none=True, exclude_defaults=True))
        if self.settings.active_controller and self.settings.active_controller.lower() == name.lower():
            self.controller = ctrl
        return ctrl

    def delete_controller(self, name: str) -> None:
        """Delete the user's controller file (a shipped one can't be deleted, see ``reset_controller``)."""
        path = self.user_file(CONTROLLERS, name)
        if path is not None:
            path.unlink(missing_ok=True)
        log.info("deleted controller '%s'", name)

    def reset_controller(self, name: str) -> Controller | None:
        """Back to the shipped version: delete the user's copy. None if the controller isn't shipped."""
        if self.default_file(CONTROLLERS, name) is None:
            return None
        path = self.user_file(CONTROLLERS, name)
        if path is not None:
            path.unlink(missing_ok=True)
        if self.settings.active_controller and self.settings.active_controller.lower() == name.lower():
            self.load_controller(name)
        log.info("controller '%s' reset to the shipped version", name)
        return self.load_controller_file(name)

    # -- scenes (none ship; an empty slot means the macro defaults)
    def scene_name(self, index: int) -> str:
        return f"scene_{index + 1}"

    def scene_path(self, index: int) -> Path:
        return self.write_path(SCENES, self.scene_name(index))

    def load_scene(self, index: int) -> Scene | None:
        return self._load_layered(SCENES, self.scene_name(index), Scene)

    def save_scene(self, index: int, scene: Scene) -> None:
        save_model(self.scene_path(index), scene)

    def delete_scene(self, index: int) -> bool:
        path = self.user_file(SCENES, self.scene_name(index))
        if path is None:
            return False
        path.unlink(missing_ok=True)
        log.info("deleted scene %d", index + 1)
        return True
