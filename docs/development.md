# Development and the standalone app

What the app is made of, downloading, running from source, building the standalone app and releasing a version.

[← All documentation pages](README.md)

## Overview

- **Backend** (`backend/`, Python): the engine, which runs at 40 FPS in its own thread and owns audio, MIDI and all outputs. It keeps running if the browser is closed.
- **Frontend** (`frontend/`, Vite + React + TypeScript + Tailwind): the pages General, Dimmers, Fixtures, Rig, Connections, Fog, Control Desk, Settings and Help. It talks to the backend over HTTP and a WebSocket.
- **Config** (`config/`): the read-only defaults that ship with the app (fixture types, the MIDI mapping, the Default rig, settings). What you make or change is kept in your data folder, see [Folders](folders.md).

## Download

Ready-to-run builds for macOS (Apple Silicon) and Windows are on the [Releases page](https://github.com/hlavamir/PitchControl/releases/latest). Download the zip for your system and unpack it; no Python or Node needed. A downloaded app keeps what you make or change in `Documents/PitchControl/` and this computer's settings in the app-data folder; see [Folders](folders.md). What changed between versions is in [CHANGELOG.md](../CHANGELOG.md); the running version is shown in Help → About.

## Run

**macOS:** double-click `run.command`. On first run it sets up the Python environment and builds the UI (it rebuilds when sources change), then starts the backend and opens the UI in the browser. Close the Terminal window to stop. Extra arguments are passed through, e.g. `./run.command --no-hardware`.

**Windows:** double-click `run.bat` — same behaviour (uses `uv` if installed, otherwise `py -3` / `python`).

Manual setup — requirements: Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/), and Node 20.19 or newer, or 22.12 or newer (only to build the UI; Vite 8 refuses older versions).

```bash
cd backend
uv venv && uv pip install -e ".[dev]"
cd ../frontend && npm install && npm run build
cd ../backend && .venv/bin/python -m pitchcontrol
```

Open http://127.0.0.1:8420.

Options:
- `--no-hardware` runs without audio, MIDI and outputs.
- Other devices (a phone) on the network are allowed in Settings → Network, not on the command line: `--host` is ignored (see [Other devices on the network](network.md)).
- `--data <folder>` uses another data folder instead of the repo's `data/` (gitignored); `--machine <folder>` another folder for this computer's files (default: `.machine/` in the data folder); `--port`, `--logs` change the defaults.

On Windows, use `.venv\Scripts\python -m pitchcontrol`. ASIO devices appear in the device list of Connections → Audio.

For frontend development, run `npm run dev` in `frontend/` (port 5173, proxied to the backend on 8420).

Tests: `cd backend && .venv/bin/python -m pytest`; the frontend rules (MIDI mapping overlap and behaviours) have Vitest tests: `cd frontend && npm test`.

## Standalone app

`packaging/` builds a self-contained app (no Python or Node needed on the target machine). It must be built on the target OS:

- **macOS:** double-click `packaging/build_macos.command` (or run it from Terminal; needs Node.js 20.19+ or 22.12+); it produces `dist/PitchControl.app` and `dist/PitchControl-macos-<arch>.zip` (about 46 MB, 22 MB zipped). The Terminal shows everything the steps print, and the same output goes to `build-macos.log` in the repo root (the latest run only, gitignored), which is what to send when a build fails or prints warnings. An Apple Silicon build runs only on Apple Silicon Macs.
- **Windows:** double-click `packaging\build_windows.bat` (needs Node.js 20.19+ or 22.12+, and Python 3.11 or 3.12: `python-rtmidi` has no Windows wheels for newer Pythons, so the script picks 3.12 / 3.11 even when a newer one is installed too); it produces `dist\PitchControl\PitchControl.exe` and a zip. The window shows the steps and stays open at the end; everything the steps print goes to `build-windows.log` (gitignored), which is what to send when a build fails.
- **Both scripts check what is installed before they build:** the UI packages (`npm ci`, recorded in `frontend/node_modules/.installed-with` with the Node version and a hash of `package-lock.json`) and the Python environment (`backend/.venv/.installed-with`: the Python version and a hash of `pyproject.toml`). When one is missing or out of date they say what and why and ask once, `Install now? [Y/n]` (Enter = yes); "n" stops and prints the commands to run by hand. On CI, or without a terminal, they install without asking; `--check` only says what would be installed.
- **Both, on GitHub:** Actions → "PitchControl app" → Run workflow (`.github/workflows/app.yml`), then download the zips from the run.

