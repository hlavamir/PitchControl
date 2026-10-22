"""A whole Open Fixture Library fixture -> a PitchControl fixture type that keeps the OFL data (item 53).

``convert.py`` maps the modes; this module wraps them into the type file, keeps what PitchControl doesn't use, writes
the import report and can build the original OFL fixture back from the type (``rebuild_ofl``).

Miro's two rules (2026-10-22): PitchControl keeps its own JSON format and, when it grows, stays close to OFL's (OFL's
names and shapes wherever the meaning is the same); an import keeps as much of the original data as possible, even
what PitchControl doesn't use. Items 54 (QLC+ import, which goes through the OFL model and this module) and 55 (an OFL
export plugin in JavaScript, whose file must equal the one this import makes) depend on the shape below.

THE SHAPE OF AN IMPORTED TYPE FILE (everything not listed here is PitchControl's own: ``description``, ``transport``,
``modes``, ``default_mode``, ``gamma``, ``strobo_color``):

* OFL's top-level keys keep their OFL names and values, untouched: ``shortName``, ``categories``, ``meta``,
  ``comment``, ``links``, ``helpWanted``, ``rdm``, ``physical``, ``matrix``, ``wheels``, ``availableChannels``,
  ``templateChannels`` (and any other key the fixture has, e.g. a hand-written ``_source``). ``links`` (manual,
  product page, video) is shown on the Fixtures page.
* ``ofl_modes``: OFL's own ``modes`` list, untouched. (OFL's ``modes`` would collide with PitchControl's ``modes``.)
* every PitchControl mode has ``ofl_mode``: the ``name`` of the OFL mode it was converted from. OFL modes that were
  not converted (see the report) are in ``ofl_modes`` only. A mode the user adds or copies by hand has no OFL mode,
  or the copy's.
* ``source``: where the data came from and what is needed to rebuild the OFL file:

  ``format``      always ``"ofl"``: the kept keys are an OFL fixture
  ``fixture``     OFL's key, ``"manufacturer-key/fixture-key"`` (absent for a file imported by hand)
  ``name``        OFL's own ``name`` (the type's name, i.e. its file name, is the user's: usually manufacturer + name)
  ``manufacturer``  the manufacturer's name (OFL's ``manufacturers.json``; absent when not known)
  ``url``         the fixture's page on open-fixture-library.org
  ``schema``      OFL's ``$schema`` value
  ``license``     ``"MIT"`` (the Open Fixture Library's licence; absent for a QLC+ file, which is the user's own)
  ``via``         ``"qlcplus"`` when the OFL fixture was built from a QLC+ ``.qxf`` (item 54), absent otherwise
  ``converter``   the version of this mapping (``CONVERTER_VERSION``; item 55's JavaScript has the same number)
  ``key_order``   OFL's top-level keys in their original order (for an exact rebuild)
  ``note``        free text, e.g. for a fixture written by hand from a manual
  A file downloaded from open-fixture-library.org ("Download as" → "Open Fixture Library JSON") has three keys more than
  OFL's repository (``fixtureKey``, ``manufacturerKey``, ``oflURL``) and the schema version in ``$schema``: they are
  kept like the others, and give ``fixture`` and ``schema_version`` to an import from a file.
  And where this copy was fetched from, which two imports of the same fixture may differ in (the comparison of items
  54 and 55 leaves them out): ``commit`` (OFL's git commit, online imports), ``file`` (the file name, imports
  from a file), ``schema_version`` (the version of OFL's schema at that commit, when known).

* the importer adds no other keys, so a type that came from QLC+ (item 54) has the same shape: ``source.format``
  is ``"ofl"`` (it went through the OFL model, ``qlcplus.py``), ``source.via`` is ``"qlcplus"``, ``source.file`` the
  ``.qxf``'s name, and the top-level key ``qlcplus`` has what OFL's model can't hold: ``creator`` (name, version,
  author of the file), ``type`` (QLC+'s own ``Type``), ``unmapped`` (every element and attribute of the file the
  reader did not use, with its path) and ``xml`` (the file itself). ``rebuild_ofl`` then gives the OFL fixture the
  reader built from the file (``fixture`` and ``schema_version`` are absent: it is no OFL fixture).

``rebuild_ofl`` is the inverse: the top-level keys in ``source.key_order``, with ``$schema`` and ``name`` from
``source``, ``modes`` from ``ofl_modes`` and the rest from the type. For a type that was imported and not edited
(editing the kept keys by hand is not supported) it returns the original fixture exactly; editing PitchControl's own
keys (modes, gamma, description) never changes it.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .convert import Converted, convert_fixture, short_reason

CONVERTER_VERSION = 1  # bump with the mapping in convert.py / this file, and with item 55's export.js
OFL_SCHEMA_MAJOR = 12  # the OFL schema the mapping was written against (12.6.0, 2026-10)
OFL_SITE = "https://open-fixture-library.org"
LICENSE = "MIT"

MODES_KEY = "ofl_modes"
MODE_KEY = "ofl_mode"
# OFL's keys that are not kept under their own name at the top level
NOT_KEPT = ("$schema", "name", "modes")
# the order of OFL's schema (schemas/fixture.json), used to rebuild a fixture whose key order isn't recorded
SCHEMA_ORDER = ["$schema", "name", "shortName", "categories", "meta", "comment", "links", "helpWanted", "rdm", "physical", "matrix", "wheels", "availableChannels", "templateChannels", "modes"]

CHECK = "Open Fixture Library fixtures are written by volunteers: compare the modes, channels and values with the fixture's manual before using the type."


class ImportProblem(ValueError):
    """The data is not something that can be imported (not an OFL fixture, a redirect, ...); the message is for the user."""


class Redirect(ImportProblem):
    """OFL's file is a redirect to another fixture (``redirectTo``)."""

    def __init__(self, target: str, reason: str = ""):
        super().__init__(f"this OFL file only points to another fixture: {target}" + (f" ({reason})" if reason else ""))
        self.target = target


