"""Help → About → Check for updates (item 82): version comparison, the zip of this platform, and the offline cases."""

import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from pitchcontrol import updates
from pitchcontrol.engine.engine import Engine
from pitchcontrol.server.app import create_app
from pitchcontrol.updates import check, download_url, parse_version, platform_suffix

PAGE = "https://github.com/hlavamir/PitchControl/releases/tag/v1.9.0"
MAC = "https://github.com/hlavamir/PitchControl/releases/download/v1.9.0/PitchControl-1.9.0-macos-arm64.zip"
WIN = "https://github.com/hlavamir/PitchControl/releases/download/v1.9.0/PitchControl-1.9.0-windows-x64.zip"
RELEASE = {
    "tag_name": "v1.9.0",
    "html_url": PAGE,
    "published_at": "2026-11-01T10:00:00Z",
    "body": "Check for updates.",
    "assets": [
        {"name": "PitchControl-1.9.0-macos-arm64.zip", "browser_download_url": MAC},
        {"name": "PitchControl-1.9.0-windows-x64.zip", "browser_download_url": WIN},
    ],
}


@pytest.fixture(autouse=True)
def fresh_cache():
    updates._cache = None
    yield
    updates._cache = None


def test_parse_version_reads_tags_and_dev_labels():
    assert parse_version("v1.9.0") == (1, 9, 0)
    assert parse_version("1.8.3") == (1, 8, 3)
    assert parse_version("1.8.3+2 (abc1234)") == (1, 8, 3)  # commits after a release: its base version
    assert parse_version("1.9.0-dev (abc1234, modified)") == (1, 9, 0)
    assert parse_version("1.10.0") > parse_version("1.9.9")  # numbers, not text
    assert parse_version("nightly") is None
    assert parse_version("") is None


def test_status_newer_latest_and_a_local_version_past_the_release():
    newer = check("1.8.3", fetch=lambda: RELEASE, suffix="macos-arm64")
    assert newer == {
        "status": "newer",
        "current": "1.8.3",
        "latest": "1.9.0",
        "published": "2026-11-01T10:00:00Z",
        "notes": "Check for updates.",
        "url": MAC,
        "page": PAGE,
        "error": None,
    }
    assert check("1.9.0", fetch=lambda: RELEASE)["status"] == "latest"
    assert check("1.9.0-dev (abc1234)", fetch=lambda: RELEASE)["status"] == "latest"  # a dev build of the release: not older
    assert check("1.8.3+2 (abc1234)", fetch=lambda: RELEASE)["status"] == "newer"
    assert check("2.0.0", fetch=lambda: RELEASE)["status"] == "latest"  # newer than the release: up to date


def test_download_link_per_platform():
    assert download_url(RELEASE, "macos-arm64") == MAC
    assert download_url(RELEASE, "windows-x64") == WIN
    assert download_url(RELEASE, None) == PAGE  # Linux, Intel Mac: no build
    no_windows = {**RELEASE, "assets": RELEASE["assets"][:1]}
    assert download_url(no_windows, "windows-x64") == PAGE  # the zip isn't attached (yet): the release page
    assert download_url({**RELEASE, "assets": None}, "macos-arm64") == PAGE
    assert platform_suffix("darwin", "arm64") == "macos-arm64"
    assert platform_suffix("win32", "AMD64") == "windows-x64"
    assert platform_suffix("darwin", "x86_64") is None
    assert platform_suffix("linux", "x86_64") is None


@pytest.mark.parametrize(
    "error, reason",
    [
        (urllib.error.URLError("nodename nor servname provided"), "nodename nor servname provided"),
        (urllib.error.HTTPError(updates.LATEST_URL, 403, "rate limit exceeded", {}, None), "GitHub answered 403"),
        (TimeoutError("timed out"), "no answer in time"),
        (json.JSONDecodeError("Expecting value", "<html>", 0), "Expecting value: line 1 column 1 (char 0)"),
        (ConnectionResetError("reset"), "reset"),
    ],
)
def test_offline_cases(error, reason):
    def fetch():
        raise error

    res = check("1.8.3", fetch=fetch)
    assert res["status"] == "offline" and res["current"] == "1.8.3" and res["error"] == reason
    assert res["url"] is None and res["latest"] is None


def test_offline_when_the_answer_is_not_a_release():
    assert check("1.8.3", fetch=lambda: {"message": "Not Found"})["status"] == "offline"
    assert check("1.8.3", fetch=lambda: {"tag_name": "nightly"})["status"] == "offline"


def test_endpoint_is_cached_for_a_few_seconds(store, monkeypatch):
    calls = []

    def fetch():
        calls.append(1)
        return RELEASE

    monkeypatch.setattr(updates, "fetch_latest", fetch)
    client = TestClient(create_app(Engine(store, enable_hardware=False)), client=("127.0.0.1", 50000))
    first = client.get("/api/update-check")
    assert first.status_code == 200 and first.json()["status"] in ("newer", "latest")
    assert client.get("/api/update-check").json() == first.json()
    assert len(calls) == 1


def test_endpoint_offline_is_not_an_error(store, monkeypatch):
    def fetch():
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(updates, "fetch_latest", fetch)
    client = TestClient(create_app(Engine(store, enable_hardware=False)), client=("127.0.0.1", 50000))
    res = client.get("/api/update-check")
    assert res.status_code == 200
    assert res.json()["status"] == "offline" and res.json()["error"] == "no route to host"
