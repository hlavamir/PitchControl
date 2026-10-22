"""Check the Open Fixture Library export plugin "PitchControl" (item 55) against the app's own OFL import (item 53).

    py tools/ofl_plugin_check.py                 # the item 50 fixtures and a few more; sets OFL up the first time
    py tools/ofl_plugin_check.py --all           # every fixture of the pinned OFL checkout (about 650)
    py tools/ofl_plugin_check.py --ofl DIR       # use your own OFL checkout (needs ``npm ci`` run in it)

Run it with the Python that has the backend installed (``backend/.venv``, or ``pip install -e backend``): it imports
``pitchcontrol``. Node 26 and git are needed; so is the internet the first time (a shallow fetch of OFL at the pinned
commit into ``<temp>/pitchcontrol-ofl-check`` and ``npm ci`` there; ``--ofl-source`` takes a local OFL clone instead of
GitHub to fetch from).

What it does:

1. gets OFL at ``OFL_COMMIT`` (or takes the checkout of ``--ofl``) and copies ``tools/open-fixture-library/plugins/pitch-control/``
   into its ``plugins/`` (``plugins.json`` is rebuilt there with ``node cli/build-plugin-data.js``; the copy and the
   change of ``plugins.json`` are undone at the end, nothing is ever committed in OFL);
2. runs the app's import (``pitchcontrol.ofl.importer.import_fixture``, saved the way the app saves a type: through the
   ``FixtureType`` model) on the OFL JSON of each fixture, and OFL's CLI, ``node cli/export-fixture.js -p pitch-control``,
   on the same fixtures;
3. compares the two: the same fixtures with a file, the same file name, and the same content (every key, every value,
   the order of the keys; ``1`` and ``1.0`` are the same number). The Python import is given what the plugin knows
   (the fixture's key, the manufacturer's name, OFL's schema version) and **not** what only an import knows: ``source.commit``
   and ``source.file``. A second run of the import *with* a commit and a file name must then differ in exactly these
   places (``source.commit``, ``source.file``, the ``, commit <hash>`` of the description) and nowhere else;
4. loads every exported file through the app's ``FixtureType`` model (no warning allowed) and writes it back: the same
   content;
5. runs OFL's own checks of the plugin: ``eslint`` on the plugin folder, the plugin's export tests
   (``node cli/run-export-test.js -p pitch-control``) and a rebuild of ``plugins.json`` that lists the plugin.

The differences between the plugin's file and a file the app saved after an import, all of them (README.md, "How the
file differs from an import"): the app's ``app_version`` stamp (it writes the version of the app that saved the file),
``source.commit`` and ``source.file`` (where the copy was fetched from), the commit in the description, and how a number
is written (``1.0`` or ``1``). Nothing else may differ; this script fails when something does.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pitchcontrol.config.models import FixtureType  # noqa: E402
from pitchcontrol.ofl.importer import import_fixture  # noqa: E402

from fixture_library import LIBRARY, SOURCES  # noqa: E402

PLUGIN_KEY = "pitch-control"
PLUGIN_SOURCE = ROOT / "tools" / "open-fixture-library" / "plugins" / PLUGIN_KEY
OFL_REPO = "https://github.com/OpenLightingProject/open-fixture-library.git"
OFL_COMMIT = "cfcb0c5b0cbb4aa0b058492a4d8586c53503b2ff"  # master on 2026-10-22 (schema 12.6.0)
FAKE_COMMIT = "0123456789abcdef0123456789abcdef01234567"

# fixtures besides the item 50 ones, each for a part of the mapping the item 50 fixtures don't reach
EXTRAS = {
    "american-dj/mega-bar-rgba": "pixel groups; three of four modes have an amber per pixel, so they are left out",
    "american-dj/crazy-pocket-8": "pixel groups, 16-bit channels, a moving head",
    "american-dj/flat-par-qa12": "switching channels",
    "alien-pro/alien-s": "switching channels, template channels, pixel groups",
    "american-dj/12p-hex-ip": "colour presets and a strobe channel",
    "american-dj/inno-pocket-spot": "gobo resources in the wheels (OFL's model embeds them)",
    "stairville/mh-x20": "gobo resources by alias",
    "afx/lmh460z": "a moving head with percent defaults and 16-bit channels",
    "cameo/thunder-wash-600-rgb": "a strobe per pixel group",
    "chauvet-dj/slimpar-pro-h-usb": "an RGBA+UV PAR (also imported online in item 53's check)",
    "chauvet-dj/megastrobe-fx12": "pixel groups named like numbers, one mode left out",
    "infinity/iw-720-rdm": "pixel groups named like numbers (the order of the keys, see the README)",
    "lixada/mini-beam-rgbw": "a twin of another brand (OFL's redirect SameAsDifferentBrand)",
    "american-dj/uv-eco-bar": "no mode PitchControl can use: the app imports nothing, the plugin has to refuse",
    "clay-paky/show-batten-100": "no mode PitchControl can use (a second one)",
}

REPORT_WIDTH = 100


# --------------------------------------------------------------------------- OFL checkout


def run(command: list[str], cwd: Path, *, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a command, with ``npm`` / ``node`` found the way the platform needs (npm is npm.cmd on Windows)."""
    exe = shutil.which(command[0])
    if exe is None:
        raise SystemExit(f"'{command[0]}' is not installed or not on the PATH")
    result = subprocess.run([exe, *command[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        if not quiet:
            print(result.stdout[-3000:], result.stderr[-3000:])
        raise SystemExit(f"'{' '.join(command)}' failed in {cwd} (exit {result.returncode})")
    return result


def prepare_ofl(directory: Path, source: str) -> None:
    """A shallow checkout of OFL at ``OFL_COMMIT`` in ``directory``, with its npm packages."""
    if not (directory / ".git").exists():
        print(f"setting OFL up in {directory} (commit {OFL_COMMIT[:7]}) ...")
        directory.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "--quiet"], directory)
        run(["git", "fetch", "--quiet", "--depth", "1", source, OFL_COMMIT], directory)
        run(["git", "checkout", "--quiet", "FETCH_HEAD"], directory)
    head = run(["git", "rev-parse", "HEAD"], directory).stdout.strip()
    if head != OFL_COMMIT:
        print(f"note: {directory} is at {head[:7]}, not at the pinned commit {OFL_COMMIT[:7]}")
    if not (directory / "node_modules").exists():
        print("npm ci in the OFL checkout (about a minute) ...")
        run(["npm", "ci", "--no-audit", "--no-fund"], directory)


def install_plugin(ofl: Path) -> None:
    target = ofl / "plugins" / PLUGIN_KEY
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PLUGIN_SOURCE, target)
    for path in target.rglob("*"):  # OFL's lint wants LF, whatever the checkout of this repository has
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    run(["node", "cli/build-plugin-data.js"], ofl)