@dataclass
class Report:
    """What an import did, for the dialog before saving."""

    fixture: dict[str, Any] = field(default_factory=dict)  # name, manufacturer, key, url
    modes: list[dict[str, Any]] = field(default_factory=list)  # taken: name, ofl_mode, pixels, channels, description
    skipped: list[dict[str, str]] = field(default_factory=list)  # mode, reason, detail
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)  # the fixture's manual links, if OFL has any
    check: str = CHECK
    dropped: list[str] = field(default_factory=list)  # what the source format has and the OFL model can't hold (QLC+ import: kept under ``qlcplus``)

    def as_json(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "modes": self.modes,
            "skipped": self.skipped,
            "assumptions": self.assumptions,
            "notes": self.notes,
            "manual": self.manual,
            "check": self.check,
            "dropped": self.dropped,
        }


@dataclass
class Imported:
    name: str  # the suggested type name (a file name)
    ftype: dict | None  # None: no mode could be converted
    report: Report
    converted: Converted


# --------------------------------------------------------------------------- names


def type_name(manufacturer: str | None, fixture_name: str) -> str:
    """A type name (it is a file name: letters, digits, space, - _ . and at most 64) from OFL's names: the manufacturer
    first unless the fixture name has it already, "/" becomes "-" ("LED Bar 240/8" -> "Stairville LED Bar 240-8")."""
    text = fixture_name.strip()
    if manufacturer and not text.lower().startswith(manufacturer.lower()):
        maker = manufacturer.strip()
        text = f"{maker[:1].upper() + maker[1:] if maker.islower() else maker} {text}"  # OFL has "cameo"
    text = unicodedata.normalize("NFKD", text.replace("/", "-")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9 _.\-]", "", text)
    text = re.sub(r"\s+", " ", text).strip().lstrip(" _.-")
    return text[:64].rstrip() or "Imported fixture"


def fixture_url(key: str) -> str:
    return f"{OFL_SITE}/{key}"


# --------------------------------------------------------------------------- import