The app shows the UI in its own window. **View → Open in browser**, **File → Open data folder** and **File → Open logs folder** are in the menu bar; Help → About shows the folders. Closing the window stops the engine: it asks first when an output is live or a page has unsaved edits.

**Menu bar.** The app has the usual menus: **File** (Save, Import Fixture ▸ Open Fixture Library… / QLC+…, Open data folder, Open logs folder, Quit), **Edit** (Cut, Copy, Paste, Select All, on the text field you are typing in), **View** (the nine pages, Full screen (on a Mac the system's own Enter Full Screen), Open in browser), **Window** (Minimize, and Zoom on macOS / Maximize on Windows) and **Help** (Documentation, Keyboard shortcuts, Show log, Report a problem, Join the Discord, About PitchControl). **Save** does what the page's Save button does (Connections, Fog, the MIDI mapping, Fixtures, Rig) and nothing on a page without one; ⌘S / Ctrl+S does the same, also while typing in a field. **Quit** asks first like the close button. On **macOS** it is the system's menu bar, with About, Settings… (⌘,) and Quit (⌘Q) under PitchControl, and ⌘1 – ⌘9 for the pages next to the plain 1 – 9 (⌘0 stays the UI scale's 100 %). On **Windows** the app draws it in its header row next to the logo, in the app's look, with the keys next to the items: **Alt** (or F10) gives it the keyboard, Alt + the underlined letter opens a menu, the arrows move, ⏎ runs an item and Esc closes; AltGr (typing @ { [) doesn't open it. **On macOS in full screen** (F, View → Full screen, ⌃⌘F, the green button, or Start in full screen) the system's menu bar slides in when the mouse reaches the top edge of the screen, as in every Mac app. A browser, on this computer or on a phone, shows no menu bar. The first Edit → Paste asks once for permission to read the clipboard (Ctrl+V needs none).

The app uses the folders described in [Folders](folders.md); it never writes into its own bundle or into the repo's `config/`.

The builds are unsigned. On first launch:
- macOS: open the app once; when macOS refuses, go to System Settings → Privacy & Security and click "Open Anyway" (right-click → Open no longer bypasses this since macOS 15).
- Windows: SmartScreen → More info → Run anyway.

macOS asks once for microphone access.

App options (for example from a terminal) are the same as for the backend (`--data`, `--machine`, `--port`, `--no-hardware`), plus `--no-window` (use the browser instead of a window).

### Releasing a version

Versions follow semantic versioning (see [CHANGELOG.md](../CHANGELOG.md)). The number lives only in `backend/src/pitchcontrol/__init__.py`.
1. Set `__version__`, and move the changelog's "Unreleased" notes under a `## X.Y.Z — date` heading.
2. If a default in `config/` changed since the last release, commit it, then record it: `backend/.venv/bin/python tools/shipped_config_history.py` (it adds every committed version of the shipped files to `config/shipped_history.py`, so a later migration recognises untouched copies) and commit that too.
3. If the UI or the screenshot script changed since the last release (`frontend/src`, `tools/screenshots.py`), retake the screenshots from a clean checkout of the release commit, so Help → About shows the plain version: build the frontend, then run `tools/screenshots.py` (see its header for the setup). Check the PNGs in `screenshots/`, then commit.
4. Commit, then tag and push: `git tag -a vX.Y.Z -m "PitchControl X.Y.Z"` and `git push origin vX.Y.Z`.
5. The "PitchControl app" workflow checks that the tag matches `__version__`, builds macOS and Windows, and creates a **draft** release with that version's changelog section. Check it on GitHub, then publish it.

Builds between releases show how far past the last tag they are, e.g. `1.1.0+3 (abc1234)`, or `1.4.0-dev (abc1234)` once the number is raised but not tagged yet.