def uninstall_plugin(ofl: Path) -> None:
    """Take the plugin out again and restore what the build changed (OFL is never left modified)."""
    shutil.rmtree(ofl / "plugins" / PLUGIN_KEY, ignore_errors=True)
    run(["git", "checkout", "--quiet", "--", "plugins/plugins.json"], ofl, check=False)


def install_hand_written(ofl: Path) -> list[str]:
    """The item 50 types that are not in OFL were written by hand in OFL's format (``tools/fixture_sources/``): put them
    into the checkout's ``fixtures/`` for the run (``remove_hand_written`` takes them out) so that OFL's CLI can export them."""
    keys = []
    for fx in LIBRARY:
        if fx.ofl or not fx.source_file:
            continue
        maker, fixture = fx.source_file.split("__")
        target = ofl / "fixtures" / maker / f"{fixture}.json"
        if target.exists() or not (ofl / "fixtures" / maker).is_dir():
            print(f"note: {maker}/{fixture} is not put into OFL ({'it is there already' if target.exists() else 'no such manufacturer'})")
            continue
        data = read_json(SOURCES / f"{fx.source_file}.json")  # without $schema, which OFL's model needs: added for the run
        data = {"$schema": "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/schemas/fixture.json", **data}
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        keys.append(f"{maker}/{fixture}")
    return keys


def remove_hand_written(ofl: Path, keys: list[str]) -> None:
    for key in keys:
        (ofl / "fixtures" / f"{key}.json").unlink(missing_ok=True)


