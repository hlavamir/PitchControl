"""Asking before the desktop app quits.

Quitting stops the engine, so the lights freeze on their last frame, and unsaved edits in the pages are lost.
``quit_reasons`` decides whether to ask (a plain function: no window needed to test it); ``confirm_quit`` shows
the question with the system's own dialog.

The question is not asked through pywebview: its ``closing`` handlers run on the window's UI thread, where pywebview's
confirmation dialog waits for that same thread (macOS) and the page can't be asked for its state (``evaluate_js``).
So every page reports its unsaved edits to the engine (``UnsavedReports``, once a second), and the dialogs are the
operating system's: a message box on Windows, ``osascript`` on macOS.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time

log = logging.getLogger(__name__)

TITLE = "Quit PitchControl?"
REPORT_MAX_AGE_S = 3.0  # a page that hasn't reported for this long is gone (a closed tab) or stuck


class UnsavedReports:
    """What the open pages say about their unsaved edits. Each page load (the desktop window, a browser tab, a reload)
    has its own id and reports every second; the answer is the union of the fresh reports, so one page's ``[]`` doesn't
    hide another's edits and a closed tab's last report doesn't stay."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: dict[str, tuple[float, list[str]]] = {}

    def report(self, client: str, pages: list[str], now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._reports[client] = (now, list(pages))
            for old in [c for c, (t, _) in self._reports.items() if now - t > 60]:
                del self._reports[old]

    def pages(self, now: float | None = None) -> list[str] | None:
        """The pages with unsaved edits on any page that reported lately; None when none did (unknown)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            fresh = [pages for t, pages in self._reports.values() if now - t <= REPORT_MAX_AGE_S]
        if not fresh:
            return None
        return sorted({p for pages in fresh for p in pages})


def live_outputs(outputs: dict | None) -> bool:
    """Whether any output is connected: an Enttec interface, Art-Net or PitchPls v2 (``Outputs.status()``)."""
    if not outputs:
        return False
    entries = [*(outputs.get("enttec") or []), outputs.get("artnet"), outputs.get("pitchpls_v2")]
    return any(isinstance(e, dict) and e.get("connected") for e in entries)


def with_live_edits(pages: list[str] | None, live: list[str]) -> list[str] | None:
    """The pages' reports plus the edits the server itself knows are not written yet: the rig and fixture types, whose
    edits are live in the engine and written only by Save, so they count whichever page is open (or none)."""
    return None if pages is None else sorted({*pages, *live})


def quit_reasons(unsaved: list[str] | None, outputs: dict | None) -> list[str]:
    """Why quitting needs a question, one sentence each; empty: quit without asking.

    ``unsaved`` is the labels of the pages with unsaved edits, or None when that couldn't be found out (the page
    never reported, or reading failed): then ask anyway, as if there were unsaved edits."""
    reasons = []
    if live_outputs(outputs):
        reasons.append("The lights are live: quitting freezes the output on its last frame.")
    if unsaved is None:
        reasons.append("Unsaved changes: PitchControl couldn't check whether a page has edits that aren't saved.")
    elif unsaved:
        reasons.append(f"Unsaved changes on {', '.join(unsaved)}: quitting drops them.")
    return reasons


def confirm_quit(reasons: list[str]) -> bool:
    """Show the reasons and ask. True = quit. Whatever goes wrong with the dialog itself, the answer is True:
    the app must always be able to quit."""
    message = "\n\n".join(reasons) + "\n\nQuit anyway?"
    try:
        if sys.platform == "win32":
            import ctypes

            MB_OKCANCEL, MB_ICONWARNING, MB_SETFOREGROUND, MB_TOPMOST, IDOK = 0x1, 0x30, 0x10000, 0x40000, 1
            answer = ctypes.windll.user32.MessageBoxW(None, message, TITLE, MB_OKCANCEL | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST)
            return answer != 2  # IDCANCEL; 0 = the call failed
        if sys.platform == "darwin":
            script = [
                "on run argv",
                'display dialog (item 1 of argv) with title "' + TITLE + '" buttons {"Cancel", "Quit"} default button "Cancel" with icon caution',
                "end run",
            ]
            res = subprocess.run(["osascript", *sum((["-e", line] for line in script), []), message], capture_output=True, text=True)
            return not (res.returncode != 0 and "-128" in res.stderr)  # -128: Cancel was pressed
        log.warning("no quit dialog on %s: quitting without asking (%s)", sys.platform, "; ".join(reasons))
    except Exception:  # noqa: BLE001
        log.exception("the quit dialog failed: quitting")
    return True
