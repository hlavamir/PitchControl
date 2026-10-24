"""Help → About → Check for updates (item 82): asks GitHub for the newest release, only when the button is pressed.
Nothing is downloaded or installed by the app; the answer carries the link for the user's browser."""

from __future__ import annotations

import json
import platform
import re
import sys
import time
import urllib.error
import urllib.request

from . import __version__

LATEST_URL = "https://api.github.com/repos/hlavamir/PitchControl/releases/latest"
TIMEOUT = 5  # seconds
CACHE_SECONDS = 5  # a double click or two windows don't ask GitHub twice (its limit: 60 requests an hour per address)
MAX_NOTES = 6000  # characters of the release text sent to the UI

_cache: tuple[float, dict] | None = None


def parse_version(text: str) -> tuple[int, int, int] | None:
    """"v1.9.0" -> (1, 9, 0); a dev label ("1.8.3+2 (abc1234)", "1.9.0-dev (abc1234)") counts as its base version."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def platform_suffix(sys_platform: str = sys.platform, machine: str = "") -> str | None:
    """The end of the release zip's name for this computer; None where there is no build (Linux, Intel Mac, Windows on ARM)."""
    machine = (machine or platform.machine()).lower()
    if sys_platform == "darwin" and machine in ("arm64", "aarch64"):
        return "macos-arm64"
    if sys_platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    return None


def download_url(release: dict, suffix: str | None) -> str:
    """The zip of this computer's platform from the release's assets, else the release page."""
    if suffix:
        for asset in release.get("assets") or []:
            name, url = asset.get("name", ""), asset.get("browser_download_url")
            if url and name.endswith(f"-{suffix}.zip"):
                return url
    return release.get("html_url") or ""


def fetch_latest() -> dict:
    """GitHub's latest release as JSON. Raises OSError (network, HTTP, timeout) or ValueError (not JSON)."""
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": f"PitchControl/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("unexpected answer")
    return data


def offline(current: str, error: str) -> dict:
    return {"status": "offline", "current": current, "latest": None, "published": None, "notes": None, "url": None, "page": None, "error": error}


def check(current: str = __version__, *, fetch=None, suffix: str | None = None) -> dict:
    """The update-check answer (``GET /api/update-check``): latest | newer | offline; never raises."""
    try:
        release = (fetch or fetch_latest)()  # looked up at call time: a test replaces fetch_latest
        tag = str(release.get("tag_name", ""))
    except urllib.error.HTTPError as e:  # before OSError: a subclass of it
        return offline(current, f"GitHub answered {e.code}")
    except TimeoutError:
        return offline(current, "no answer in time")
    except urllib.error.URLError as e:
        return offline(current, str(e.reason) or "no connection")
    except (OSError, ValueError, AttributeError) as e:  # ValueError: bad JSON
        return offline(current, str(e) or "unexpected answer")
    latest, mine = parse_version(tag), parse_version(current)
    if latest is None or mine is None:
        return offline(current, "unexpected answer")
    page = release.get("html_url") or ""
    return {
        "status": "newer" if latest > mine else "latest",  # a local version past the release counts as up to date
        "current": current,
        "latest": ".".join(map(str, latest)),
        "published": release.get("published_at"),
        "notes": str(release.get("body") or "")[:MAX_NOTES],
        "url": download_url(release, suffix),
        "page": page,
        "error": None,
    }


def check_cached() -> dict:
    """``check()`` for this computer, remembered for a few seconds."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    result = check(suffix=platform_suffix())
    _cache = (now, result)
    return result