# --------------------------------------------------------------------------- the fixtures


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ofl_input(ofl: Path, key: str, manufacturers: dict[str, Any]) -> tuple[dict | None, str | None]:
    """The OFL JSON of a fixture the way OFL's model hands it to a plugin (a twin of another brand: the other brand's
    JSON with the twin's name), and the manufacturer's name. ``None`` for a redirect that isn't a twin."""
    data = read_json(ofl / "fixtures" / f"{key}.json")
    if "redirectTo" in data:
        if data.get("reason") != "SameAsDifferentBrand":
            return None, None
        data = {**read_json(ofl / "fixtures" / f"{data['redirectTo']}.json"), "name": data["name"]}
    return data, manufacturers.get(key.split("/")[0], {}).get("name")


def schema_version(ofl: Path) -> str:
    return read_json(ofl / "schemas" / "fixture.json")["version"]


def app_file(data: dict, key: str, manufacturer: str | None, version: str, **origin: str) -> tuple[str, dict] | None:
    """(type name, content) of the file the app saves after importing the fixture, or None when nothing is imported."""
    result = import_fixture(copy.deepcopy(data), fixture=key, manufacturer=manufacturer, schema_version=version, **origin)
    if result.ftype is None:
        return None
    ftype = FixtureType.model_validate(result.ftype | {"name": result.name})
    return result.name, ftype.model_dump(mode="json", exclude_none=True, exclude={"name"})


# --------------------------------------------------------------------------- comparing


INTEGER_KEY = re.compile(r"0|[1-9][0-9]{0,8}")  # what a JavaScript object lists first, in number order, whatever the file says


def differences(want: Any, got: Any, path: str = "", notes: list[str] | None = None) -> list[str]:
    """Where ``got`` isn't ``want``: types, key sets, the order of keys, values (1 == 1.0). The order of the keys of an
    object that has keys like "1" and "2" can't be the file's in JavaScript: that goes to ``notes`` (when given), not to the result."""
    if isinstance(want, bool) or isinstance(got, bool):
        return [] if want is got else [f"{path}: {want!r} != {got!r}"]
    if isinstance(want, dict) and isinstance(got, dict):
        out: list[str] = []
        if set(want) != set(got):
            out.append(f"{path}: keys differ, only in the app's: {sorted(set(want) - set(got))}, only in the plugin's: {sorted(set(got) - set(want))}")
        elif list(want) != list(got):
            line = f"{path}: the order of the keys differs: {list(want)[:8]} / {list(got)[:8]}"
            if notes is not None and any(INTEGER_KEY.fullmatch(key) for key in got):
                notes.append(line)
            else:
                out.append(line)
        for key in want:
            if key in got:
                out += differences(want[key], got[key], f"{path}/{key}", notes)
        return out
    if isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            return [f"{path}: {len(want)} entries != {len(got)}"]
        return [d for i, (a, b) in enumerate(zip(want, got)) for d in differences(a, b, f"{path}[{i}]", notes)]
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return [] if want == got else [f"{path}: {want!r} != {got!r}"]
    return [] if want == got and type(want) is type(got) else [f"{path}: {str(want)[:60]!r} != {str(got)[:60]!r}"]


def without_origin(content: dict) -> dict:
    """An import's file with what only an import knows taken out: ``source.commit``, ``source.file``, the commit in the description."""
    out = copy.deepcopy(content)
    out["source"].pop("commit", None)
    out["source"].pop("file", None)
    out["description"] = re.sub(r", commit [0-9a-f]{7}\)", ")", out["description"])
    return out


def as_app_text(content: dict) -> str:
    """The file's text as the app writes it, but with ``1.0`` written the way JavaScript writes it (``1``)."""
    text = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    return re.sub(r"(?m)((?:^\s*|: ))(-?\d+)\.0(,?)$", r"\1\2\3", text)


