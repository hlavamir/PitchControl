"""Fetch fixtures from the Open Fixture Library's GitHub repository (item 53's online import).

The list of manufacturers is ``fixtures/manufacturers.json``, the fixtures of a manufacturer are the files of its
folder (GitHub's contents API: OFL has no index file in the repository), a fixture is its ``.json`` file. Everything is
read at one commit (the head of ``master`` when the dialog opens), so the files of one import fit together and the
type can say which commit it came from. ``fetch_text`` is the only function that touches the network; the tests replace it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .. import __version__

REPO = "OpenLightingProject/open-fixture-library"
RAW = f"https://raw.githubusercontent.com/{REPO}"
API = f"https://api.github.com/repos/{REPO}"

KEY = re.compile(r"[a-z0-9][a-z0-9\-]*")
REF = re.compile(r"master|[0-9a-f]{7,40}")


class OnlineError(Exception):
    """The Open Fixture Library can't be reached or doesn't have what was asked; the message is for the user."""


def fetch_text(url: str, accept: str | None = None, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": f"PitchControl/{__version__}", **({"Accept": accept} if accept else {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise OnlineError("the Open Fixture Library doesn't have that fixture") from exc
        if exc.code in (403, 429):
            raise OnlineError("GitHub is limiting requests from this connection for now: try again in a while, or import a downloaded .json file") from exc
        raise OnlineError(f"GitHub answered {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise OnlineError(f"can't reach the Open Fixture Library on GitHub ({getattr(exc, 'reason', exc)}): is this computer online?") from exc


def _json(url: str, accept: str | None = None) -> Any:
    try:
        return json.loads(fetch_text(url, accept))
    except ValueError as exc:
        raise OnlineError("the Open Fixture Library's answer is not JSON") from exc


def check_key(key: str, what: str) -> str:
    if not KEY.fullmatch(key):
        raise OnlineError(f"'{key}' is not a valid {what} key (lower-case letters, digits and - only)")
    return key


def check_ref(ref: str) -> str:
    if not REF.fullmatch(ref):
        raise OnlineError(f"'{ref}' is not a git commit")
    return ref


def latest_commit() -> str:
    """The head of OFL's ``master`` (the ref ``master`` itself if GitHub's API doesn't answer)."""
    try:
        sha = fetch_text(f"{API}/commits/master", accept="application/vnd.github.sha").strip()
    except OnlineError:
        return "master"
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else "master"


def manufacturers(ref: str) -> list[dict[str, str]]:
    data = _json(f"{RAW}/{check_ref(ref)}/fixtures/manufacturers.json")
    return sorted(({"key": k, "name": str(v.get("name", k))} for k, v in data.items() if not k.startswith("$") and isinstance(v, dict)), key=lambda m: m["name"].lower())


def fixtures_of(manufacturer: str, ref: str) -> list[str]:
    """The fixture keys of one manufacturer, alphabetical."""
    listing = _json(f"{API}/contents/fixtures/{check_key(manufacturer, 'manufacturer')}?ref={check_ref(ref)}")
    if not isinstance(listing, list):
        raise OnlineError("the Open Fixture Library has no such manufacturer")
    return sorted(item["name"][:-5] for item in listing if isinstance(item, dict) and str(item.get("name", "")).endswith(".json"))


def fixture(key: str, ref: str) -> dict:
    """One fixture's JSON; ``key`` is ``manufacturer/fixture``."""
    maker, _, name = key.partition("/")
    return _json(f"{RAW}/{check_ref(ref)}/fixtures/{check_key(maker, 'manufacturer')}/{check_key(name, 'fixture')}.json")


def schema_version(ref: str) -> str | None:
    """The version of OFL's fixture schema at that commit, or None."""
    try:
        version = _json(f"{RAW}/{check_ref(ref)}/schemas/fixture.json").get("version")
    except OnlineError:
        return None
    return version if isinstance(version, str) else None


def parse_key(text: str) -> str:
    """``manufacturer/fixture`` from that, or from a page address of open-fixture-library.org (or its GitHub file)."""
    text = text.strip()
    match = re.search(r"open-fixture-library\.org/([a-z0-9\-]+)/([a-z0-9\-]+)", text) or re.search(r"/fixtures/([a-z0-9\-]+)/([a-z0-9\-]+)\.json", text)
    if match:
        return f"{match[1]}/{match[2]}"
    if re.fullmatch(r"[a-z0-9\-]+/[a-z0-9\-]+", text):
        return text
    raise OnlineError("use the fixture's key (manufacturer/fixture, as in the address of its page on open-fixture-library.org)")
