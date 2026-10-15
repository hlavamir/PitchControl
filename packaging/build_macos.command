#!/bin/bash
# Build PitchControl.app into dist/ (run on a Mac; the app runs on the same CPU type).
#
# What is installed (the UI packages, the Python environment) is checked first and only installed when it is
# missing or out of date; the script says what and why and asks once ("Install now? [Y/n]", Enter = yes). On CI,
# or without a terminal, it installs without asking. "--check" only says what would be installed.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Everything the steps print, errors included, also goes to build-macos.log in the repo root (the latest run only),
# which is what to send when a build fails or warns. The script runs itself once more with its output through tee:
# the Terminal still shows everything, the prompt below still reads from the keyboard, and the exit code is kept.
# It starts itself by its absolute path, because $0 can be relative and the script has changed folder (cd above).
# CI keeps the output on the console as well; "--check" writes no log, so it doesn't replace the last build's.
if [ -z "${PC_BUILD_LOGGING:-}" ] && [ "${1:-}" != "--check" ]; then
    LOG="$ROOT/build-macos.log"
    ver() { if command -v "$1" >/dev/null 2>&1; then "$@" 2>&1 | head -n 1; else echo "not found"; fi; }
    {
        echo "PitchControl macOS build, $(date)"
        echo "Folder: $ROOT"
        echo "Mac: $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null), $(uname -m)"
        echo "node: $(ver node --version)"
        echo "npm: $(ver npm --version)"
        echo "python3: $(ver python3 --version)"
        echo "uv: $(ver uv --version)"
        echo "git: $(ver git --version)"
        echo
    } 2>&1 | tee "$LOG"
    set +e
    PC_BUILD_LOGGING=1 /bin/bash "$ROOT/packaging/build_macos.command" "$@" 2>&1 | tee -a "$LOG"
    RC="${PIPESTATUS[0]}"
    set -e
    if [ "$RC" -ne 0 ]; then
        echo "BUILD FAILED (exit code $RC), full log: $LOG" | tee -a "$LOG"
    else
        echo "Full log: $LOG"
    fi
    exit "$RC"
fi

# the UI build (Vite 8) needs Node 20.19 or newer, or 22.12 or newer
if ! command -v node >/dev/null 2>&1; then
    echo "Node.js was not found. Install the LTS version from https://nodejs.org and run this again."
    exit 1
fi
NODE_VER="$(node --version)"
IFS=. read -r NODE_MAJOR NODE_MINOR _ <<<"${NODE_VER#v}"
if ! { [ "$NODE_MAJOR" -gt 22 ] || { [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -ge 12 ]; } || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -ge 19 ]; }; }; then
    echo "Node.js $NODE_VER is too old: the UI build needs 20.19 or newer, or 22.12 or newer. Install the LTS version from https://nodejs.org and run this again."
    exit 1
fi

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
# a marker in each environment says what it was installed with: Node or Python version, and the hash of the file that lists the packages
UI_NOW="$NODE_VER $(sha frontend/package-lock.json)"
UI_MARKER=frontend/node_modules/.installed-with
PY=backend/.venv/bin/python
PY_MARKER=backend/.venv/.installed-with
if [ -x "$PY" ]; then PY_NOW="$("$PY" --version) $(sha backend/pyproject.toml)"; else PY_NOW=""; fi

NEED_UI="" NEED_PY=""
if [ ! -d frontend/node_modules ]; then NEED_UI="not installed yet"
elif [ ! -f "$UI_MARKER" ]; then NEED_UI="no record of what installed them (installed before this check existed)"
elif [ "$(cut -d' ' -f1 "$UI_MARKER")" != "$NODE_VER" ]; then NEED_UI="installed with Node $(cut -d' ' -f1 "$UI_MARKER" | tr -d v), now Node ${NODE_VER#v}"
elif [ "$(cat "$UI_MARKER")" != "$UI_NOW" ]; then NEED_UI="package-lock.json changed since the last install"
fi
if [ ! -x "$PY" ]; then NEED_PY="not created yet"
elif [ ! -f "$PY_MARKER" ]; then NEED_PY="no record of what installed it (installed before this check existed)"
elif [ "$(cat "$PY_MARKER")" != "$PY_NOW" ]; then NEED_PY="pyproject.toml or the Python version changed since the last install"
fi

if [ -n "$NEED_UI$NEED_PY" ]; then
    echo "Needs installing:"
    [ -n "$NEED_UI" ] && echo "  UI packages (npm ci): $NEED_UI"
    [ -n "$NEED_PY" ] && echo "  Python environment (pip install): $NEED_PY"
    if [ "${1:-}" = "--check" ]; then exit 0; fi
    if [ -z "${CI:-}" ] && [ -t 0 ]; then
        read -r -p "Install now? [Y/n] " ANSWER
        case "$ANSWER" in
            [nN]*)
                echo "Not installed. To do it by hand:"
                [ -n "$NEED_UI" ] && echo "  (cd frontend && npm ci)"
                [ -n "$NEED_PY" ] && echo "  (cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -e \".[build]\")   # or uv"
                exit 1 ;;
        esac
    fi
elif [ "${1:-}" = "--check" ]; then
    echo "Nothing to install."
    exit 0
fi

echo "== web UI"
if [ -n "$NEED_UI" ]; then
    (cd frontend && npm ci)
    echo "$UI_NOW" > "$UI_MARKER"
fi
(cd frontend && npm run build --silent)

echo "== Python environment"
if [ -n "$NEED_PY" ]; then
    cd backend
    if command -v uv >/dev/null 2>&1; then
        [ -x .venv/bin/python ] || uv venv .venv
        uv pip install --python .venv/bin/python -e ".[build]"
    else
        [ -x .venv/bin/python ] || python3 -m venv .venv
        .venv/bin/python -m pip install -e ".[build]"
    fi
    cd "$ROOT"
    echo "$("$PY" --version) $(sha backend/pyproject.toml)" > "$PY_MARKER"
fi
PY="$ROOT/backend/.venv/bin/python"
[ -f packaging/icon.icns ] || "$PY" packaging/make_icon.py

echo "== PyInstaller"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath dist --workpath build packaging/pitchcontrol.spec

echo "== smoke test"
"dist/PitchControl.app/Contents/MacOS/PitchControl" --smoke-test --no-hardware --data "$(mktemp -d)" --port 8499

ARCH="$(uname -m)"
rm -f "dist/PitchControl-macos-$ARCH.zip"
ditto -c -k --keepParent dist/PitchControl.app "dist/PitchControl-macos-$ARCH.zip"
echo "Done: dist/PitchControl.app and dist/PitchControl-macos-$ARCH.zip"