def _check_fixture(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ImportProblem("this is not an Open Fixture Library fixture (the JSON is not an object)")
    if "redirectTo" in data:
        raise Redirect(str(data["redirectTo"]), str(data.get("reason", "")))
    if not isinstance(data.get("modes"), list) or not data["modes"] or not isinstance(data.get("name"), str):
        raise ImportProblem("this is not an Open Fixture Library fixture (no name or no modes)")
    if not all(isinstance(m, dict) and isinstance(m.get("name"), str) and isinstance(m.get("channels"), list) for m in data["modes"]):
        raise ImportProblem("this is not an Open Fixture Library fixture (a mode has no name or no channels)")
    return data


def _key_of(data: dict) -> str | None:
    """``maker/fixture`` of a file downloaded from the website (it carries ``manufacturerKey`` and ``fixtureKey``)."""
    maker, fixture = data.get("manufacturerKey"), data.get("fixtureKey")
    return f"{maker}/{fixture}" if isinstance(maker, str) and isinstance(fixture, str) else None


def _schema_version_of(data: dict) -> str | None:
    """The schema version in the website download's ``$schema``: ``…/schema-12.6.0/schemas/fixture.json``."""
    match = re.search(r"/schema-(\d+\.\d+\.\d+)/", str(data.get("$schema", "")))
    return match[1] if match else None


def _maker_hint(data: dict) -> str | None:
    """The manufacturer key of a downloaded file as words (``american-dj`` -> ``American Dj``), for the suggested name only."""
    maker = data.get("manufacturerKey")
    return maker.replace("-", " ").title() if isinstance(maker, str) and maker else None


def _channel_count(mode: dict) -> int:
    return sum(mode["pixels"] * len(slot["pixels"]) if "pixels" in slot and slot["pixels"] else 1 for slot in mode["channels"])


def _assumptions(converted: Converted) -> list[str]:
    counts: dict[str, int] = {}
    for line in converted.assumptions:
        counts[line] = counts.get(line, 0) + 1
    return [f"{line} (in {n} modes)" if n > 1 else line for line, n in counts.items()]


def import_fixture(
    data: Any,
    *,
    fixture: str | None = None,
    manufacturer: str | None = None,
    commit: str | None = None,
    file: str | None = None,
    schema_version: str | None = None,
    skip: dict[str, str] | None = None,
    note: str | None = None,
    via: str | None = None,
    where: str | None = None,
    licence: str | None = LICENSE,
    keep: dict[str, Any] | None = None,
    check: str = CHECK,
) -> Imported:
    """The PitchControl type for one OFL fixture (the parsed JSON) and the report of the import. ``skip`` leaves OFL
    modes out on purpose (OFL mode name -> why; reported like the ones that can't be converted). Raises
    ``ImportProblem`` for data that isn't an OFL fixture and ``Redirect`` for a redirect file.

    The QLC+ import (``qlcplus.py``) builds an OFL fixture from a ``.qxf`` and calls this with ``via="qlcplus"`` (where
    it came from, ``source.via``), ``where`` (the words for the description), ``licence`` (None: the user's own file),
    ``keep`` (more keys of the type: ``{"qlcplus": …}``) and its own ``check`` line."""
    data = copy.deepcopy(_check_fixture(data))
    converted = convert_fixture(data, skip)
    key = fixture or _key_of(data)
    schema_version = schema_version or _schema_version_of(data)
    report = Report(
        check=check,
        fixture={"name": data["name"], "manufacturer": manufacturer, "key": key, "url": fixture_url(key) if key else None},
        skipped=[{"mode": name, "reason": short_reason(why), "detail": why} for name, why in converted.skipped],
        assumptions=_assumptions(converted),
        manual=[u for u in data.get("links", {}).get("manual", []) if isinstance(u, str)] if isinstance(data.get("links"), dict) else [],
    )
    if schema_version and schema_version.split(".")[0] != str(OFL_SCHEMA_MAJOR):
        report.assumptions.append(f"this fixture is in OFL schema {schema_version}; the conversion was written for {OFL_SCHEMA_MAJOR}.x, so look at the result closely")
    name = type_name(manufacturer or _maker_hint(data), data["name"])
    if not converted.modes:
        report.notes.append("none of this fixture's modes can be expressed in PitchControl, so nothing is imported")
        return Imported(name, None, report, converted)
    for mode in converted.modes:
        report.modes.append(
            {"name": mode["name"], "ofl_mode": mode[MODE_KEY], "pixels": mode["pixels"], "channels": _channel_count(mode), "description": mode["description"]}
        )
    default = converted.modes[0]
    report.notes.append(f"the default mode is {default['name']} (the first one; change it on the Fixtures page)")

    shown = f"{manufacturer} {data['name']}" if manufacturer and not data["name"].lower().startswith(manufacturer.lower()) else data["name"]
    cats = data.get("categories")
    where = where or f"the Open Fixture Library (MIT licence{', ' + key if key else ''}{', commit ' + commit[:7] if commit else ''})"
    source: dict[str, Any] = {
        "format": "ofl",
        "fixture": key,
        "name": data["name"],
        "manufacturer": manufacturer,
        "url": fixture_url(key) if key else None,
        "schema": data.get("$schema"),
        "license": licence,
        "via": via,
        "converter": CONVERTER_VERSION,
        "key_order": list(data),
        "note": note,
        "commit": commit,
        "file": file,
        "schema_version": schema_version,
    }
    ftype: dict[str, Any] = {
        "description": (
            f"{shown}{' (' + ', '.join(cats) + ')' if isinstance(cats, list) and cats else ''}. Imported from {where}. "
            f"Modes: {', '.join(m['name'] for m in converted.modes)}; {default['name']} is the default. Check the type against the manual."
        ),
        "transport": "dmx",
        "modes": converted.modes,
        "default_mode": default["id"],
        "gamma": 1.0,
        "strobo_color": {"h": 0.0, "s": 0.0, "b": 1.0},
        "source": {k: v for k, v in source.items() if v is not None},
    }
    for k, v in data.items():
        if k not in NOT_KEPT:
            ftype[k] = v
    ftype[MODES_KEY] = data["modes"]
    ftype.update(copy.deepcopy(keep or {}))
    return Imported(name, ftype, report, converted)


# --------------------------------------------------------------------------- the way back


def rebuild_ofl(ftype: dict) -> dict:
    """The OFL fixture an imported type was made from (see the module doc)."""
    source = ftype.get("source") or {}
    values = {"$schema": source.get("schema"), "name": source.get("name"), "modes": ftype.get(MODES_KEY)}
    order = source.get("key_order") or SCHEMA_ORDER
    out: dict[str, Any] = {}
    for key in order:
        value = values[key] if key in values else ftype.get(key)
        if value is not None:
            out[key] = copy.deepcopy(value)
    return out