class Loader(logging.Handler):
    """Collects what the model's validators log (a repaired file is not a loadable one)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


# --------------------------------------------------------------------------- the run


def export_with_cli(ofl: Path, keys: list[str], out: Path) -> subprocess.CompletedProcess:
    paths = [f"fixtures/{key}.json" for key in keys]
    return run(["node", "cli/export-fixture.js", "-p", PLUGIN_KEY, "-o", str(out), *paths], ofl, check=False)


def check_fixtures(ofl: Path, keys: list[str], everything: bool, problems: list[str]) -> dict[str, int]:
    manufacturers = read_json(ofl / "fixtures" / "manufacturers.json")
    version = schema_version(ofl)
    out = Path(tempfile.mkdtemp(prefix="pitchcontrol-plugin-out-"))
    expected: dict[str, tuple[str, dict]] = {}  # key -> (type name, the app's file)
    nothing: list[str] = []  # keys the app imports nothing from
    for key in keys:
        data, maker = ofl_input(ofl, key, manufacturers)
        if data is None:
            continue
        made = app_file(data, key, maker, version)
        if made is None:
            nothing.append(key)
        else:
            expected[key] = made
            with_origin = app_file(data, key, maker, version, commit=FAKE_COMMIT, file=f"{key.split('/')[1]}.json")
            assert with_origin is not None
            left = differences(made[1], without_origin(with_origin[1]))
            if left:
                problems.append(f"{key}: an import with a commit and a file differs from one without in more than the documented places: {left[:3]}")

    if everything:  # one call: OFL's -a (a fixture without a usable mode just gets no file)
        result = run(["node", "cli/export-fixture.js", "-p", PLUGIN_KEY, "-a", "-o", str(out)], ofl, check=False)
        if result.returncode != 0:
            problems.append(f"export -a failed: {result.stderr[-500:]}")
    else:
        if expected:
            result = export_with_cli(ofl, list(expected), out)
            if result.returncode != 0:
                problems.append(f"export of {len(expected)} fixtures failed: {result.stderr[-800:]}")
        for key in nothing:  # the plugin must refuse a fixture the app imports nothing from, with the reason
            result = export_with_cli(ofl, [key], out)
            if result.returncode == 0 or "can't express any mode" not in result.stderr:
                problems.append(f"{key}: the app imports nothing, the plugin should fail with a reason (exit {result.returncode}): {result.stderr[-200:]}")

    exported: dict[str, tuple[str, str]] = {}  # key -> (file name, text)
    for path in sorted(out.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        exported[json.loads(text)["source"]["fixture"]] = (path.name, text)

    handler = Loader()
    logging.getLogger("pitchcontrol").addHandler(handler)
    order_notes: list[str] = []
    counts = {"fixtures": len(keys), "compared": 0, "same text": 0, "nothing": len(nothing), "renamed": 0}
    try:
        for key, (type_name, want) in expected.items():
            if key not in exported:
                problems.append(f"{key}: the app imports it, the plugin made no file")
                continue
            name, text = exported[key]
            got = json.loads(text)
            counts["compared"] += 1
            if name != f"{type_name}.json":
                counts["renamed"] += 1  # two fixtures with the same type name: the later gets -2 (documented)
                if not re.fullmatch(re.escape(type_name) + r"-\d+\.json", name):
                    problems.append(f"{key}: file name '{name}', the app names the type '{type_name}'")
            for line in differences(want, got, notes=order_notes)[:5]:
                problems.append(f"{key}: {line}")
            if text == as_app_text(want):
                counts["same text"] += 1
            handler.messages.clear()
            loaded = FixtureType.model_validate(got | {"name": type_name})
            if handler.messages:
                problems.append(f"{key}: the app reports when loading the file: {handler.messages[:2]}")
            again = loaded.model_dump(mode="json", exclude_none=True, exclude={"name"})
            for line in differences(got, again)[:3]:
                problems.append(f"{key}: loading and saving the file changes it: {line}")
        for key in exported:
            if key not in expected:
                problems.append(f"{key}: the plugin made a file, the app imports nothing from it")
    finally:
        logging.getLogger("pitchcontrol").removeHandler(handler)
    shutil.rmtree(out, ignore_errors=True)
    counts["order"] = len(order_notes)
    return counts


def ofl_checks(ofl: Path, keys: list[str], problems: list[str]) -> list[str]:
    """OFL's own checks of the plugin: lint, the export tests, the plugin list."""
    lines = []
    lint = run(["npx", "eslint", f"plugins/{PLUGIN_KEY}"], ofl, check=False)
    lines.append("eslint plugins/pitch-control: " + ("clean" if lint.returncode == 0 else "FAILED"))
    if lint.returncode != 0:
        problems.append("eslint:\n" + (lint.stdout + lint.stderr)[-2500:])
    test = run(["node", "cli/run-export-test.js", "-p", PLUGIN_KEY, *[f"fixtures/{key}.json" for key in keys]], ofl, check=False)
    failed = [line for line in test.stdout.splitlines() if "[FAIL]" in line or line.startswith("- ")]
    lines.append(f"export tests on {len(keys)} fixtures: " + ("passed" if test.returncode == 0 and not failed else "FAILED"))
    if test.returncode != 0 or failed:
        problems.append("export tests:\n" + (test.stdout + test.stderr)[-2500:])
    data = read_json(ofl / "plugins" / "plugins.json")
    listed = PLUGIN_KEY in data["exportPlugins"] and data["data"][PLUGIN_KEY]["exportTests"]
    lines.append("plugins.json lists the plugin and its export tests: " + ("yes" if listed else "NO"))
    if not listed:
        problems.append("plugins.json does not list the plugin with its export tests")
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="every fixture of the OFL checkout, not only item 50 and the extras")
    parser.add_argument("--ofl", type=Path, help="an OFL checkout to use (default: a pinned shallow one in the temp folder)")
    parser.add_argument("--ofl-source", default=OFL_REPO, help="where to fetch OFL from the first time (a URL or a local clone)")
    parser.add_argument("--skip-lint", action="store_true", help="don't run eslint and the export tests (no OFL dev dependencies)")
    args = parser.parse_args()

    ofl = (args.ofl or Path(tempfile.gettempdir()) / "pitchcontrol-ofl-check").resolve()
    if args.ofl is None:
        prepare_ofl(ofl, args.ofl_source)
    if args.ofl is not None and not (ofl / "node_modules").exists():
        raise SystemExit(f"{ofl} has no node_modules: run 'npm ci' there first")
    run(["node", "cli/build-register.js"], ofl)

    item50 = [fx.ofl for fx in LIBRARY if fx.ofl]
    keys = item50 + [key for key in EXTRAS if key not in item50]
    if args.all:
        register = read_json(ofl / "fixtures" / "register.json")["filesystem"]
        keys = [k for k, v in register.items() if "redirectTo" not in v or v.get("reason") == "SameAsDifferentBrand"]
    missing = [k for k in keys if not (ofl / "fixtures" / f"{k}.json").exists()]
    if missing:
        raise SystemExit(f"not in this OFL checkout: {missing}")

    problems: list[str] = []
    hand_written = [] if args.all else install_hand_written(ofl)
    install_plugin(ofl)
    try:
        keys = [*hand_written, *keys]
        counts = check_fixtures(ofl, keys, args.all, problems)
        checks = [] if args.skip_lint else ofl_checks(ofl, keys[:60], problems)
    finally:
        uninstall_plugin(ofl)
        remove_hand_written(ofl, hand_written)

    print("=" * REPORT_WIDTH)
    print(f"OFL {OFL_COMMIT[:7]} (schema {schema_version(ofl)}), plugin {PLUGIN_SOURCE.relative_to(ROOT)}")
    print(f"fixtures: {counts['fixtures']}; the app imports a file from {counts['compared'] + 0} of them, nothing from {counts['nothing']}")
    print(f"compared (content, order of keys, loads in the app's model without a warning): {counts['compared']}; the same text as the app writes (but for 1.0 written 1): {counts['same text']}")
    if counts["order"]:
        print(f"objects whose keys (like \"1\", \"2\") JavaScript puts first, so the order of the keys differs: {counts['order']}")
    if counts["renamed"]:
        print(f"files with a number added to the name (two fixtures, one type name): {counts['renamed']}")
    for line in checks:
        print(line)
    if args.all:
        print("(the item 50 fixtures and the extras were not listed separately: this was the whole library)")
    else:
        print("the item 50 fixtures (the three written by hand are copied into OFL for the run) and these extras:")
        for key, why in EXTRAS.items():
            print(f"  {key}: {why}")
    if problems:
        print("-" * REPORT_WIDTH)
        print(f"{len(problems)} problem(s):")
        for problem in problems[:40]:
            print(" -", problem)
        raise SystemExit(1)
    print("PASS")


if __name__ == "__main__":
    main()
